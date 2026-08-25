"""ASR Provider 接口层。

统一结果格式，供 run_eval.py 消费。
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
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


def _resolve_dashscope_cli() -> Path:
    """定位项目 venv 中的 dashscope CLI。

    优先使用与当前 Python 解释器同目录的 dashscope；若不存在，则沿当前文件
    向上查找 .venv/bin/dashscope（兼容 uv 直接调用系统解释器的情况）。
    """
    candidates: list[Path] = []

    # 1. 与 sys.executable 同目录（标准 venv 激活场景）
    candidates.append(Path(sys.executable).resolve().parent / "dashscope")

    # 2. 沿当前文件向上搜索 .venv/bin/dashscope
    here = Path(__file__).resolve().parent
    for parent in [here, *here.parents]:
        venv_bin = parent / ".venv" / "bin" / "dashscope"
        if venv_bin not in candidates:
            candidates.append(venv_bin)

    for cli in candidates:
        if cli.is_file():
            return cli

    searched = "\n".join(f"  - {c}" for c in candidates)
    raise RuntimeError(
        f"未找到 dashscope CLI。已搜索路径：\n{searched}\n"
        "请确认项目 venv 中存在 .venv/bin/dashscope。"
    )


# ── 音频上传到 DashScope OSS（供需要 URL 的模型共用）─────────────

_OSS_UPLOAD_CACHE: dict[str, str] = {}


def upload_to_dashscope_oss(local_path: str, model: str = "paraformer-v2") -> str:
    """将本地音频文件上传到 DashScope 临时 OSS 并返回 oss:// URL。

    Args:
        local_path: 本地音频文件路径
        model: 用于上传命令的 --model 参数，默认 paraformer-v2

    Returns:
        oss:// 开头的临时 URL

    Raises:
        RuntimeError: 上传失败或解析不到 OSS URL
    """
    local_path = os.path.abspath(local_path)

    # 已是 OSS URL 直接返回
    if local_path.startswith("oss://"):
        return local_path

    if local_path in _OSS_UPLOAD_CACHE:
        return _OSS_UPLOAD_CACHE[local_path]

    dashscope_cli = _resolve_dashscope_cli()

    try:
        proc = subprocess.run(
            [str(dashscope_cli), "oss.upload", "--model", model, "--file", local_path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"上传超时（120s）: {local_path}") from exc
    except Exception as exc:
        raise RuntimeError(f"上传进程异常: {type(exc).__name__}: {exc}") from exc

    if proc.returncode != 0:
        err = proc.stderr.strip() or proc.stdout.strip() or "(无输出)"
        raise RuntimeError(f"dashscope oss.upload 失败（rc={proc.returncode}）: {err}")

    # 解析输出中的 oss:// URL
    output = proc.stdout.strip()
    match = re.search(r"oss://\S+", output)
    if not match:
        raise RuntimeError(
            f"未能从上传输出解析 OSS URL。输出内容：\n{output}"
        )

    oss_url = match.group(0)
    _OSS_UPLOAD_CACHE[local_path] = oss_url
    return oss_url
