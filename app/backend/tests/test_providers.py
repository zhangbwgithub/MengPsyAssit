"""Provider 层单元测试（无网络）：工厂选择 + paraformer 响应解析 + LLM 消息组装。"""

import pytest

from psyapp.config import Settings
from psyapp.providers import (
    ASRProvider,
    DashScopeParaformer,
    DeepseekLLM,
    LLMProvider,
    MimoLLM,
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
        "xiaomi_cn_api_key": "test-key",
        "deepseek_api_key": "test-key",
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


def test_factory_defaults_select_paraformer_and_mimo(tmp_path):
    """T-S0.6：LLM 默认从 qwen 切换为 mimo（mimo-v2.5-pro）。"""
    settings = _settings(tmp_path)
    asr = get_asr_provider(settings)
    llm = get_llm_provider(settings)
    assert isinstance(asr, ASRProvider) and isinstance(asr, DashScopeParaformer)
    assert isinstance(llm, LLMProvider) and isinstance(llm, MimoLLM)
    assert asr.name == "paraformer"
    assert llm.name == "mimo"
    assert settings.llm_provider == "mimo"
    assert settings.llm_model == "mimo-v2.5-pro"


def test_factory_select_deepseek_and_qwen(tmp_path):
    """llm_provider=deepseek / qwen 各选出对应实现；llm_model 留空时跟随 provider 默认。"""
    ds = _settings(tmp_path, llm_provider="deepseek")
    llm = get_llm_provider(ds)
    assert isinstance(llm, DeepseekLLM) and llm.name == "deepseek"
    assert ds.llm_model == "deepseek-v4-flash"

    qw = _settings(tmp_path, llm_provider="qwen")
    llm = get_llm_provider(qw)
    assert isinstance(llm, QwenLLM) and llm.name == "qwen"
    assert qw.llm_model == "qwen-max"


def test_factory_explicit_llm_model_overrides_default(tmp_path):
    """显式 LLM_MODEL 覆盖 provider 默认模型。"""
    settings = _settings(tmp_path, llm_provider="qwen", llm_model="qwen-plus")
    assert settings.llm_model == "qwen-plus"


def test_factory_unknown_asr_provider_raises(tmp_path):
    settings = _settings(tmp_path, asr_provider="xxx")
    with pytest.raises(ValueError, match="asr_provider"):
        get_asr_provider(settings)


def test_factory_unknown_llm_provider_raises(tmp_path):
    settings = _settings(tmp_path, llm_provider="xxx")
    with pytest.raises(ValueError, match="llm_provider"):
        get_llm_provider(settings)


def test_factory_empty_api_key_raises(tmp_path):
    settings = _settings(tmp_path, dashscope_api_key="")
    with pytest.raises(ProviderError, match="dashscope_api_key"):
        get_asr_provider(settings)
    with pytest.raises(ProviderError, match="dashscope_api_key"):
        get_llm_provider(_settings(tmp_path, llm_provider="qwen", dashscope_api_key=""))


def test_factory_mimo_missing_key_raises_with_env_name(tmp_path):
    """mimo 无 key：抛 ProviderError，错误信息含环境变量名 XIAOMI_CN_API_KEY。"""
    settings = _settings(tmp_path, xiaomi_cn_api_key="")
    with pytest.raises(ProviderError, match="XIAOMI_CN_API_KEY"):
        get_llm_provider(settings)


def test_factory_deepseek_missing_key_raises_with_env_name(tmp_path):
    settings = _settings(tmp_path, llm_provider="deepseek", deepseek_api_key="")
    with pytest.raises(ProviderError, match="DEEPSEEK_API_KEY"):
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
