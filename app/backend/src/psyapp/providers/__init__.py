"""AI Provider 包：抽象接口 + 工厂。

按 Settings 字段选择实现；未知值抛清晰错误。
ASR=paraformer-v2；LLM=mimo（默认，T-S0.6 陛下拍板）/ deepseek / qwen 三选一。
"""

from __future__ import annotations

from ..config import Settings
from .base import ASRProvider, LLMProvider, ProviderError, Segment, TranscriptResult
from .deepseek import DeepseekLLM
from .mimo import MimoLLM
from .paraformer import DashScopeParaformer
from .qwen import QwenLLM

__all__ = [
    "ASRProvider",
    "DashScopeParaformer",
    "DeepseekLLM",
    "LLMProvider",
    "MimoLLM",
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
    """按 settings.llm_provider 选择 LLM 实现（mimo / deepseek / qwen）。"""
    name = settings.llm_provider
    if name == "mimo":
        return MimoLLM(api_key=settings.xiaomi_cn_api_key, model=settings.llm_model)
    if name == "deepseek":
        return DeepseekLLM(api_key=settings.deepseek_api_key, model=settings.llm_model)
    if name == "qwen":
        return QwenLLM(api_key=settings.dashscope_api_key, model=settings.llm_model)
    raise ValueError(f"未知的 llm_provider: {name!r}（可用值: 'mimo' / 'deepseek' / 'qwen'）")
