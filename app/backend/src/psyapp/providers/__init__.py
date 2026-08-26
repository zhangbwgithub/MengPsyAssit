"""AI Provider 包：抽象接口 + 工厂。

按 Settings 字段选择实现；未知值抛清晰错误。
S0 只实现各一个：ASR=paraformer-v2，LLM=qwen（DashScope）。
"""

from __future__ import annotations

from ..config import Settings
from .base import ASRProvider, LLMProvider, ProviderError, Segment, TranscriptResult
from .paraformer import DashScopeParaformer
from .qwen import QwenLLM

__all__ = [
    "ASRProvider",
    "DashScopeParaformer",
    "LLMProvider",
    "ProviderError",
    "QwenLLM",
    "Segment",
    "TranscriptResult",
    "get_asr_provider",
    "get_llm_provider",
]


def get_asr_provider(settings: Settings) -> ASRProvider:
    """按 settings.asr_provider 选择 ASR 实现。"""
    name = settings.asr_provider
    if name == "paraformer":
        return DashScopeParaformer(api_key=settings.dashscope_api_key)
    raise ValueError(f"未知的 asr_provider: {name!r}（S0 可用值: 'paraformer'）")


def get_llm_provider(settings: Settings) -> LLMProvider:
    """按 settings.llm_provider 选择 LLM 实现。"""
    name = settings.llm_provider
    if name == "qwen":
        return QwenLLM(api_key=settings.dashscope_api_key, model=settings.llm_model)
    raise ValueError(f"未知的 llm_provider: {name!r}（S0 可用值: 'qwen'）")
