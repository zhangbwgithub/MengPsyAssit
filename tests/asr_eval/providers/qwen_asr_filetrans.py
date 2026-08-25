"""候选 3：qwen3-asr-flash-filetrans（长音频文件转写，异步任务）。

两种实现路径：
- SDK 路径：dashscope.audio.asr.Transcription
- HTTP 路径：urllib.request 直接调 REST API

关键特征：
- 支持长音频（项目需求：180 分钟录音）
- 支持句级时间戳，不支持说话人分离
- 输入必须是 DashScope OSS URL（本地文件需先上传）
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from . import ASRResult, get_api_key, timed_call

# ── 模型常量 ────────────────────────────────────────────────────
MODEL_NAME = "qwen3-asr-flash-filetrans"
_API_BASE = "https://dashscope.aliyuncs.com/api/v1"


# ═══════════════════════════════════════════════════════════════
# SDK 路径
# ═══════════════════════════════════════════════════════════════


def _run_via_sdk(
    file_url: str,
    api_key: str,
    *,
    language: str = "zh",
    poll_interval: float = 3.0,
    max_wait: float = 600.0,
) -> ASRResult:
    """通过 dashscope SDK 调用 qwen3-asr-flash-filetrans。"""
    from dashscope.audio.asr import Transcription

    result = ASRResult(model=MODEL_NAME, audio=file_url)

    try:
        # 异步提交（SDK 参数仍使用 file_urls 数组）
        resp, latency = timed_call(
            Transcription.async_call,
            model=MODEL_NAME,
            file_urls=[file_url],
            language=language,
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


# ═══════════════════════════════════════════════════════════════
# HTTP 路径（纯标准库）
# ═══════════════════════════════════════════════════════════════


def _run_via_http(
    file_url: str,
    api_key: str,
    *,
    language: str = "zh",
    poll_interval: float = 3.0,
    max_wait: float = 600.0,
) -> ASRResult:
    """通过 urllib.request 调用 qwen3-asr-flash-filetrans HTTP API。"""
    result = ASRResult(model=MODEL_NAME, audio=file_url)

    # 提交异步任务；注意 input 字段是 file_url（单数）
    submit_body = json.dumps(
        {
            "model": MODEL_NAME,
            "input": {"file_url": file_url},
            "parameters": {"language": language},
        }
    ).encode("utf-8")

    submit_req = urllib.request.Request(
        f"{_API_BASE}/services/audio/asr/transcription",
        data=submit_body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",
            # OSS URL 需要服务端解析
            "X-DashScope-OssResourceResolve": "enable",
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
    # qwen3-asr-flash-filetrans 的结果位于 output.result.transcription_url
    output = poll_resp.get("output", {})
    transcription_url = output.get("result", {}).get("transcription_url")
    if transcription_url:
        try:
            req = urllib.request.Request(transcription_url)
            with urllib.request.urlopen(req, timeout=30) as resp:
                transcript_json = json.loads(resp.read().decode("utf-8"))
            result = _parse_filetrans_transcript(transcript_json, result)
        except Exception as exc:
            result.status = "error"
            result.error = f"下载转写结果失败: {exc}"
    else:
        # 兼容可能的多 results 结构
        results_list = output.get("results", [])
        for item in results_list:
            if item.get("transcription_url"):
                try:
                    req = urllib.request.Request(item["transcription_url"])
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        transcript_json = json.loads(resp.read().decode("utf-8"))
                    result = _parse_filetrans_transcript(transcript_json, result)
                except Exception as exc:
                    result.status = "error"
                    result.error = f"下载转写结果失败: {exc}"
            elif "transcripts" in item:
                result = _parse_filetrans_transcript(item, result)

    return result


# ═══════════════════════════════════════════════════════════════
# 结果解析（SDK / HTTP 共用）
# ═══════════════════════════════════════════════════════════════


def _fetch_transcription_results(
    task_result: Any, result: ASRResult, file_url: str
) -> ASRResult:
    """从 SDK 返回的任务结果中提取并解析转写内容。"""
    output = task_result.output
    transcription_url = output.get("result", {}).get("transcription_url")
    if transcription_url:
        try:
            req = urllib.request.Request(transcription_url)
            with urllib.request.urlopen(req, timeout=30) as resp:
                transcript_json = json.loads(resp.read().decode("utf-8"))
            result = _parse_filetrans_transcript(transcript_json, result)
        except Exception as exc:
            result.status = "error"
            result.error = f"下载转写结果失败: {exc}"
        return result

    # 兼容可能的多 results 结构
    results_list = output.get("results", [])
    for item in results_list:
        if item.get("transcription_url"):
            try:
                req = urllib.request.Request(item["transcription_url"])
                with urllib.request.urlopen(req, timeout=30) as resp:
                    transcript_json = json.loads(resp.read().decode("utf-8"))
                result = _parse_filetrans_transcript(transcript_json, result)
            except Exception as exc:
                result.status = "error"
                result.error = f"下载转写结果失败: {exc}"
        elif "transcripts" in item:
            result = _parse_filetrans_transcript(item, result)

    return result


def _parse_filetrans_transcript(
    transcript_data: dict[str, Any], result: ASRResult
) -> ASRResult:
    """解析 qwen3-asr-flash-filetrans 的 transcription JSON。

    预期结构：
    {"transcripts": [{"sentences": [{"text": ..., "begin_time": ms, "end_time": ms}, ...]}]}
    注意：该模型不支持说话人分离，因此 sentences 中无 speaker_id。
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
                    # 官方模型页明确：不支持说话人分离
                    "speaker_id": None,
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
    language: str = "zh",
    poll_interval: float = 3.0,
    max_wait: float = 600.0,
    use_sdk: bool | None = None,
) -> ASRResult:
    """调用 qwen3-asr-flash-filetrans 转写音频。

    Args:
        file_url: DashScope OSS URL（本地文件需先通过 dashscope oss.upload 上传）
        language: 语言代码，默认 'zh'
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
            language=language,
            poll_interval=poll_interval,
            max_wait=max_wait,
        )
    else:
        return _run_via_http(
            file_url,
            api_key,
            language=language,
            poll_interval=poll_interval,
            max_wait=max_wait,
        )
