"""真实冒烟：三个 LLM（mimo / deepseek / qwen）最小 completion + 默认 mimo 完整 clean+record 链路。

用法（.env 已含 DASHSCOPE_API_KEY / XIAOMI_CN_API_KEY / DEEPSEEK_API_KEY，pydantic-settings 自动读取）：
    .venv/bin/python tests/provider_eval/smoke_llm_providers.py            # 全跑
    .venv/bin/python tests/provider_eval/smoke_llm_providers.py --basic    # 只跑三模型最小 completion
    .venv/bin/python tests/provider_eval/smoke_llm_providers.py --chain    # 只跑 mimo clean+record 链路

结果落盘 tests/provider_eval/results/<时间戳>/：
- llm_completions.json：三个模型最小 completion 的请求入参与响应原文
- mimo_clean_record.json：默认 mimo 完整链路（golden 对话稿 → clean → record JSON）往返
- http_trace.jsonl：每次 HTTP 请求的入参/响应原文/耗时（不记录任何请求头，杜绝 key 泄露）

断言：三模型响应均非空；mimo clean 非空且 record JSON 三字段齐全；
落盘文件全量扫描不含任何 key 明文。全部通过退出码 0，否则 1。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "app" / "backend" / "src"))

from psyapp.config import Settings
from psyapp.prompts import render_prompt
from psyapp.providers import DeepseekLLM, MimoLLM, QwenLLM
from psyapp.services import parse_record_json
from smoke_providers import HttpTracer  # 复用既有 tracer（不记录请求头）

GOLDEN_PATH = REPO_ROOT / "tests" / "golden" / "01_normal_dialogue.json"
RESULTS_ROOT = Path(__file__).resolve().parent / "results"


def _check_keys(settings: Settings) -> list[str]:
    """返回缺失 key 的环境变量名列表（不打印 key 本体）。"""
    missing = []
    if not settings.xiaomi_cn_api_key.strip():
        missing.append("XIAOMI_CN_API_KEY")
    if not settings.deepseek_api_key.strip():
        missing.append("DEEPSEEK_API_KEY")
    if not settings.dashscope_api_key.strip():
        missing.append("DASHSCOPE_API_KEY")
    return missing


def run_basic(out_dir: Path, settings: Settings, tracer: HttpTracer) -> None:
    """三模型最小 completion：各问一次「什么是心理咨询记录」，断言响应非空。"""
    messages = [{"role": "user", "content": "用一句话说明什么是心理咨询记录"}]
    providers = [
        MimoLLM(api_key=settings.xiaomi_cn_api_key, client=tracer.make_client()),
        DeepseekLLM(api_key=settings.deepseek_api_key, client=tracer.make_client()),
        QwenLLM(api_key=settings.dashscope_api_key, model="qwen-max", client=tracer.make_client()),
    ]
    results = []
    for provider in providers:
        print(f"[LLM:{provider.name}] health_check … {provider.health_check()}")
        t0 = time.monotonic()
        content = provider.complete(messages, temperature=0.3)
        latency = time.monotonic() - t0
        assert content and content.strip(), f"{provider.name} 响应为空"
        results.append(
            {
                "provider": provider.name,
                "model": provider._model,
                "latency_s": round(latency, 2),
                "request": {"messages": messages, "temperature": 0.3},
                "response_content": content,
            }
        )
        print(f"[LLM:{provider.name}] 响应：{content[:80]}… 耗时={latency:.1f}s")

    (out_dir / "llm_completions.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def run_mimo_chain(out_dir: Path, settings: Settings, tracer: HttpTracer) -> None:
    """默认 mimo 完整链路：golden 01 对话稿 → clean prompt → record prompt → 断言三字段。"""
    mimo = MimoLLM(
        api_key=settings.xiaomi_cn_api_key,
        model=settings.llm_model if settings.llm_provider == "mimo" else "mimo-v2.5-pro",
        client=tracer.make_client(),
    )
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    transcript = "\n".join(f"{t['speaker']}: {t['text']}" for t in golden["turns"])
    print(f"[mimo] golden 对话稿 {len(golden['turns'])} 段，开始 clean …")

    t0 = time.monotonic()
    clean_prompt = render_prompt("clean", settings=settings, transcript=transcript)
    cleaned = mimo.complete([{"role": "user", "content": clean_prompt}], temperature=0.3).strip()
    clean_latency = time.monotonic() - t0
    assert cleaned, "clean 返回空文本"
    print(f"[mimo] clean 完成 耗时={clean_latency:.1f}s")

    t0 = time.monotonic()
    record_prompt = render_prompt("record", settings=settings, cleaned_transcript=cleaned)
    record_text = mimo.complete([{"role": "user", "content": record_prompt}], temperature=0.3)
    record_latency = time.monotonic() - t0
    data = parse_record_json(record_text)  # 三字段缺失/非 JSON 会抛 ValueError
    print(f"[mimo] record 完成 耗时={record_latency:.1f}s topics={data['client_reported_topics']}")

    payload = {
        "provider": mimo.name,
        "model": mimo._model,
        "golden": GOLDEN_PATH.name,
        "turns": len(golden["turns"]),
        "transcript_input": transcript,
        "clean": {"latency_s": round(clean_latency, 2), "cleaned_text": cleaned},
        "record": {
            "latency_s": round(record_latency, 2),
            "raw_text": record_text,
            "parsed": data,
        },
    }
    (out_dir / "mimo_clean_record.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def scan_no_key_leak(out_dir: Path, settings: Settings) -> None:
    """全量扫描落盘文件，任何 key 明文出现即失败（零泄露红线）。"""
    keys = [
        settings.xiaomi_cn_api_key.strip(),
        settings.deepseek_api_key.strip(),
        settings.dashscope_api_key.strip(),
    ]
    for path in out_dir.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        assert "Authorization" not in text, f"{path.name} 含 Authorization 字样"
        for key in keys:
            if key:
                assert key not in text, f"{path.name} 含 key 明文（零泄露红线）"
    print("[leak-scan] 落盘文件无 key/Authorization ✓")


def main() -> int:
    parser = argparse.ArgumentParser(description="LLM Provider 真实冒烟（T-S0.6）")
    parser.add_argument("--basic", action="store_true", help="只跑三模型最小 completion")
    parser.add_argument("--chain", action="store_true", help="只跑默认 mimo clean+record 链路")
    args = parser.parse_args()
    run_both = not (args.basic or args.chain)

    settings = Settings()
    missing = _check_keys(settings)
    if missing:
        print(f"缺少环境变量: {', '.join(missing)}（由 .env 提供，本脚本不新建）", file=sys.stderr)
        return 2

    out_dir = RESULTS_ROOT / datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    tracer = HttpTracer()

    try:
        if run_both or args.basic:
            run_basic(out_dir, settings, tracer)
        if run_both or args.chain:
            run_mimo_chain(out_dir, settings, tracer)
    finally:
        tracer.dump(out_dir)

    scan_no_key_leak(out_dir, settings)
    print(f"冒烟通过，结果目录: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
