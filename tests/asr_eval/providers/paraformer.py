"""候选 1：paraformer-v2 录音文件识别（异步任务，支持说话人分离）。

两种实现路径：
- SDK 路径：dashscope.audio.asr.Transcription
- HTTP 路径：urllib.request 直接调 REST API

关键约束：file_urls 必须是公网可访问 URL，不支持本地文件。
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from . import ASRResult, get_api_key, timed_call

# ── 模型常量 ────────────────────────────────────────────────────
MODEL_NAME = "paraformer-v2"
_API_BASE = "https://dashscope.aliyuncs.com/api/v1"


# ═══════════════════════════════════════════════════════════════
# SDK 路径
# ═══════════════════════════════════════════════════════════════


def _run_via_sdk(
    file_url: str,
    api_key: str,
    *,
    language_hints: list[str] | None = None,
    speaker_count: int = 2,
    poll_interval: float = 3.0,
    max_wait: float = 300.0,
) -> ASRResult:
    """通过 dashscope SDK 调用 paraformer-v2 录音文件识别。"""
    from dashscope.audio.asr import Transcription

    if language_hints is None:
        language_hints = ["zh", "en"]

    result = ASRResult(model=MODEL_NAME, audio=file_url)

    try:
        # 异步提交
        resp, latency = timed_call(
            Transcription.async_call,
            model=MODEL_NAME,
            file_urls=[file_url],
            language_hints=language_hints,
            diarization_enabled=True,
            speaker_count=speaker_count,
        )

        # 轮询等待
        poll_start = time.monotonic()
        while True:
            task_result = Transcription.wait(task=resp)
            status = task_result.output.get("task_status", "")
            if status in ("SUCCEEDED", "FAILED", "UNKNOWN"):
                break
            if time.monotonic() - poll_start > max_wait:
                result.status = "error"
                result.error = f"超时：等待 {max_wait}s 仍为 {status}"
                result.latency_s = time.monotonic() - (poll_start - latency)
                return result
            time.sleep(poll_interval)

        result.latency_s = time.monotonic() - (poll_start - latency)

        if status != "SUCCEEDED":
            result.status = "error"
            result.error = f"任务失败：{status} — {task_result.output}"
            return result

        # 下载 transcription_url 中的结果
        result = _fetch_transcription_results(task_result, result, file_url)

    except Exception as exc:
        result.status = "error"
        result.error = f"{type(exc).__name__}: {exc}"

    return result


def _fetch_transcription_results(
    task_result: Any, result: ASRResult, file_url: str
) -> ASRResult:
    """从 SDK 返回的任务结果中提取并解析转写内容。"""
    import urllib.request

    output = task_result.output
    results_list = output.get("results", [])

    for item in results_list:
        if item.get("transcription_url"):
            try:
                req = urllib.request.Request(item["transcription_url"])
                with urllib.request.urlopen(req, timeout=30) as resp:
                    transcript_json = json.loads(resp.read().decode("utf-8"))
                result = _parse_paraformer_transcript(transcript_json, result)
            except Exception as exc:
                result.status = "error"
                result.error = f"下载转写结果失败: {exc}"
        elif "transcripts" in item:
            # 有时结果直接嵌入
            result = _parse_paraformer_transcript(item, result)

    return result


# ═══════════════════════════════════════════════════════════════
# HTTP 路径（纯标准库）
# ═══════════════════════════════════════════════════════════════


def _run_via_http(
    file_url: str,
    api_key: str,
    *,
    language_hints: list[str] | None = None,
    speaker_count: int = 2,
    poll_interval: float = 3.0,
    max_wait: float = 300.0,
) -> ASRResult:
    """通过 urllib.request 调用 paraformer-v2 HTTP API。"""
    if language_hints is None:
        language_hints = ["zh", "en"]

    result = ASRResult(model=MODEL_NAME, audio=file_url)

    # 提交异步任务
    submit_body = json.dumps(
        {
            "model": MODEL_NAME,
            "input": {"file_urls": [file_url]},
            "parameters": {
                "diarization_enabled": True,
                "speaker_count": speaker_count,
                "language_hints": language_hints,
            },
        }
    ).encode("utf-8")

    submit_req = urllib.request.Request(
        f"{_API_BASE}/services/audio/asr/transcription",
        data=submit_body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",
        },
        method="POST",
    )

    try:
        t0 = time.monotonic()
        with urllib.request.urlopen(submit_req, timeout=30) as resp:
            submit_resp = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        result.status = "error"
        result.error = f"HTTP {exc.code}: {body}"
        result.latency_s = 0.0
        return result
    except Exception as exc:
        result.status = "error"
        result.error = f"{type(exc).__name__}: {exc}"
        result.latency_s = 0.0
        return result

    task_id = submit_resp.get("output", {}).get("task_id")
    if not task_id:
        result.status = "error"
        result.error = f"提交失败，无 task_id：{submit_resp}"
        result.latency_s = time.monotonic() - t0
        return result

    # 轮询
    poll_req = urllib.request.Request(
        f"{_API_BASE}/tasks/{task_id}",
        headers={"Authorization": f"Bearer {api_key}"},
    )

    while True:
        try:
            with urllib.request.urlopen(poll_req, timeout=15) as resp:
                poll_resp = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            result.status = "error"
            result.error = f"轮询失败: {exc}"
            result.latency_s = time.monotonic() - t0
            return result

        status = poll_resp.get("output", {}).get("task_status", "")
        if status in ("SUCCEEDED", "FAILED", "UNKNOWN"):
            break
        if time.monotonic() - t0 > max_wait:
            result.status = "error"
            result.error = f"超时：等待 {max_wait}s 仍为 {status}"
            result.latency_s = time.monotonic() - t0
            return result
        time.sleep(poll_interval)

    result.latency_s = time.monotonic() - t0

    if status != "SUCCEEDED":
        result.status = "error"
        result.error = f"任务失败：{status} — {poll_resp.get('output', {})}"
        return result

    # 解析转写结果
    results_list = poll_resp.get("output", {}).get("results", [])
    for item in results_list:
        if item.get("transcription_url"):
            try:
                req = urllib.request.Request(item["transcription_url"])
                with urllib.request.urlopen(req, timeout=30) as resp:
                    transcript_json = json.loads(resp.read().decode("utf-8"))
                result = _parse_paraformer_transcript(transcript_json, result)
            except Exception as exc:
                result.status = "error"
                result.error = f"下载转写结果失败: {exc}"
        elif "transcripts" in item:
            result = _parse_paraformer_transcript(item, result)

    return result


# ═══════════════════════════════════════════════════════════════
# 结果解析（SDK / HTTP 共用）
# ═══════════════════════════════════════════════════════════════


def _parse_paraformer_transcript(
    transcript_data: dict[str, Any], result: ASRResult
) -> ASRResult:
    """解析 paraformer-v2 的 transcription JSON。

    预期结构：
    {"transcripts": [{"sentences": [{"text": ..., "begin_time": ms, "end_time": ms, "speaker_id": int}, ...]}]}
    """
    transcripts = transcript_data.get("transcripts", [])
    all_sentences: list[dict[str, Any]] = []
    full_parts: list[str] = []

    for tr in transcripts:
        for sent in tr.get("sentences", []):
            text = sent.get("text", "")
            full_parts.append(text)
            all_sentences.append(
                {
                    "text": text,
                    "begin_ms": sent.get("begin_time"),
                    "end_ms": sent.get("end_time"),
                    "speaker_id": sent.get("speaker_id"),
                }
            )

    result.full_text = "".join(full_parts)
    result.sentences = all_sentences
    return result


# ═══════════════════════════════════════════════════════════════
# 公共入口
# ═══════════════════════════════════════════════════════════════


def transcribe(
    file_url: str,
    *,
    language_hints: list[str] | None = None,
    speaker_count: int = 2,
    poll_interval: float = 3.0,
    max_wait: float = 300.0,
    use_sdk: bool | None = None,
) -> ASRResult:
    """调用 paraformer-v2 转写音频。

    Args:
        file_url: 公网可访问的音频 URL
        language_hints: 语言提示，默认 ['zh', 'en']
        speaker_count: 说话人数量
        poll_interval: 轮询间隔秒数
        max_wait: 最大等待秒数
        use_sdk: None=自动检测, True=强制SDK, False=强制HTTP

    Returns:
        ASRResult 统一结果
    """
    api_key = get_api_key()

    if use_sdk is None:
        from . import check_sdk_available

        use_sdk = check_sdk_available()

    if use_sdk:
        return _run_via_sdk(
            file_url,
            api_key,
            language_hints=language_hints,
            speaker_count=speaker_count,
            poll_interval=poll_interval,
            max_wait=max_wait,
        )
    else:
        return _run_via_http(
            file_url,
            api_key,
            language_hints=language_hints,
            speaker_count=speaker_count,
            poll_interval=poll_interval,
            max_wait=max_wait,
        )
