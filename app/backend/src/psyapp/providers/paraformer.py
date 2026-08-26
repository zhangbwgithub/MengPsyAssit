"""paraformer-v2 录音文件识别（DashScope 异步任务，说话人分离）。

纯 HTTP 实现（httpx），不使用 dashscope SDK 做转写调用——P0 实测 SDK
传临时 URL 会报 SERVER_ERROR/InvalidParameter.MalformedURL；正确姿势是：
1. 本地文件用 `dashscope oss.upload` 子进程上传，拿到 oss:// URL
2. 提交异步任务时请求头带 `X-DashScope-OssResourceResolve: enable`
3. 轮询任务状态，下载 transcription_url 结果 JSON

参考实现：tests/asr_eval/providers/paraformer.py（P0 实测说话人分离 100% 全对）。
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from .base import ASRProvider, ProviderError, Segment, TranscriptResult

logger = logging.getLogger(__name__)

MODEL_NAME = "paraformer-v2"
_API_BASE = "https://dashscope.aliyuncs.com/api/v1"

_POLL_INTERVAL_S = 3.0
_POLL_TIMEOUT_S = 900.0  # 15 分钟
_UPLOAD_TIMEOUT_S = 120.0


def _resolve_dashscope_cli() -> Path:
    """定位 dashscope CLI：优先当前解释器所在 venv 的 bin 目录。"""
    candidates = [Path(sys.executable).resolve().parent / "dashscope"]
    for parent in [Path.cwd(), *Path.cwd().parents]:
        cli = parent / ".venv" / "bin" / "dashscope"
        if cli not in candidates:
            candidates.append(cli)
    for cli in candidates:
        if cli.is_file():
            return cli
    searched = "\n".join(f"  - {c}" for c in candidates)
    raise ProviderError(f"未找到 dashscope CLI。已搜索：\n{searched}")


def parse_transcript(transcript_data: dict[str, Any]) -> TranscriptResult:
    """解析 paraformer-v2 的 transcription JSON 为 TranscriptResult。

    预期结构：
    {"transcripts": [{"sentences": [
        {"text": ..., "begin_time": ms, "end_time": ms, "speaker_id": int}, ...
    ]}]}

    speaker 取 sentence 的 speaker_id 字符串化；confidence 该接口不返回，置 None。
    """
    segments: list[Segment] = []
    for transcript in transcript_data.get("transcripts", []):
        for sent in transcript.get("sentences", []):
            speaker_id = sent.get("speaker_id")
            segments.append(
                Segment(
                    seq=len(segments),
                    speaker="" if speaker_id is None else str(speaker_id),
                    text=sent.get("text", ""),
                    start_ms=sent.get("begin_time"),
                    end_ms=sent.get("end_time"),
                    confidence=None,
                )
            )
    return TranscriptResult(segments=segments, raw=transcript_data)


class DashScopeParaformer(ASRProvider):
    """paraformer-v2 ASR provider。"""

    name = "paraformer"

    def __init__(
        self,
        api_key: str,
        *,
        poll_interval: float = _POLL_INTERVAL_S,
        poll_timeout: float = _POLL_TIMEOUT_S,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key:
            raise ProviderError("dashscope_api_key 未配置，无法初始化 paraformer provider")
        self._api_key = api_key
        self._poll_interval = poll_interval
        self._poll_timeout = poll_timeout
        self._client = client or httpx.Client(timeout=30.0)

    # ── 公共接口 ────────────────────────────────────────────────

    def transcribe(self, audio_path: str, *, speaker_hint: int | None = 2) -> TranscriptResult:
        """转写本地音频文件（上传 OSS → 提交异步任务 → 轮询 → 解析）。"""
        oss_url = self._upload_oss(audio_path)
        task_id = self._submit_task(oss_url, speaker_hint)
        output = self._poll_task(task_id)
        return self._fetch_result(output)

    def health_check(self) -> bool:
        """探测策略：GET 一个必然不存在的 task_id。

        不产生转写费用；key 无效会返回 401/403，网络不通抛异常，
        其余响应（如 404/400 任务不存在）说明 key 与服务均可用。
        """
        try:
            resp = self._client.get(
                f"{_API_BASE}/tasks/__health_check__",
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
        except httpx.HTTPError as exc:
            logger.warning("paraformer health_check 网络异常: %s", type(exc).__name__)
            return False
        return resp.status_code not in (401, 403)

    # ── OSS 上传 ────────────────────────────────────────────────

    def _upload_oss(self, audio_path: str) -> str:
        """用 dashscope CLI 上传本地文件到临时 OSS，返回 oss:// URL。"""
        path = Path(audio_path).resolve()
        if not path.is_file():
            raise ProviderError(f"音频文件不存在: {path}")
        cli = _resolve_dashscope_cli()
        try:
            proc = subprocess.run(
                [str(cli), "oss.upload", "--model", MODEL_NAME, "--file", str(path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
                timeout=_UPLOAD_TIMEOUT_S,
                env={**os.environ, "DASHSCOPE_API_KEY": self._api_key},
            )
        except subprocess.TimeoutExpired as exc:
            raise ProviderError(f"oss.upload 超时（{_UPLOAD_TIMEOUT_S}s）: {path}") from exc
        if proc.returncode != 0:
            err = proc.stderr.strip() or proc.stdout.strip() or "(无输出)"
            raise ProviderError(f"dashscope oss.upload 失败（rc={proc.returncode}）: {err}")
        match = re.search(r"oss://\S+", proc.stdout)
        if not match:
            raise ProviderError(f"未能从上传输出解析 oss:// URL。输出：\n{proc.stdout.strip()}")
        return match.group(0)

    # ── 异步任务 ────────────────────────────────────────────────

    def _submit_task(self, oss_url: str, speaker_hint: int | None) -> str:
        """提交转写异步任务，返回 task_id。"""
        parameters: dict[str, Any] = {
            "diarization_enabled": True,
            "language_hints": ["zh", "en"],
        }
        if speaker_hint is not None:
            parameters["speaker_count"] = speaker_hint
        body = {
            "model": MODEL_NAME,
            "input": {"file_urls": [oss_url]},
            "parameters": parameters,
        }
        resp = self._request(
            "POST",
            f"{_API_BASE}/services/audio/asr/transcription",
            headers={
                "X-DashScope-Async": "enable",
                # 传入 DashScope OSS URL 时需要服务端解析
                "X-DashScope-OssResourceResolve": "enable",
            },
            json=body,
        )
        task_id = resp.get("output", {}).get("task_id")
        if not task_id:
            raise ProviderError(f"提交转写任务失败，无 task_id：{resp}")
        logger.info("paraformer 任务已提交: task_id=%s", task_id)
        return task_id

    def _poll_task(self, task_id: str) -> dict[str, Any]:
        """轮询任务直到终态，返回 output 字段。"""
        deadline = time.monotonic() + self._poll_timeout
        while True:
            resp = self._request("GET", f"{_API_BASE}/tasks/{task_id}")
            output = resp.get("output", {})
            status = output.get("task_status", "")
            if status == "SUCCEEDED":
                return output
            if status in ("FAILED", "UNKNOWN", "CANCELED"):
                raise ProviderError(f"转写任务失败：{status} — {output}")
            if time.monotonic() > deadline:
                raise ProviderError(f"转写任务超时：等待 {self._poll_timeout}s 仍为 {status}")
            time.sleep(self._poll_interval)

    def _fetch_result(self, output: dict[str, Any]) -> TranscriptResult:
        """从任务 output 下载 transcription_url 并解析。"""
        for item in output.get("results", []):
            if item.get("transcription_url"):
                # transcription_url 是预签名公网 URL，无需鉴权头
                try:
                    resp = self._client.get(item["transcription_url"], timeout=30.0)
                    resp.raise_for_status()
                    return parse_transcript(resp.json())
                except httpx.HTTPError as exc:
                    raise ProviderError(f"下载转写结果失败: {type(exc).__name__}: {exc}") from exc
            if "transcripts" in item:
                return parse_transcript(item)
        raise ProviderError(f"任务成功但无转写结果：{output}")

    # ── HTTP 辅助 ───────────────────────────────────────────────

    def _request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        """带鉴权的 API 请求；日志与异常均不泄露 Authorization。"""
        headers = dict(kwargs.pop("headers", {}))
        headers["Authorization"] = f"Bearer {self._api_key}"
        try:
            resp = self._client.request(method, url, headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            raise ProviderError(f"DashScope API 网络异常: {type(exc).__name__}: {exc}") from exc
        if resp.status_code >= 400:
            raise ProviderError(f"DashScope API HTTP {resp.status_code}: {resp.text}")
        try:
            return resp.json()
        except ValueError as exc:
            raise ProviderError(f"DashScope API 返回非 JSON: {resp.text[:200]}") from exc
