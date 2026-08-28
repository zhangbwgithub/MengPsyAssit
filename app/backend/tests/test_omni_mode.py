"""T-S1.6 双模式管线测试（无网络）：mode 默认/显式/非法、omni 解析、omni 重试失败。

omni provider 用 monkeypatch 假 provider，不真实调 API。
"""

from __future__ import annotations

import json

import httpx

from psyapp.enums import PipelineMode, SessionStatus
from psyapp.models import Job, Session
from psyapp.providers.omni import (
    OMNI_TRANSCRIBE_PROMPT,
    QwenOmniLLM,
    fix_role_flip_by_address,
    parse_omni_transcript,
)

GOOD_RECORD = json.dumps(
    {
        "summary": "来访者自述最近睡眠不好、工作压力大。",
        "counselor_work": "咨询师询问近况并追问细节。",
        "client_reported_topics": ["睡眠", "工作压力"],
    },
    ensure_ascii=False,
)

OMNI_RAW = (
    "1\t咨询师\t你好，最近感觉怎么样？\n"
    "2\t来访者\t最近睡眠不太好。\n"
    "\n"
    "3\t咨询师\t能具体说说吗？\n"
)


class FakeOmni:
    name = "qwen3.5-omni-plus"

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0
        self.last_prompt = None

    def transcribe_audio(self, audio_path, prompt):
        self.calls += 1
        self.last_prompt = prompt
        return self.responses[min(self.calls - 1, len(self.responses) - 1)]


class FakeRecordLLM:
    name = "deepseek"

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def complete(self, messages, *, schema_hint=None, temperature=0.3):
        self.calls += 1
        return self.responses[min(self.calls - 1, len(self.responses) - 1)]


# ── omni 输出解析 ────────────────────────────────────────────────


def test_parse_omni_transcript_tabs_roles_and_speaker_codes():
    segments = parse_omni_transcript(OMNI_RAW)

    assert len(segments) == 3
    assert [seg["seq"] for seg in segments] == [0, 1, 2]
    assert [seg["speaker"] for seg in segments] == ["A", "B", "A"]
    assert [seg["role"] for seg in segments] == ["T", "P", "T"]
    assert [seg["role_label"] for seg in segments] == ["咨询师", "来访者", "咨询师"]
    assert [seg["content"] for seg in segments] == [
        "你好，最近感觉怎么样？",
        "最近睡眠不太好。",
        "能具体说说吗？",
    ]
    assert all(seg["cleaned_content"] == seg["content"] for seg in segments)
    assert all(seg["start_ms"] is None and seg["end_ms"] is None for seg in segments)


def test_parse_omni_transcript_tolerates_colon_spaces_and_unknown_role():
    text = (
        "0 咨询师： 你好，最近怎么样？\n"
        "\n"
        "1 来访者：最近睡眠不好。\n"
        "\n"
        "2 老师 我们来聊聊。\n"
    )
    segments = parse_omni_transcript(text)

    assert len(segments) == 3
    assert [seg["role"] for seg in segments] == ["T", "P", "P"]
    # 未知角色归 P 兜底并保留原词为 role_label
    assert [seg["role_label"] for seg in segments] == ["咨询师", "来访者", "老师"]
    assert segments[0]["content"] == "你好，最近怎么样？"
    assert segments[1]["content"] == "最近睡眠不好。"
    assert segments[2]["content"] == "我们来聊聊。"


def test_parse_omni_transcript_skips_blank_and_unparseable_lines():
    text = "```text\n\n这是前言\n\n1\t咨询师\t你好。\n\n2 来访者 好的。\n"
    segments = parse_omni_transcript(text)

    assert len(segments) == 2
    assert [seg["speaker"] for seg in segments] == ["A", "B"]
    assert segments[0]["content"] == "你好。"


# ── 称呼语翻转校正（T-S1.8 确定性兜底）───────────────────────────────


def test_flip_address_triggers_reversal_when_therapist_round_addresses_teacher():
    """「咨询师」轮以「X老师，」开头称呼对方 → 全篇角色对调，speaker 代号也随校正后的角色分配。"""
    text = (
        "1\t咨询师\t雨生老师，你怎么从来都不休假\n"
        "2\t来访者\t工作安排比较满。\n"
        "3\t咨询师\t那你也要注意休息。\n"
    )
    segments = parse_omni_transcript(text)

    assert [seg["role"] for seg in segments] == ["P", "T", "P"]
    assert [seg["role_label"] for seg in segments] == ["来访者", "咨询师", "来访者"]
    assert [seg["speaker"] for seg in segments] == ["A", "B", "A"]


def test_no_flip_when_patient_addresses_therapist():
    """来访者称呼咨询师为老师是正常语态：规则不误触发，解析零变化。"""
    text = (
        "1\t咨询师\t你好，最近感觉怎么样？\n"
        "2\t来访者\t王老师，我最近睡不好。\n"
        "3\t咨询师\t能具体说说吗？\n"
    )
    segments = parse_omni_transcript(text)

    assert [seg["role"] for seg in segments] == ["T", "P", "T"]
    assert [seg["role_label"] for seg in segments] == ["咨询师", "来访者", "咨询师"]
    assert [seg["speaker"] for seg in segments] == ["A", "B", "A"]


def test_no_flip_when_teacher_mentioned_but_not_addressed():
    """正文提及「老师」但不在句首称呼位：不触发，零变化。"""
    text = (
        "1\t咨询师\t你刚才提到老师说的那句话\n"
        "2\t来访者\t是的。\n"
    )
    segments = parse_omni_transcript(text)

    assert [seg["role"] for seg in segments] == ["T", "P"]
    assert [seg["role_label"] for seg in segments] == ["咨询师", "来访者"]
    assert [seg["speaker"] for seg in segments] == ["A", "B"]


