"""ASR Provider 接口层。

统一结果格式，供 run_eval.py 消费。
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Sentence:
    """一句话的转写结果。"""

    text: str
    begin_ms: float | None = None
    end_ms: float | None = None
    speaker_id: int | str | None = None


@dataclass
class ASRResult:
    """统一的 ASR 结果记录。"""

    model: str
    audio: str
    status: str = "ok"  # "ok" | "error"
    latency_s: float | None = None
    full_text: str = ""
    sentences: list[dict[str, Any]] = field(default_factory=list)
    cer: float | None = None
    speaker_stats: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """转为可 JSON 序列化的字典。"""
        return {
            "model": self.model,
            "audio": self.audio,
            "status": self.status,
            "latency_s": self.latency_s,
            "full_text": self.full_text,
            "sentences": self.sentences,
            "cer": self.cer,
            "speaker_stats": self.speaker_stats,
            "error": self.error,
        }


def get_api_key() -> str:
    """从环境变量读取 DASHSCOPE_API_KEY，缺失时退出码 2。"""
    key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    if not key:
        print(
            "错误：环境变量 DASHSCOPE_API_KEY 未设置或为空。\n"
            "请先设置：export DASHSCOPE_API_KEY='sk-...'",
            file=sys.stderr,
        )
        sys.exit(2)
    return key


def check_sdk_available() -> bool:
    """检测 dashscope SDK 是否可导入。"""
    try:
        import dashscope  # noqa: F401

        return True
    except ImportError:
        return False


def timed_call(fn, *args, **kwargs) -> tuple[Any, float]:
    """执行函数并返回 (结果, 耗时秒)。"""
    start = time.monotonic()
    result = fn(*args, **kwargs)
    elapsed = time.monotonic() - start
    return result, elapsed
