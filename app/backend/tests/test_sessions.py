"""T-S0.3 主链路 API 单测（无网络，fake provider）。

覆盖：上传→状态流转→segments 落库→清理文本→记录 JSON 解析落库，
以及非法扩展名/超大小/404/坏 JSON 重试与 failed 状态。
"""

from __future__ import annotations

import json


from psyapp import audio as audio_mod
from psyapp.enums import SessionStatus
from psyapp.models import Job, Record, Segment
from psyapp.providers.base import Segment as AsrSegment
from psyapp.providers.base import TranscriptResult


class FakeASR:
    name = "paraformer"

    def transcribe(self, audio_path, *, speaker_hint=None):
        return TranscriptResult(
            segments=[
                AsrSegment(0, "0", "你好，最近感觉怎么样？", 100, 2000, None),
                AsrSegment(1, "1", "最近睡眠不太好。", 2200, 4000, None),
                AsrSegment(2, "0", "能具体说说吗？", 4300, 6000, None),
                AsrSegment(3, "1", "就是工作压力大，晚上睡不着。", 6400, 9000, None),
            ],
            raw={},
        )


class FakeCleanLLM:
    name = "qwen"

    def __init__(self, responses=("清理后的对话",)):
        self.responses = list(responses)
        self.calls = 0

    def complete(self, messages, *, schema_hint=None, temperature=0.3):
        self.calls += 1
        return self.responses[min(self.calls - 1, len(self.responses) - 1)]


class FakeRecordLLM:
    name = "qwen"

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def complete(self, messages, *, schema_hint=None, temperature=0.3):
        self.calls += 1
        return self.responses[min(self.calls - 1, len(self.responses) - 1)]


GOOD_RECORD = json.dumps(
    {
        "summary": "来访者自述最近睡眠不好、工作压力大。",
        "counselor_work": "咨询师询问近况并追问细节。",
        "client_reported_topics": ["睡眠", "工作压力"],
    },
    ensure_ascii=False,
)


# ── 完整主链路 ────────────────────────────────────────────────


def test_upload_full_chain_creates_segments_clean_and_record(client, monkeypatch):
    monkeypatch.setattr("psyapp.routes.get_asr_provider", lambda s: FakeASR())
    monkeypatch.setattr("psyapp.routes.get_llm_provider", lambda s: FakeCleanLLM())
    # record 也需要独立 fake；需区分两个 llm 实例的调用
    clean = FakeCleanLLM()
    record = FakeRecordLLM([GOOD_RECORD])
    monkeypatch.setattr("psyapp.routes.get_asr_provider", lambda s: FakeASR())
    llms = iter([clean, record])
    monkeypatch.setattr("psyapp.routes.get_llm_provider", lambda s: next(llms))

    resp = client.post("/sessions", files={"file": ("x.wav", b"fake-wav-bytes", "audio/wav")})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    session_id = body["data"]["session_id"]

    detail = client.get(f"/sessions/{session_id}").json()["data"]
    assert detail["status"] == SessionStatus.DONE
    assert len(detail["segments"]) == 4
    speakers = {seg["speaker"] for seg in detail["segments"]}
    assert {"T", "P"} <= speakers
    assert detail["segments"][0]["speaker"] == "T"
    assert detail["segments"][1]["speaker"] == "P"
    assert detail["cleaned_text"] == "清理后的对话"
    assert detail["record"] is not None
    assert detail["record"]["summary"] == "来访者自述最近睡眠不好、工作压力大。"
    assert detail["record"]["counselor_work"] == "咨询师询问近况并追问细节。"
    assert detail["record"]["client_reported_topics"] == ["睡眠", "工作压力"]

    # 音频随机名落盘（非原始文件名）
    from pathlib import Path

    stored = Path(detail["audio_path"])
    assert stored.name != "x.wav"
    assert stored.name.endswith(".wav")

    # DB 侧复核：segments/records/jobs 均落库
    from psyapp.db import create_session_factory

    factory = create_session_factory(client.app.state.engine)
    db = factory()
    try:
        assert db.query(Segment).filter(Segment.session_id == session_id).count() == 4
        rec = db.query(Record).filter(Record.session_id == session_id).one()
        assert rec.basic_info["provider"] == "qwen"
        assert rec.basic_info["model"] == "qwen-max"
        assert rec.basic_info["prompt_version"] == "v1"
        jobs = db.query(Job).filter(Job.session_id == session_id).all()
        job_types = {j.type for j in jobs}
        assert {"transcribe", "clean", "record"} <= job_types
        assert all(j.status == "done" for j in jobs)
    finally:
        db.close()


def test_speaker_zero_P_reverses_mapping(client, monkeypatch):
    monkeypatch.setattr("psyapp.routes.get_asr_provider", lambda s: FakeASR())
    monkeypatch.setattr(
        "psyapp.routes.get_llm_provider", lambda s: FakeCleanLLM()
    )

    resp = client.post(
        "/sessions",
        files={"file": ("x.wav", b"fake", "audio/wav")},
        data={"speaker_zero": "P"},
    )
    session_id = resp.json()["data"]["session_id"]
    detail = client.get(f"/sessions/{session_id}").json()["data"]
    assert detail["segments"][0]["speaker"] == "P"
    assert detail["segments"][1]["speaker"] == "T"


