"""AI Provider 抽象层：接口一次定型（方案文档 §4）。

- ASR / LLM 均通过统一接口调用，实现可配置可替换。
- provider 只吐说话人编号（"0"/"1"/…），"谁是咨询师" 的映射是上层业务，不在本层做。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class ProviderError(RuntimeError):
    """Provider 调用失败（网络/上传/任务失败等），message 含可读错误信息。"""


@dataclass
class Segment:
    """一段转写：说话人编号 + 文本 + 时间区间。"""

    seq: int
    speaker: str  # 说话人编号字符串，如 "0"/"1"；"谁是 T" 的映射交给上层
    text: str
    start_ms: int | None = None
    end_ms: int | None = None
    confidence: float | None = None


@dataclass
class TranscriptResult:
    """ASR 统一结果：segments + 原始 API 响应（供追溯）。"""

    segments: list[Segment] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


class ASRProvider(ABC):
    """语音识别 provider 统一接口。"""

    name: str

    @abstractmethod
    def transcribe(self, audio_path: str, *, speaker_hint: int | None = 2) -> TranscriptResult:
        """转写本地音频文件。speaker_hint 为说话人数量提示（None=不提示）。"""
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """最小代价探测 provider 可用性。"""
        ...


class LLMProvider(ABC):
    """大语言模型 provider 统一接口。"""

    name: str

    @abstractmethod
    def complete(
        self,
        messages: list[dict],
        *,
        schema_hint: str | None = None,
        temperature: float = 0.3,
    ) -> str:
        """对话补全，返回文本内容。schema_hint 非空时提示模型按结构输出。"""
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """最小代价探测 provider 可用性。"""
        ...
