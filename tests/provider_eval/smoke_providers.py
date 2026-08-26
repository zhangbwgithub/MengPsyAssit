"""真实冒烟：ASR（paraformer-v2）+ LLM（qwen-max）走一遍真实 DashScope API。

用法（需注入 DASHSCOPE_API_KEY 环境变量）：
    .venv/bin/python tests/provider_eval/smoke_providers.py            # 全跑
    .venv/bin/python tests/provider_eval/smoke_providers.py --asr      # 只跑 ASR
    .venv/bin/python tests/provider_eval/smoke_providers.py --llm      # 只跑 LLM

结果落盘 tests/provider_eval/results/<时间戳>/：
- asr_transcript.json：解析后的全部 Segment + paraformer transcription 原文
- llm_completion.json：LLM 请求入参与响应原文
- http_trace.jsonl：每次 HTTP 请求的入参/响应原文/耗时（不记录任何请求头，杜绝 key 泄露）

断言：ASR 段数 >10 且 ≥2 个说话人标签；LLM 响应非空。全部通过退出码 0，否则 1。
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "app" / "backend" / "src"))

from psyapp.config import Settings  # noqa: E402
from psyapp.providers import DashScopeParaformer, QwenLLM  # noqa: E402

AUDIO_PATH = REPO_ROOT / "tests" / "audio" / "01_normal_dialogue.wav"
RESULTS_ROOT = Path(__file__).resolve().parent / "results"


class HttpTracer:
    """记录每次 HTTP 请求的方法/URL/入参/响应原文/耗时（不含请求头）。"""

    def __init__(self) -> None:
        self.entries: list[dict] = []

    def make_client(self, timeout: float = 180.0) -> httpx.Client:
        return httpx.Client(
            timeout=timeout,
            event_hooks={"request": [self._on_request], "response": [self._on_response]},
        )

    def _on_request(self, request: httpx.Request) -> None:
        request.extensions["_trace_index"] = len(self.entries)
        body = request.content.decode("utf-8", errors="replace") if request.content else None
        self.entries.append(
            {"method": request.method, "url": str(request.url), "request_body": body}
        )

    def _on_response(self, response: httpx.Response) -> None:
        response.read()
        idx = response.request.extensions.get("_trace_index")
        if idx is None:
            return
        self.entries[idx].update(
            {
                "status_code": response.status_code,
                "elapsed_ms": round(response.elapsed.total_seconds() * 1000, 1),
                "response_body": response.text,
            }
        )

    def dump(self, out_dir: Path) -> None:
        with (out_dir / "http_trace.jsonl").open("w", encoding="utf-8") as f:
            for entry in self.entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def run_asr(out_dir: Path, settings: Settings, tracer: HttpTracer) -> None:
    """ASR 冒烟：完整转写 01_normal_dialogue.wav，断言段数与说话人数。"""
    provider = DashScopeParaformer(
        api_key=settings.dashscope_api_key, client=tracer.make_client(timeout=30.0)
    )
    print(f"[ASR] health_check … {provider.health_check()}")

    t0 = time.monotonic()
    result = provider.transcribe(str(AUDIO_PATH), speaker_hint=2)
    latency = time.monotonic() - t0

    speakers = sorted({seg.speaker for seg in result.segments})
    payload = {
        "provider": provider.name,
        "audio": AUDIO_PATH.name,
        "latency_s": round(latency, 2),
        "speaker_labels": speakers,
        "segment_count": len(result.segments),
        "segments": [dataclasses.asdict(seg) for seg in result.segments],
        "raw_transcription": result.raw,
    }
    (out_dir / "asr_transcript.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[ASR] 段数={len(result.segments)} 说话人={speakers} 耗时={latency:.1f}s")

    assert len(result.segments) > 10, f"段数应 >10，实际 {len(result.segments)}"
    assert len(speakers) >= 2, f"说话人标签应 ≥2，实际 {speakers}"


def run_llm(out_dir: Path, settings: Settings, tracer: HttpTracer) -> None:
    """LLM 冒烟：qwen-max 一次中文 completion，断言非空。"""
    provider = QwenLLM(
        api_key=settings.dashscope_api_key,
        model=settings.llm_model,
        client=tracer.make_client(),
    )
    print(f"[LLM] health_check … {provider.health_check()}")

    messages = [{"role": "user", "content": "用一句话说明什么是心理咨询记录"}]
    t0 = time.monotonic()
    content = provider.complete(messages, temperature=0.3)
    latency = time.monotonic() - t0

    payload = {
        "provider": provider.name,
        "model": settings.llm_model,
        "latency_s": round(latency, 2),
        "request": {"messages": messages, "temperature": 0.3},
        "response_content": content,
    }
    (out_dir / "llm_completion.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[LLM] 响应：{content[:80]}… 耗时={latency:.1f}s")

    assert content and content.strip(), "LLM 响应为空"


def main() -> int:
    parser = argparse.ArgumentParser(description="Provider 真实冒烟")
    parser.add_argument("--asr", action="store_true", help="只跑 ASR 冒烟")
    parser.add_argument("--llm", action="store_true", help="只跑 LLM 冒烟")
    args = parser.parse_args()
    run_both = not (args.asr or args.llm)

    if not os.environ.get("DASHSCOPE_API_KEY", "").strip():
        print("缺少 DASHSCOPE_API_KEY 环境变量", file=sys.stderr)
        return 2

    settings = Settings()
    out_dir = RESULTS_ROOT / datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    tracer = HttpTracer()

    try:
        if run_both or args.asr:
            run_asr(out_dir, settings, tracer)
        if run_both or args.llm:
            run_llm(out_dir, settings, tracer)
    finally:
        tracer.dump(out_dir)

    print(f"冒烟通过，结果目录: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
