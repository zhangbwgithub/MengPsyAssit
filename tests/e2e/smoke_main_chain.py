#!/usr/bin/env python
"""T-S0.3 真实端到端冒烟（有网络）。

流程：
1. 启动后端（默认端口 8661，可 --port 覆盖；DASHSCOPE_API_KEY 从环境继承）
2. curl 上传 tests/audio/01_normal_dialogue.wav（POST /sessions，multipart）
3. 轮询 GET /sessions/{id} 至 done（超时 10 分钟）
4. 断言：status=done、segments≥10 且含 T 与 P、cleaned_text 非空、
   record 含 summary/counselor_work/client_reported_topics
5. 全程响应原文落盘 tests/e2e/results/<时间戳>/

用法：
    .venv/bin/python tests/e2e/smoke_main_chain.py
    .venv/bin/python tests/e2e/smoke_main_chain.py --database-url sqlite:////绝对路径/data/app.db
    DASHSCOPE_API_KEY 从调用方环境继承；本脚本不打印、不落盘任何密钥。
    后端 cwd 固定为仓库根，避免相对路径 sqlite:///data/app.db 解析歧义；
    --database-url 可显式指定 DATABASE_URL（真实冒烟建议用绝对路径指向旧库）。
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIO = REPO_ROOT / "tests" / "audio" / "01_normal_dialogue.wav"
RESULTS_ROOT = REPO_ROOT / "tests" / "e2e" / "results"
PORT = 8661
BASE = f"http://127.0.0.1:{PORT}"
POLL_TIMEOUT_SEC = 600
POLL_INTERVAL_SEC = 5
MAX_FILE_MB = 200


def redact(obj):
    """递归删除可能出现密钥/鉴权的字段，落盘响应前调用。"""
    if isinstance(obj, dict):
        cleaned = {}
        for key, value in obj.items():
            low = key.lower()
            if any(word in low for word in ("authorization", "api_key", "api-key", "token", "secret")):
                continue
            cleaned[key] = redact(value)
        return cleaned
    if isinstance(obj, list):
        return [redact(item) for item in obj]
    if isinstance(obj, str):
        if "sk-" in obj:
            return "<redacted>"
        return obj
    return obj


def http_json(method: str, url: str, *, body: bytes | None = None, headers: dict | None = None):
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def multipart_body(fields: dict[str, str], file_field: str, filename: str, data: bytes) -> tuple[bytes, str]:
    boundary = f"PsySmoke{uuid4().hex}"
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(
            f"--{boundary}\r\n".encode()
            + f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
            + f"{value}\r\n".encode()
        )
    parts.append(
        f"--{boundary}\r\n".encode()
        + f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'.encode()
        + b"Content-Type: application/octet-stream\r\n\r\n"
        + data
        + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    return body, headers['Content-Type']


def run_server(settings: dict) -> subprocess.Popen:
    env = dict(os.environ)
    prepend_path = settings.pop("PREPEND_SYS_PATH", "")
    for key, value in settings.items():
        env[key] = value
    if prepend_path and prepend_path not in env.get("PYTHONPATH", "").split(os.pathsep):
        env["PYTHONPATH"] = (
            prepend_path + os.pathsep + env["PYTHONPATH"]
            if env.get("PYTHONPATH")
            else prepend_path
        )
    proc = subprocess.Popen(
        [
            str(REPO_ROOT / ".venv" / "bin" / "python"),
            "-m",
            "uvicorn",
            "psyapp.main:app",
            "--port",
            str(PORT),
            "--host",
            "127.0.0.1",
        ],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return proc


def wait_health(timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            status, body = http_json("GET", f"{BASE}/health")
            if status == 200:
                return body
        except Exception:  # noqa: BLE001
            time.sleep(1)
    raise RuntimeError(f"后端 {BASE}/health 在 {timeout}s 内未就绪")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep-server", action="store_true", help="冒烟后不关闭后端")
    parser.add_argument(
        "--database-url",
        default="",
        help="显式设置 DATABASE_URL（如 sqlite:////绝对路径/data/app.db），默认继承环境变量",
    )
    args = parser.parse_args()

    if not os.environ.get("DASHSCOPE_API_KEY"):
        print("[FAIL] 环境缺少 DASHSCOPE_API_KEY，无法真实冒烟", file=sys.stderr)
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = RESULTS_ROOT / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    log = (out_dir / "smoke.log").open("w", encoding="utf-8")

    def save(name, payload):
        path = out_dir / name
        path.write_text(
            json.dumps(redact(payload), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    def write(line):
        print(line)
        log.write(line + "\n")
        log.flush()

    write(f"[INFO] 冒烟开始 {stamp}，结果落盘 {out_dir}")

    server = None
    try:
        server_settings = {
            "DASHSCOPE_API_KEY": os.environ["DASHSCOPE_API_KEY"],
            "PREPEND_SYS_PATH": str(REPO_ROOT / "app" / "backend" / "src"),
        }
        if args.database_url:
            server_settings["DATABASE_URL"] = args.database_url
        server = run_server(server_settings)
        write("[INFO] 后端启动中（uvicorn:8661）…")
        health = wait_health()
        write(f"[INFO] /health → {health}")
        save("health.json", health)

        audio_bytes = AUDIO.read_bytes()
        write(f"[INFO] 上传音频 {AUDIO}（{len(audio_bytes)} bytes）")
        body, content_type = multipart_body(
            {"speaker_zero": "T"}, "file", AUDIO.name, audio_bytes
        )
        status, upload = http_json(
            "POST",
            f"{BASE}/sessions",
            body=body,
            headers={"Content-Type": content_type},
        )
        write(f"[INFO] POST /sessions → HTTP {status}")
        save("upload.json", {"status_code": status, "body": upload})
        if status != 200 or not upload.get("ok"):
            write(f"[FAIL] 上传失败: {upload}")
            return 1
        session_id = upload["data"]["session_id"]
        write(f"[INFO] session_id={session_id}，初始状态={upload['data']['status']}")

        seen_states = [upload["data"]["status"]]
        deadline = time.monotonic() + POLL_TIMEOUT_SEC
        final = None
        while time.monotonic() < deadline:
            time.sleep(POLL_INTERVAL_SEC)
            status, detail = http_json("GET", f"{BASE}/sessions/{session_id}")
            state = detail["data"]["status"]
            if state not in seen_states:
                seen_states.append(state)
                write(f"[INFO] 状态流转: {state}")
            if state in ("done", "failed"):
                final = detail["data"]
                break
        if final is None:
            write(f"[FAIL] 轮询 {POLL_TIMEOUT_SEC}s 超时未达终态: {seen_states}")
            return 1

        save("final_session.json", final)
        write(f"[INFO] 终态: {final['status']}（状态序列 {' → '.join(seen_states)}）")

        # ── 断言 ──────────────────────────────────────────────
        failures: list[str] = []
        if final["status"] != "done":
            failures.append(f"status={final['status']}，期望 done")
        segments = final.get("segments") or []
        speakers = {seg.get("speaker") for seg in segments}
        if len(segments) < 10:
            failures.append(f"segments 数量 {len(segments)} < 10")
        if not {"T", "P"} <= speakers:
            failures.append(f"segments 未同时含 T/P 两种说话人，实际={sorted(speakers)}")
        if not final.get("cleaned_text"):
            failures.append("cleaned_text 为空")
        record = final.get("record") or {}
        for field in ("summary", "counselor_work", "client_reported_topics"):
            if not record.get(field):
                failures.append(f"record 缺少字段 {field}")

        if failures:
            for item in failures:
                write(f"[FAIL] {item}")
            return 1

        write("[PASS] 全部断言通过：done / segments≥10 / T+P / cleaned_text / record 三字段")
        write(f"[PASS] segments={len(segments)}，speakers={sorted(speakers)}，record.summary 前 80 字={record['summary'][:80]!r}")
        return 0
    finally:
        if server is not None and not args.keep_server:
            server.terminate()
            with contextlib.suppress(Exception):
                server.wait(timeout=10)
        # 结果清单必须在关日志前写入
        write(f"[INFO] 结果文件目录: {out_dir}")
        listed = sorted(p.name for p in out_dir.iterdir())
        write(f"[INFO] 落盘文件: {listed}  (检查: 无 authorization/api_key 字段入盘)")
        log.close()


if __name__ == "__main__":
    sys.exit(main())
