"""Provider 层单元测试（无网络）：工厂选择 + paraformer 响应解析 + qwen 消息组装。"""

import pytest

from psyapp.config import Settings
from psyapp.providers import (
    ASRProvider,
    DashScopeParaformer,
    LLMProvider,
    ProviderError,
    QwenLLM,
    get_asr_provider,
    get_llm_provider,
)
from psyapp.providers.paraformer import parse_transcript


def _settings(tmp_path, **overrides) -> Settings:
    kwargs = {
        "database_url": f"sqlite:///{tmp_path / 'test.db'}",
        "data_dir": str(tmp_path),
        "dashscope_api_key": "test-key",
    }
    kwargs.update(overrides)
    return Settings(**kwargs)


# ── 仿真 paraformer transcription JSON（结构照真实响应）──────────

FAKE_TRANSCRIPT = {
    "transcripts": [
        {
            "sentences": [
                {"text": "你好，最近感觉怎么样？", "begin_time": 120, "end_time": 2100, "speaker_id": 0},
                {"text": "最近睡眠不太好。", "begin_time": 2400, "end_time": 3900, "speaker_id": 1},
                {"text": "能具体说说吗？", "begin_time": 4200, "end_time": 5500, "speaker_id": 0},
            ],
            "channel_id": 0,
        }
    ],
    "task_id": "fake-task-id",
}


# ── 工厂 ────────────────────────────────────────────────────────


def test_factory_defaults_select_paraformer_and_qwen(tmp_path):
    settings = _settings(tmp_path)
    asr = get_asr_provider(settings)
    llm = get_llm_provider(settings)
    assert isinstance(asr, ASRProvider) and isinstance(asr, DashScopeParaformer)
    assert isinstance(llm, LLMProvider) and isinstance(llm, QwenLLM)
    assert asr.name == "paraformer"
    assert llm.name == "qwen"


def test_factory_unknown_asr_provider_raises(tmp_path):
    settings = _settings(tmp_path, asr_provider="xxx")
    with pytest.raises(ValueError, match="asr_provider"):
        get_asr_provider(settings)


def test_factory_unknown_llm_provider_raises(tmp_path):
    settings = _settings(tmp_path, llm_provider="deepseek")
    with pytest.raises(ValueError, match="llm_provider"):
        get_llm_provider(settings)


def test_factory_empty_api_key_raises(tmp_path):
    settings = _settings(tmp_path, dashscope_api_key="")
    with pytest.raises(ProviderError, match="dashscope_api_key"):
        get_asr_provider(settings)
    with pytest.raises(ProviderError, match="dashscope_api_key"):
        get_llm_provider(settings)


# ── paraformer 响应解析 ─────────────────────────────────────────


def test_parse_transcript_segments_fields():
    result = parse_transcript(FAKE_TRANSCRIPT)
    assert len(result.segments) == 3

    seg0 = result.segments[0]
    assert seg0.seq == 0
    assert seg0.speaker == "0"  # 编号字符串化，"谁是 T" 不在本层
    assert seg0.text == "你好，最近感觉怎么样？"
    assert seg0.start_ms == 120
    assert seg0.end_ms == 2100
    assert seg0.confidence is None

    assert result.segments[1].speaker == "1"
    assert result.segments[2].seq == 2
    assert result.raw is FAKE_TRANSCRIPT


def test_parse_transcript_empty_transcripts():
    result = parse_transcript({"transcripts": []})
    assert result.segments == []
    result2 = parse_transcript({})
    assert result2.segments == []


# ── qwen 消息组装（schema_hint）────────────────────────────────


def test_qwen_build_messages_without_hint():
    msgs = [{"role": "user", "content": "你好"}]
    assert QwenLLM.build_messages(msgs, None) == msgs


def test_qwen_build_messages_with_hint():
    msgs = [{"role": "user", "content": "你好"}]
    built = QwenLLM.build_messages(msgs, "输出 JSON：{summary: str}")
    assert built[0]["role"] == "system"
    assert "输出 JSON" in built[0]["content"]
    assert built[1] == msgs[0]


def test_qwen_build_messages_hint_merges_existing_system():
    msgs = [
        {"role": "system", "content": "你是助手"},
        {"role": "user", "content": "你好"},
    ]
    built = QwenLLM.build_messages(msgs, "输出 JSON")
    assert len(built) == 2
    assert "你是助手" in built[0]["content"]
    assert "输出 JSON" in built[0]["content"]