def test_invalid_speaker_zero_rejected(client):
    resp = client.post(
        "/sessions",
        files={"file": ("x.wav", b"fake", "audio/wav")},
        data={"speaker_zero": "X"},
    )
    assert resp.status_code == 422
    assert resp.json()["ok"] is False
    assert resp.json()["error"]["code"] == "validation_error"


# ── 失败路径 ──────────────────────────────────────────────────


def test_upload_invalid_extension_rejected_unified_error(client):
    resp = client.post(
        "/sessions", files={"file": ("notes.txt", b"not audio", "text/plain")}
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "invalid_file_type"
    assert "message" in body["error"]


def test_upload_too_large_rejected_413(client, monkeypatch):
    monkeypatch.setattr(audio_mod, "MAX_AUDIO_BYTES", 8)
    resp = client.post(
        "/sessions", files={"file": ("big.wav", b"0123456789" * 2, "audio/wav")}
    )
    assert resp.status_code == 413
    body = resp.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "file_too_large"


def test_get_missing_session_404(client):
    resp = client.get("/sessions/99999")
    assert resp.status_code == 404
    body = resp.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "not_found"


def test_bad_record_json_retries_then_failed(client, monkeypatch):
    monkeypatch.setattr("psyapp.routes.get_asr_provider", lambda s: FakeASR())
    monkeypatch.setattr(
        "psyapp.routes.get_llm_provider",
        lambda s: FakeRecordLLM(["### not json at all", "still not json"]),
    )

    resp = client.post("/sessions", files={"file": ("x.wav", b"fake", "audio/wav")})
    session_id = resp.json()["data"]["session_id"]
    detail = client.get(f"/sessions/{session_id}").json()["data"]
    assert detail["status"] == SessionStatus.FAILED
    assert detail["record"] is None

    from psyapp.db import create_session_factory

    factory = create_session_factory(client.app.state.engine)
    db = factory()
    try:
        record_job = (
            db.query(Job)
            .filter(Job.session_id == session_id, Job.type == "record")
            .one()
        )
        assert record_job.status == "failed"
        assert "记录生成失败" in record_job.error
    finally:
        db.close()


def test_record_json_recovers_on_second_attempt(client, monkeypatch):
    monkeypatch.setattr("psyapp.routes.get_asr_provider", lambda s: FakeASR())
    monkeypatch.setattr(
        "psyapp.routes.get_llm_provider",
        lambda s: FakeRecordLLM(["garbage", GOOD_RECORD]),
    )

    resp = client.post("/sessions", files={"file": ("x.wav", b"fake", "audio/wav")})
    session_id = resp.json()["data"]["session_id"]
    detail = client.get(f"/sessions/{session_id}").json()["data"]
    assert detail["status"] == SessionStatus.DONE
    assert detail["record"]["summary"]


def test_session_list_returns_dev_sessions(client, monkeypatch):
    monkeypatch.setattr("psyapp.routes.get_asr_provider", lambda s: FakeASR())
    llms = iter([FakeCleanLLM(), FakeRecordLLM([GOOD_RECORD])])
    monkeypatch.setattr("psyapp.routes.get_llm_provider", lambda s: next(llms))
    client.post("/sessions", files={"file": ("a.wav", b"fake", "audio/wav")})

    resp = client.get("/sessions")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["sessions"]) == 1
    assert data["sessions"][0]["status"] == SessionStatus.DONE
    assert "session_id" in data["sessions"][0]


def test_pipeline_transition_marks_transcribing_then_done(client, monkeypatch):
    """直接驱动 pipeline，验证状态机 uploading → transcribing → done。"""
    from psyapp.db import create_session_factory
    from psyapp.models import Session as SessionModel
    from psyapp.services import run_background_pipeline

    factory = create_session_factory(client.app.state.engine)
    db = factory()
    session = SessionModel(
        user_id=1,
        mode="in_person",
        status=SessionStatus.UPLOADING,
        audio_path="data/audio/fake.wav",
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    class ProbeASR(FakeASR):
        captured_status: str | None = None

        def transcribe(self, audio_path, *, speaker_hint=None):
            # 后台任务已把状态置为 transcribing 后才真正转写
            probe_db = factory()
            try:
                ProbeASR.captured_status = probe_db.get(
                    SessionModel, session.id
                ).status
            finally:
                probe_db.close()
            return super().transcribe(audio_path, speaker_hint=speaker_hint)

    run_background_pipeline(
        session.id,
        factory,
        client.app.state.settings,
        "data/audio/fake.wav",
        "T",
        ProbeASR(),
        FakeCleanLLM(),
        FakeRecordLLM([GOOD_RECORD]),
    )
    db.close()

    assert ProbeASR.captured_status == SessionStatus.TRANSCRIBING
    db2 = factory()
    try:
        assert db2.get(SessionModel, session.id).status == SessionStatus.DONE
    finally:
        db2.close()
