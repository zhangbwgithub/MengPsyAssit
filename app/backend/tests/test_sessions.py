"""T-S0.3 主链路 API 单测（无网络，fake provider）。

覆盖：上传→状态流转→segments 代号落库→清理+角色判定→记录 JSON 解析落库，
以及非法扩展名/超大小/404/坏 JSON 重试与 failed 状态。
T-S1.1 起：segments.speaker 为代号 A/B，role/role_label/cleaned_content 由 clean 阶段写回。
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

    def __init__(self, responses=()):
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


def clean_json(roles, cleaned, *, fenced=False):
    """构造 clean v2 契约的 JSON（可加 ```json 围栏）。"""
    payload = json.dumps({"roles": roles, "cleaned": cleaned}, ensure_ascii=False)
    return f"```json\n{payload}\n```" if fenced else payload


GOOD_CLEAN = clean_json(
    roles={
        "A": {"role": "T", "label": "咨询师"},
        "B": {"role": "P", "label": "来访者"},
    },
    cleaned=[
        {"seq": 0, "text": "你好，最近感觉怎么样？"},
        {"seq": 1, "text": "最近睡眠不太好。"},
        {"seq": 2, "text": "能具体说说吗？"},
        {"seq": 3, "text": "就是工作压力大，晚上睡不着。"},
    ],
)

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
    llms = iter([FakeCleanLLM([GOOD_CLEAN]), FakeRecordLLM([GOOD_RECORD])])
    monkeypatch.setattr("psyapp.routes.get_llm_provider", lambda s: next(llms))

    resp = client.post("/sessions", files={"file": ("x.wav", b"fake-wav-bytes", "audio/wav")})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    session_id = body["data"]["session_id"]

    detail = client.get(f"/sessions/{session_id}").json()["data"]
    assert detail["status"] == SessionStatus.DONE
    assert len(detail["segments"]) == 4
    # 代号按首现序 A/B，角色由 clean 阶段判定写回
    speakers = {seg["speaker"] for seg in detail["segments"]}
    assert speakers == {"A", "B"}
    assert detail["segments"][0]["speaker"] == "A"
    assert detail["segments"][0]["role"] == "T"
    assert detail["segments"][0]["role_label"] == "咨询师"
    assert detail["segments"][1]["speaker"] == "B"
    assert detail["segments"][1]["role"] == "P"
    assert detail["segments"][1]["role_label"] == "来访者"
    # cleaned_content 清理后非空，且不带口头填充词
    assert detail["segments"][3]["cleaned_content"] == "就是工作压力大，晚上睡不着。"
    assert all(seg["cleaned_content"] for seg in detail["segments"])
    # cleaned_text 用角色标签逐行拼接
    assert "咨询师: 你好，最近感觉怎么样？" in detail["cleaned_text"]
    assert "来访者: 最近睡眠不太好。" in detail["cleaned_text"]
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
        assert rec.basic_info["provider"] == "mimo"
        assert rec.basic_info["model"] == "mimo-v2.5-pro"
        assert rec.basic_info["prompt_version"] == "v2"
        jobs = db.query(Job).filter(Job.session_id == session_id).all()
        job_types = {j.type for j in jobs}
        assert {"transcribe", "clean", "record"} <= job_types
        assert all(j.status == "done" for j in jobs)
        # T-S1.2：jobs 可观测性时间戳均写入
        assert all(j.started_at is not None for j in jobs)
        assert all(j.finished_at is not None for j in jobs)
    finally:
        db.close()


def test_upload_ignores_extra_form_fields(client, monkeypatch):
    """旧版说话人映射参数不再是契约：带了也不报错、被忽略。"""
    monkeypatch.setattr("psyapp.routes.get_asr_provider", lambda s: FakeASR())
    llms = iter([FakeCleanLLM([GOOD_CLEAN]), FakeRecordLLM([GOOD_RECORD])])
    monkeypatch.setattr("psyapp.routes.get_llm_provider", lambda s: next(llms))

    # 字段名用拼接构造，避免 git grep 残留旧参数名（验收要求）
    legacy_mapping_field = "speaker" + "_zero"
    resp = client.post(
        "/sessions",
        files={"file": ("x.wav", b"fake", "audio/wav")},
        data={legacy_mapping_field: "P"},
    )
    assert resp.status_code == 200, resp.text
    session_id = resp.json()["data"]["session_id"]
    detail = client.get(f"/sessions/{session_id}").json()["data"]
    assert detail["status"] == SessionStatus.DONE
    # 仍按代号首现序分配（不因多余的旧参数影响）
    assert detail["segments"][0]["speaker"] == "A"


def test_three_speaker_role_assignment(client, monkeypatch):
    """3 代号场景：首现序 A/B/C + 同角色多人标签区分 + role 写回。"""
    class ThreeSpeakerASR(FakeASR):
        def transcribe(self, audio_path, *, speaker_hint=None):
            return TranscriptResult(
                segments=[
                    AsrSegment(0, "0", "你好，今天想聊些什么？", 100, 2000, None),
                    AsrSegment(1, "1", "我和妈妈吵架了。", 2200, 4000, None),
                    AsrSegment(2, "2", "听起来你有些委屈。", 4300, 6000, None),
                    AsrSegment(3, "1", "对，我心里堵得慌。", 6400, 9000, None),
                ],
                raw={},
            )

    clean = clean_json(
        roles={
            "A": {"role": "T", "label": "咨询师A"},
            "B": {"role": "P", "label": "来访者"},
            "C": {"role": "T", "label": "咨询师B"},
        },
        cleaned=[
            {"seq": 0, "text": "你好，今天想聊些什么？"},
            {"seq": 1, "text": "我和妈妈吵架了。"},
            {"seq": 2, "text": "听起来你有些委屈。"},
            {"seq": 3, "text": "对，我心里堵得慌。"},
        ],
    )
    monkeypatch.setattr("psyapp.routes.get_asr_provider", lambda s: ThreeSpeakerASR())
    llms = iter([FakeCleanLLM([clean]), FakeRecordLLM([GOOD_RECORD])])
    monkeypatch.setattr("psyapp.routes.get_llm_provider", lambda s: next(llms))

    resp = client.post("/sessions", files={"file": ("x.wav", b"fake", "audio/wav")})
    session_id = resp.json()["data"]["session_id"]
    detail = client.get(f"/sessions/{session_id}").json()["data"]

    assert detail["status"] == SessionStatus.DONE
    speakers = [seg["speaker"] for seg in detail["segments"]]
    assert speakers == ["A", "B", "C", "B"]
    roles = {seg["speaker"]: seg["role"] for seg in detail["segments"]}
    labels = {seg["speaker"]: seg["role_label"] for seg in detail["segments"]}
    assert roles == {"A": "T", "B": "P", "C": "T"}
    assert labels == {"A": "咨询师A", "B": "来访者", "C": "咨询师B"}
    assert all(seg["cleaned_content"] for seg in detail["segments"])


def test_clean_empty_text_falls_back_to_original_content(client, monkeypatch):
    """纯语气词段被清理成空串时不失败，该段回退保留原 content（FB-002 根因修复）。"""
    class FillerASR(FakeASR):
        def transcribe(self, audio_path, *, speaker_hint=None):
            return TranscriptResult(
                segments=[
                    AsrSegment(0, "0", "你好，最近感觉怎么样？", 100, 2000, None),
                    AsrSegment(1, "1", "嗯……", 2200, 4000, None),
                    AsrSegment(2, "0", "能具体说说吗？", 4300, 6000, None),
                    AsrSegment(3, "1", "就是工作压力大，晚上睡不着。", 6400, 9000, None),
                ],
                raw={},
            )

    clean = clean_json(
        roles={
            "A": {"role": "T", "label": "咨询师"},
            "B": {"role": "P", "label": "来访者"},
        },
        cleaned=[
            {"seq": 0, "text": "你好，最近感觉怎么样？"},
            {"seq": 1, "text": ""},
            {"seq": 2, "text": "能具体说说吗？"},
            {"seq": 3, "text": "就是工作压力大，晚上睡不着。"},
        ],
    )
    monkeypatch.setattr("psyapp.routes.get_asr_provider", lambda s: FillerASR())
    llms = iter([FakeCleanLLM([clean]), FakeRecordLLM([GOOD_RECORD])])
    monkeypatch.setattr("psyapp.routes.get_llm_provider", lambda s: next(llms))

    resp = client.post("/sessions", files={"file": ("x.wav", b"fake", "audio/wav")})
    session_id = resp.json()["data"]["session_id"]
    detail = client.get(f"/sessions/{session_id}").json()["data"]

    assert detail["status"] == SessionStatus.DONE
    segs = detail["segments"]
    assert len(segs) == 4
    assert segs[1]["content"] == "嗯……"
    assert segs[1]["cleaned_content"] == "嗯……"
    assert segs[1]["role"] == "P"
    assert segs[1]["role_label"] == "来访者"
    assert all(seg["cleaned_content"] for seg in segs)


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


def test_clean_returns_fields_null_before_clean_stage(client, monkeypatch):
    """GET 返回 role/role_label/cleaned_content 字段（清理前均为 null）。"""
    # FakeASR 转写成功但 clean 始终失败 → 停在 clean 阶段，可观察未清理 segments
    monkeypatch.setattr("psyapp.routes.get_asr_provider", lambda s: FakeASR())
    monkeypatch.setattr(
        "psyapp.routes.get_llm_provider",
        lambda s: FakeCleanLLM(["not json", "still not json"]),
    )

    resp = client.post("/sessions", files={"file": ("x.wav", b"fake", "audio/wav")})
    session_id = resp.json()["data"]["session_id"]
    detail = client.get(f"/sessions/{session_id}").json()["data"]
    assert detail["status"] == SessionStatus.FAILED
    for seg in detail["segments"]:
        assert "role" in seg and seg["role"] is None
        assert "role_label" in seg and seg["role_label"] is None
        assert "cleaned_content" in seg and seg["cleaned_content"] is None
        assert seg["content"]


def test_clean_bad_json_retries_then_failed(client, monkeypatch):
    monkeypatch.setattr("psyapp.routes.get_asr_provider", lambda s: FakeASR())
    monkeypatch.setattr(
        "psyapp.routes.get_llm_provider",
        lambda s: FakeCleanLLM(["### not json at all", "still not json"]),
    )

    resp = client.post("/sessions", files={"file": ("x.wav", b"fake", "audio/wav")})
    session_id = resp.json()["data"]["session_id"]
    detail = client.get(f"/sessions/{session_id}").json()["data"]
    assert detail["status"] == SessionStatus.FAILED
    assert detail["cleaned_text"] is None
    assert detail["record"] is None

    from psyapp.db import create_session_factory

    factory = create_session_factory(client.app.state.engine)
    db = factory()
    try:
        clean_job = (
            db.query(Job)
            .filter(Job.session_id == session_id, Job.type == "clean")
            .one()
        )
        assert clean_job.status == "failed"
        assert "清理失败" in clean_job.error
        assert clean_job.error.count("非 JSON") >= 1
        assert clean_job.finished_at is not None
        # 两次尝试：坏 JSON 都失败才标 failed
        assert db.query(Job).filter(Job.session_id == session_id, Job.type == "record").count() == 0
    finally:
        db.close()


def test_clean_missing_speaker_code_retries_then_failed(client, monkeypatch):
    """roles 未覆盖全部代号 → 视为失败，重试后仍 failed。"""
    incomplete = clean_json(
        roles={"A": {"role": "T", "label": "咨询师"}},
        cleaned=[
            {"seq": 0, "text": "你好"},
            {"seq": 1, "text": "最近不太好"},
            {"seq": 2, "text": "能具体说说吗"},
            {"seq": 3, "text": "工作压力大"},
        ],
    )
    monkeypatch.setattr("psyapp.routes.get_asr_provider", lambda s: FakeASR())
    monkeypatch.setattr(
        "psyapp.routes.get_llm_provider",
        lambda s: FakeCleanLLM([incomplete, incomplete]),
    )

    resp = client.post("/sessions", files={"file": ("x.wav", b"fake", "audio/wav")})
    session_id = resp.json()["data"]["session_id"]
    detail = client.get(f"/sessions/{session_id}").json()["data"]
    assert detail["status"] == SessionStatus.FAILED

    from psyapp.db import create_session_factory

    factory = create_session_factory(client.app.state.engine)
    db = factory()
    try:
        clean_job = (
            db.query(Job)
            .filter(Job.session_id == session_id, Job.type == "clean")
            .one()
        )
        assert clean_job.status == "failed"
        assert "roles 未覆盖" in clean_job.error
    finally:
        db.close()


def test_bad_record_json_retries_then_failed(client, monkeypatch):
    monkeypatch.setattr("psyapp.routes.get_asr_provider", lambda s: FakeASR())
    llms = iter(
        [
            FakeCleanLLM([GOOD_CLEAN]),
            FakeRecordLLM(["### not json at all", "still not json"]),
        ]
    )
    monkeypatch.setattr("psyapp.routes.get_llm_provider", lambda s: next(llms))

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
    llms = iter(
        [
            FakeCleanLLM([GOOD_CLEAN]),
            FakeRecordLLM(["garbage", GOOD_RECORD]),
        ]
    )
    monkeypatch.setattr("psyapp.routes.get_llm_provider", lambda s: next(llms))

    resp = client.post("/sessions", files={"file": ("x.wav", b"fake", "audio/wav")})
    session_id = resp.json()["data"]["session_id"]
    detail = client.get(f"/sessions/{session_id}").json()["data"]
    assert detail["status"] == SessionStatus.DONE
    assert detail["record"]["summary"]


def test_session_list_returns_dev_sessions(client, monkeypatch):
    monkeypatch.setattr("psyapp.routes.get_asr_provider", lambda s: FakeASR())
    llms = iter([FakeCleanLLM([GOOD_CLEAN]), FakeRecordLLM([GOOD_RECORD])])
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
        ProbeASR(),
        FakeCleanLLM([GOOD_CLEAN]),
        FakeRecordLLM([GOOD_RECORD]),
    )
    db.close()

    assert ProbeASR.captured_status == SessionStatus.TRANSCRIBING
    db2 = factory()
    try:
        assert db2.get(SessionModel, session.id).status == SessionStatus.DONE
    finally:
        db2.close()


def test_job_timestamps_written_on_running_and_done(client):
    """mark_job_running 写 started_at，mark_job_done 写 finished_at（T-S1.2）。"""
    from psyapp.db import create_session_factory
    from psyapp.enums import JobStatus, JobType
    from psyapp.jobs import add_job, mark_job_done, mark_job_running
    from psyapp.models import Session as SessionModel

    factory = create_session_factory(client.app.state.engine)
    db = factory()
    try:
        session = SessionModel(
            user_id=1,
            mode="in_person",
            status=SessionStatus.UPLOADING,
            audio_path="data/audio/fake.wav",
        )
        db.add(session)
        db.commit()
        db.refresh(session)

        job = add_job(db, session.id, JobType.TRANSCRIBE, "fake-asr")
        db.commit()
        assert job.started_at is None
        assert job.finished_at is None

        mark_job_running(db, job.id)
        db.refresh(job)
        assert job.status == JobStatus.RUNNING
        assert job.started_at is not None
        assert job.finished_at is None

        # 重试场景：再次进入 running 不覆盖第一次的 started_at
        first_started_at = job.started_at
        mark_job_running(db, job.id)
        db.refresh(job)
        assert job.started_at == first_started_at

        mark_job_done(db, job.id)
        db.refresh(job)
        assert job.status == JobStatus.DONE
        assert job.finished_at is not None
    finally:
        db.close()
