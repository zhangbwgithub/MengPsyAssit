"""候选 2：qwen3-asr-flash（同步，多模态 chat 风格）。

两种实现路径：
- SDK 路径：dashscope.MultiModalConversation.call（支持本地文件绝对路径）
- HTTP 路径：urllib.request + OpenAI 兼容风格（audio 需 base64 data URI）

关键特征：
- 返回整段纯文本，无句级时间戳、无说话人分离
- 限流 100 RPM
"""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request

from . import ASRResult, get_api_key, timed_call

# ── 模型常量 ────────────────────────────────────────────────────
MODEL_NAME = "qwen3-asr-flash"
_API_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"


# ═══════════════════════════════════════════════════════════════
# SDK 路径
# ═══════════════════════════════════════════════════════════════


def _run_via_sdk(audio_path: str, api_key: str) -> ASRResult:
    """通过 dashscope SDK 调用 qwen3-asr-flash。

    audio_path: 本地文件绝对路径 或 URL
    """
    from dashscope import MultiModalConversation

    result = ASRResult(model=MODEL_NAME, audio=audio_path)

    messages = [{"role": "user", "content": [{"audio": audio_path}]}]

    try:
        resp, latency = timed_call(
            MultiModalConversation.call,
            model=MODEL_NAME,
            messages=messages,
            result_format="message",
        )
        result.latency_s = latency

        # 检查错误
        if hasattr(resp, "status_code") and resp.status_code != 200:
            result.status = "error"
            result.error = f"HTTP {resp.status_code}: {getattr(resp, 'message', resp)}"
            return result

        if resp.output is None:
            result.status = "error"
            result.error = f"无输出：{resp}"
            return result

        # 提取纯文本
        choices = resp.output.get("choices", [])
        if choices:
            message = choices[0].get("message", {})
            content = message.get("content", [])
            # content 是列表，每个元素可能有 {"text": "..."} 或直接是文本
            text_parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and "text" in item:
                    text_parts.append(item["text"])
                elif isinstance(item, str):
                    text_parts.append(item)
            result.full_text = "".join(text_parts)
        else:
            # 某些版本可能直接返回 output.text
            result.full_text = getattr(resp.output, "text", "")

        # qwen3-asr-flash 无句级时间戳
        result.sentences = []

    except Exception as exc:
        result.status = "error"
        result.error = f"{type(exc).__name__}: {exc}"

    return result


# ═══════════════════════════════════════════════════════════════
# HTTP 路径（纯标准库）
# ═══════════════════════════════════════════════════════════════


def _file_to_base64_data_uri(audio_path: str) -> str:
    """将本地文件转为 data:audio/wav;base64,<data> 格式。"""
    with open(audio_path, "rb") as f:
        data = f.read()
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:audio/wav;base64,{b64}"


def _run_via_http(audio_path: str, api_key: str) -> ASRResult:
    """通过 urllib.request 调用 qwen3-asr-flash HTTP API。"""
    result = ASRResult(model=MODEL_NAME, audio=audio_path)

    # 处理 audio 输入：URL 直接用，本地文件转 base64
    if audio_path.startswith(("http://", "https://")):
        audio_input = audio_path
    elif os.path.isfile(audio_path):
        audio_input = _file_to_base64_data_uri(audio_path)
    else:
        result.status = "error"
        result.error = f"音频路径无效：{audio_path}"
        return result

    body = json.dumps(
        {
            "model": MODEL_NAME,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": {"data": audio_input},
                        }
                    ],
                }
            ],
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        f"{_API_BASE}/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        t0 = time.monotonic()
        with urllib.request.urlopen(req, timeout=120) as resp:
            resp_data = json.loads(resp.read().decode("utf-8"))
        result.latency_s = time.monotonic() - t0
    except urllib.error.HTTPError as exc:
        body_str = ""
        try:
            body_str = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        result.status = "error"
        result.error = f"HTTP {exc.code}: {body_str}"
        result.latency_s = 0.0
        return result
    except Exception as exc:
        result.status = "error"
        result.error = f"{type(exc).__name__}: {exc}"
        result.latency_s = 0.0
        return result

    # 解析响应
    try:
        choices = resp_data.get("choices", [])
        if choices:
            message = choices[0].get("message", {})
            content = message.get("content", "")
            if isinstance(content, str):
                result.full_text = content
            elif isinstance(content, list):
                text_parts = []
                for item in content:
                    if isinstance(item, dict) and "text" in item:
                        text_parts.append(item["text"])
                    elif isinstance(item, str):
                        text_parts.append(item)
                result.full_text = "".join(text_parts)
        # 无句级时间戳
        result.sentences = []
    except Exception as exc:
        result.status = "error"
        result.error = f"解析响应失败: {exc} — {resp_data}"

    return result


# ═══════════════════════════════════════════════════════════════
# 公共入口
# ═══════════════════════════════════════════════════════════════


def transcribe(
    audio_path: str,
    *,
    use_sdk: bool | None = None,
) -> ASRResult:
    """调用 qwen3-asr-flash 转写音频。

    Args:
        audio_path: 本地文件绝对路径 或 URL
        use_sdk: None=自动检测, True=强制SDK, False=强制HTTP

    Returns:
        ASRResult 统一结果
    """
    api_key = get_api_key()

    if use_sdk is None:
        from . import check_sdk_available

        use_sdk = check_sdk_available()

    if use_sdk:
        return _run_via_sdk(audio_path, api_key)
    else:
        return _run_via_http(audio_path, api_key)