def test_fix_role_flip_by_address_returns_same_list_when_no_trigger():
    turns = [("咨询师", "你好"), ("来访者", "老师，我最近睡不好")]
    assert fix_role_flip_by_address(turns) == turns


# ── 路由：mode 契约 ──────────────────────────────────────────────


def test_upload_defaults_to_omni_and_returns_mode_display(client, monkeypatch):
    fake_omni = FakeOmni([OMNI_RAW])
    monkeypatch.setattr("psyapp.routes.QwenOmniLLM", lambda api_key: fake_omni)
    monkeypatch.setattr(
        "psyapp.routes.get_llm_provider", lambda s: FakeRecordLLM([GOOD_RECORD])
    )

    resp = client.post("/sessions", files={"file": ("x.wav", b"fake", "audio/wav")})
    assert resp.status_code == 200, resp.text
    session_id = resp.json()["data"]["session_id"]

    detail = client.get(f"/sessions/{session_id}").json()["data"]
    assert detail["status"] == SessionStatus.DONE
    assert detail["pipeline_mode"] == PipelineMode.OMNI
    assert detail["model_display"] == "qwen3.5-omni-plus"
    assert len(detail["segments"]) == 3
    assert detail["segments"][0]["role"] == "T"
    assert detail["segments"][0]["role_label"] == "咨询师"
    assert detail["segments"][0]["start_ms"] is None
    assert detail["segments"][0]["end_ms"] is None
    assert detail["record"]["summary"] == "来访者自述最近睡眠不好、工作压力大。"

    from psyapp.db import create_session_factory

    factory = create_session_factory(client.app.state.engine)
    db = factory()
    try:
        session = db.get(Session, session_id)
        assert session.pipeline_mode == PipelineMode.OMNI
        assert session.raw_transcript == OMNI_RAW
        jobs = db.query(Job).filter(Job.session_id == session_id).all()
        assert {j.type for j in jobs} == {"transcribe", "record"}
        transcribe = next(j for j in jobs if j.type == "transcribe")
        assert transcribe.provider == "qwen3.5-omni-plus"
        assert transcribe.status == "done"
        # omni 无 clean 阶段：不建 clean job
        assert not any(j.type == "clean" for j in jobs)
    finally:
        db.close()


def test_upload_invalid_mode_rejected_400(client):
    resp = client.post(
        "/sessions",
        files={"file": ("x.wav", b"fake", "audio/wav")},
        data={"mode": "invalid"},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "validation_error"
    assert "mode" in body["error"]["message"]


def test_omni_zero_rounds_retries_then_failed(client, monkeypatch):
    fake_omni = FakeOmni(["不是轮次文本", "仍然不是轮次文本"])
    monkeypatch.setattr("psyapp.routes.QwenOmniLLM", lambda api_key: fake_omni)
    monkeypatch.setattr(
        "psyapp.routes.get_llm_provider", lambda s: FakeRecordLLM([GOOD_RECORD])
    )

    resp = client.post("/sessions", files={"file": ("x.wav", b"fake", "audio/wav")})
    assert resp.status_code == 200, resp.text
    session_id = resp.json()["data"]["session_id"]

    detail = client.get(f"/sessions/{session_id}").json()["data"]
    assert detail["status"] == SessionStatus.FAILED
    assert detail["record"] is None

    from psyapp.db import create_session_factory

    factory = create_session_factory(client.app.state.engine)
    db = factory()
    try:
        assert fake_omni.calls == 2
        session = db.get(Session, session_id)
        # 第二次尝试的原始输出仍保留为审计底稿
        assert session.raw_transcript == "仍然不是轮次文本"
        jobs = db.query(Job).filter(Job.session_id == session_id).all()
        assert {j.type for j in jobs} == {"transcribe"}
        transcribe = jobs[0]
        assert transcribe.status == "failed"
        assert transcribe.provider == "qwen3.5-omni-plus"
        assert "0 轮" in transcribe.error
    finally:
        db.close()


# ── QwenOmniLLM 请求结构（照探针，不发真实请求）─────────────────────


def test_qwen_omni_transcribe_audio_builds_probe_request(tmp_path):
    audio = tmp_path / "x.mp3"
    audio.write_bytes(b"fake-audio-bytes")
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "1\t咨询师\t你好"}}]},
        )

    provider = QwenOmniLLM(
        api_key="test-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    out = provider.transcribe_audio(str(audio), OMNI_TRANSCRIBE_PROMPT)

    assert out == "1\t咨询师\t你好"
    body = captured["body"]
    assert body["model"] == "qwen3.5-omni-plus"
    assert body["modalities"] == ["text"]
    assert body["enable_thinking"] is False
    assert body["temperature"] == 0.0
    content = body["messages"][0]["content"]
    assert content[0]["type"] == "input_audio"
    assert content[0]["input_audio"]["format"] == "mp3"
    assert content[0]["input_audio"]["data"].startswith("data:;base64,")
    assert content[1] == {"type": "text", "text": OMNI_TRANSCRIBE_PROMPT}


def test_qwen_omni_uses_audio_suffix_as_format(tmp_path):
    """探针用 mp3，但上传可能是 wav/m4a 等：format 跟随真实后缀，避免误标 mp3。"""
    audio = tmp_path / "x.wav"
    audio.write_bytes(b"fake-audio-bytes")

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        content = body["messages"][0]["content"]
        assert content[0]["input_audio"]["format"] == "wav"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "1\t咨询师\t你好"}}]},
        )

    provider = QwenOmniLLM(
        api_key="test-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert provider.transcribe_audio(str(audio), OMNI_TRANSCRIBE_PROMPT) == (
        "1\t咨询师\t你好"
    )
