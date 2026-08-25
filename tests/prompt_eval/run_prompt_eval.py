#!/usr/bin/env python3
"""T-0.3 LLM prompt 骨架实测脚本。

流程：
1. 取 tests/golden/01_normal_dialogue.json 的对话稿 -> clean prompt -> 清理文本
2. 清理文本 -> record prompt -> 记录 JSON
3. tests/golden/adversarial_inducement.txt -> record prompt（跳过 clean）-> 记录 JSON

全部请求的 prompt 全文、响应全文、耗时原样落盘到
tests/prompt_eval/results/<时间戳>/。
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

# ── 路径常量 ──────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[2]
TESTS_DIR = REPO_ROOT / "tests"
GOLDEN_DIR = TESTS_DIR / "golden"
PROMPTS_DIR = REPO_ROOT / "app" / "backend" / "prompts"
RESULTS_DIR = Path(__file__).resolve().parent / "results"

CLEAN_TEMPLATE = PROMPTS_DIR / "clean" / "v1.md"
RECORD_TEMPLATE = PROMPTS_DIR / "record" / "v1.md"
NORMAL_DIALOGUE = GOLDEN_DIR / "01_normal_dialogue.json"
ADVERSARIAL_SAMPLE = GOLDEN_DIR / "adversarial_inducement.txt"

# ── 调用参数 ──────────────────────────────────────────────────
API_KEY_ENV = "DASHSCOPE_API_KEY"
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL = "qwen-max"
TEMPERATURE = 0.2
MAX_ATTEMPTS = 2
RETRY_SLEEP_SECONDS = 3

REQUIRED_RECORD_FIELDS = ("summary", "counselor_work", "client_reported_topics")


# ── 工具函数 ──────────────────────────────────────────────────


def read_text(path: Path) -> str:
    """以 UTF-8 读取文本文件。"""
    return path.read_text(encoding="utf-8")


def render_template(template: str, **values: str) -> str:
    """替换模板中的 {{key}} 占位符。"""
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    return rendered


def render_messages(messages: list[dict]) -> str:
    """把 messages 渲染成可落盘的 prompt 全文。"""
    parts: list[str] = []
    for msg in messages:
        role = msg.get("role", "?")
        content = msg.get("content", "")
        parts.append(f"[{role}]\n{content}")
    return "\n\n".join(parts)


def extract_json(text: str) -> dict | None:
    """从模型输出中提取 JSON 对象（容忍 markdown 代码块与前后噪声）。"""
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        return json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None


def _usage_to_dict(usage) -> dict | None:
    """把 openai SDK 返回的 usage 转成普通 dict（版本兼容）。"""
    if usage is None:
        return None
    try:
        if hasattr(usage, "model_dump"):
            return usage.model_dump()
        return dict(usage)
    except Exception:
        return None


def _chat_openai(api_key: str, messages: list[dict]) -> tuple[str, dict | None]:
    """openai SDK 路径。"""
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=BASE_URL)
    resp = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=TEMPERATURE,
    )
    content = resp.choices[0].message.content
    return content, _usage_to_dict(getattr(resp, "usage", None))


def _chat_urllib(api_key: str, messages: list[dict]) -> tuple[str, dict | None]:
    """urllib 标准库路径（openai 包不可用或调用失败时的兜底）。"""
    body = {
        "model": MODEL,
        "messages": messages,
        "temperature": TEMPERATURE,
    }
    req = urllib.request.Request(
        BASE_URL + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    content = payload["choices"][0]["message"]["content"]
    return content, payload.get("usage")


def _perform_chat(api_key: str, messages: list[dict]) -> tuple[str, dict | None, str]:
    """优先 openai SDK；不可用或调用失败时回退 urllib。"""
    try:
        import openai  # noqa: F401

        sdk = "openai"
        try:
            content, usage = _chat_openai(api_key, messages)
        except Exception as exc:
            print(
                f"    openai SDK 调用失败（{type(exc).__name__}: {exc}），回退 urllib"
            )
            content, usage = _chat_urllib(api_key, messages)
            sdk = "urllib"
    except ImportError:
        content, usage = _chat_urllib(api_key, messages)
        sdk = "urllib"
    return content, usage, sdk


def chat(
    messages: list[dict], out_dir: Path, case_name: str
) -> tuple[str, dict]:
    """调用 qwen-max，并把 prompt 全文、响应全文、耗时/usage 落盘。"""
    api_key = os.environ.get(API_KEY_ENV)
    if not api_key:
        print(f"错误：环境变量 {API_KEY_ENV} 未设置", file=sys.stderr)
        sys.exit(2)

    prompt_text = render_messages(messages)
    content = ""
    usage = None
    sdk = ""
    last_err: Exception | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            start = time.perf_counter()
            content, usage, sdk = _perform_chat(api_key, messages)
            elapsed = time.perf_counter() - start
            break
        except Exception as exc:
            last_err = exc
            if attempt < MAX_ATTEMPTS:
                print(
                    f"    {case_name} 第 {attempt} 次调用失败"
                    f"（{type(exc).__name__}: {exc}），{RETRY_SLEEP_SECONDS} 秒后重试"
                )
                time.sleep(RETRY_SLEEP_SECONDS)
    else:
        print(f"错误：{case_name} 调用失败：{last_err}", file=sys.stderr)
        sys.exit(3)

    # 原样落盘：prompt 全文 / 响应全文 / 元信息
    (out_dir / f"{case_name}.prompt.txt").write_text(prompt_text, encoding="utf-8")
    (out_dir / f"{case_name}.response.txt").write_text(content, encoding="utf-8")

    meta = {
        "case": case_name,
        "model": MODEL,
        "temperature": TEMPERATURE,
        "sdk": sdk,
        "latency_seconds": round(elapsed, 3),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "prompt_chars": len(prompt_text),
        "response_chars": len(content),
        "usage": usage,
    }
    (out_dir / f"{case_name}.meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return content, meta


def load_transcript(golden_path: Path) -> str:
    """从黄金文字稿取对话稿（优先 transcript 字段，兜底按 turns 拼接）。"""
    golden = json.loads(read_text(golden_path))
    transcript = golden.get("transcript")
    if transcript:
        return transcript
    return "\n".join(
        f"{turn['speaker']}: {turn['text']}" for turn in golden.get("turns", [])
    )


def save_parsed_json(out_dir: Path, case_name: str, raw: str) -> dict | None:
    """解析 record 输出并落盘 parsed.json；失败返回 None。"""
    parsed = extract_json(raw)
    if parsed is None:
        return None
    (out_dir / f"{case_name}.parsed.json").write_text(
        json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return parsed


# ── 主流程 ────────────────────────────────────────────────────


def main() -> None:
    # 前置检查
    for path in (CLEAN_TEMPLATE, RECORD_TEMPLATE, NORMAL_DIALOGUE, ADVERSARIAL_SAMPLE):
        if not path.is_file():
            print(f"错误：文件不存在：{path}", file=sys.stderr)
            sys.exit(1)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = RESULTS_DIR / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"输出目录：{out_dir}\n")

    clean_template = read_text(CLEAN_TEMPLATE)
    record_template = read_text(RECORD_TEMPLATE)

    # 用例 1：正常对话 -> clean
    print("用例 1/3：clean（01_normal_dialogue.json 对话稿）")
    transcript = load_transcript(NORMAL_DIALOGUE)
    clean_prompt = render_template(clean_template, transcript=transcript)
    cleaned, meta1 = chat(
        [{"role": "user", "content": clean_prompt}],
        out_dir,
        "01_clean_normal_dialogue",
    )
    print(
        f"  完成：{meta1['latency_seconds']}s，sdk={meta1['sdk']}，"
        f"输出 {len(cleaned)} 字"
    )

    # 用例 2：清理后全文 -> record
    print("\n用例 2/3：record（清理后对话）")
    record_prompt = render_template(record_template, cleaned_transcript=cleaned)
    record_raw, meta2 = chat(
        [{"role": "user", "content": record_prompt}],
        out_dir,
        "02_record_cleaned_dialogue",
    )
    parsed2 = save_parsed_json(out_dir, "02_record_cleaned_dialogue", record_raw)
    if parsed2 is None:
        print(
            f"  完成：{meta2['latency_seconds']}s，sdk={meta2['sdk']}，"
            "JSON 解析失败（响应原文已落盘）"
        )
    else:
        missing2 = [k for k in REQUIRED_RECORD_FIELDS if k not in parsed2]
        print(
            f"  完成：{meta2['latency_seconds']}s，sdk={meta2['sdk']}，"
            f"JSON 解析成功，缺失字段：{missing2 or '无'}"
        )

    # 用例 3：诱导样本 -> record（跳过 clean）
    print("\n用例 3/3：record（诱导样本，跳过 clean）")
    adv_text = read_text(ADVERSARIAL_SAMPLE).strip()
    adv_prompt = render_template(record_template, cleaned_transcript=adv_text)
    adv_raw, meta3 = chat(
        [{"role": "user", "content": adv_prompt}],
        out_dir,
        "03_record_adversarial",
    )
    parsed3 = save_parsed_json(out_dir, "03_record_adversarial", adv_raw)
    if parsed3 is None:
        print(
            f"  完成：{meta3['latency_seconds']}s，sdk={meta3['sdk']}，"
            "JSON 解析失败（响应原文已落盘）"
        )
    else:
        missing3 = [k for k in REQUIRED_RECORD_FIELDS if k not in parsed3]
        print(
            f"  完成：{meta3['latency_seconds']}s，sdk={meta3['sdk']}，"
            f"JSON 解析成功，缺失字段：{missing3 or '无'}"
        )

    # 汇总索引
    index = {
        "timestamp": timestamp,
        "model": MODEL,
        "temperature": TEMPERATURE,
        "cases": [
            {
                "name": "01_clean_normal_dialogue",
                "input": "01_normal_dialogue.json 的 transcript",
                "sdk": meta1["sdk"],
                "latency_seconds": meta1["latency_seconds"],
                "response_chars": meta1["response_chars"],
            },
            {
                "name": "02_record_cleaned_dialogue",
                "input": "用例 1 的清理输出",
                "sdk": meta2["sdk"],
                "latency_seconds": meta2["latency_seconds"],
                "response_chars": meta2["response_chars"],
                "json_parsed": parsed2 is not None,
            },
            {
                "name": "03_record_adversarial",
                "input": "tests/golden/adversarial_inducement.txt",
                "sdk": meta3["sdk"],
                "latency_seconds": meta3["latency_seconds"],
                "response_chars": meta3["response_chars"],
                "json_parsed": parsed3 is not None,
            },
        ],
    }
    (out_dir / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n结果已全部写入：{out_dir}")


if __name__ == "__main__":
    main()
