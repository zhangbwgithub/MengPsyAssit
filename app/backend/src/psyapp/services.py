"""会话处理服务：S0 最简主链路后台任务（转写 → 清理 → 记录生成）。

任务卡路线决策：
- 后台执行：FastAPI BackgroundTasks 跑一个任务函数串行执行三段；不引队列中间件。
- jobs 表记录形态：每个会话三个阶段各一行（type=transcribe/clean/record），
  每行独立记录 provider 与状态/错误，便于故障定位与追溯。
- 清理/记录均为一次整体调用；LLM 返回坏 JSON 重试 1 次，仍失败标 failed。
- 会话状态机最小版：uploading（创建即写）→ transcribing（后台开始）→ done/failed。
  失败时对应 job.error 记原因；会话可重交（复用 POST /sessions，幂等清空旧 segments）。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from .config import Settings
from .enums import JobType, SessionStatus
from .jobs import add_job, mark_job_done, mark_job_failed, mark_job_running
from .models import Record, Session
from .prompts import render_prompt
from .segments import apply_segments_to_session, build_transcript_lines

logger = logging.getLogger(__name__)


def run_background_pipeline(
    session_id: int,
    session_factory: Any,
    settings: Settings,
    audio_path: str,
    speaker_zero: str,
    asr: Any,
    clean_llm: Any,
    record_llm: Any,
) -> None:
    """S0 主链路后台任务：转写 → segments 落库 → 清理 → 记录生成。

    幂等：支持同一会话重交（失败/无 segments 时重跑，旧 segments 先清空）。
    任一阶段异常都捕获 → session.status=failed，对应 job.error 记原因。

    asr/clean_llm/record_llm 为 provider 实例；测试可传 fake，生产由工厂创建。
    """
    db = session_factory()

    # ── 转写 ──────────────────────────────────────────────────
    transcribe_job = add_job(db, session_id, JobType.TRANSCRIBE, asr.name)
    db.commit()
    _set_session_status(db, session_id, SessionStatus.TRANSCRIBING)
    try:
        result = asr.transcribe(audio_path)
        if not result.segments:
            raise RuntimeError("ASR 返回 0 个分段")
        mark_job_running(db, transcribe_job.id)
        apply_segments_to_session(
            db, session_id, settings.dev_user_id, result.segments, speaker_zero
        )
        db.commit()
        mark_job_done(db, transcribe_job.id)
    except Exception as exc:  # noqa: BLE001 —— 主链路任何失败都收敛为 failed
        logger.exception("会话 %s 转写失败", session_id)
        mark_job_failed(db, transcribe_job.id, str(exc))
        _set_session_status(db, session_id, SessionStatus.FAILED)
        db.close()
        return

    # ── 清理（一次整体调用，坏 JSON/异常重试 1 次）────────────
    clean_job = add_job(db, session_id, JobType.CLEAN, clean_llm.name)
    db.commit()
    cleaned_text = _clean_transcript(db, session_id, clean_job, settings, clean_llm)
    if cleaned_text is None:
        _set_session_status(db, session_id, SessionStatus.FAILED)
        db.close()
        return
    _set_session_cleaned_text(db, session_id, cleaned_text)

    # ── 记录（一次整体调用，坏 JSON 重试 1 次，成功落库）──────
    record_job = add_job(db, session_id, JobType.RECORD, record_llm.name)
    db.commit()
    record_data = _generate_record(
        db, session_id, record_job, settings, cleaned_text, record_llm
    )
    if record_data is None:
        _set_session_status(db, session_id, SessionStatus.FAILED)
        db.close()
        return

    _set_session_status(db, session_id, SessionStatus.DONE)
    db.close()


def _set_session_status(db, session_id: int, status: str) -> None:
    session = db.get(Session, session_id)
    if session is None:
        raise RuntimeError(f"会话不存在: {session_id}")
    session.status = status
    db.commit()


def _set_session_cleaned_text(db, session_id: int, text: str) -> None:
    session = db.get(Session, session_id)
    if session is None:
        raise RuntimeError(f"会话不存在: {session_id}")
    session.cleaned_text = text
    db.commit()


def _clean_transcript(db, session_id: int, job, settings: Settings, clean_llm: Any) -> str | None:
    """口语清理：一次整体调用。失败重试 1 次；仍失败记 job.error 返回 None。"""
    transcript = build_transcript_lines(db, session_id)
    if not transcript:
        mark_job_failed(db, job.id, "清理输入为空：没有可清理的转写文本")
        return None
    prompt = render_prompt("clean", settings=settings, transcript=transcript)
    for attempt in (1, 2):
        try:
            mark_job_running(db, job.id)
            text = clean_llm.complete(
                [{"role": "user", "content": prompt}], temperature=0.3
            )
            text = text.strip()
            if not text:
                raise ValueError("清理返回空文本")
            mark_job_done(db, job.id)
            return text
        except Exception as exc:  # noqa: BLE001
            logger.warning("会话 %s 清理失败（第 %d 次）: %s", session_id, attempt, exc)
            if attempt == 2:
                mark_job_failed(db, job.id, f"清理失败（重试后仍失败）: {exc}")
                return None
    return None


def _generate_record(
    db, session_id: int, job, settings: Settings, cleaned_text: str, record_llm: Any
) -> dict[str, Any] | None:
    """记录生成：一次整体调用，坏 JSON 重试 1 次；成功落库 records，返回数据。"""
    prompt = render_prompt("record", settings=settings, cleaned_transcript=cleaned_text)
    last_error: str | None = None
    for attempt in (1, 2):
        try:
            mark_job_running(db, job.id)
            text = record_llm.complete(
                [{"role": "user", "content": prompt}], temperature=0.3
            )
            data = parse_record_json(text)
            store_record(db, session_id, settings, data)
            mark_job_done(db, job.id)
            return data
        except Exception as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__}: {exc}"
            logger.warning("会话 %s 记录生成失败（第 %d 次）: %s", session_id, attempt, exc)
    mark_job_failed(db, job.id, f"记录生成失败（重试后仍失败）: {last_error}")
    return None


def parse_record_json(text: str) -> dict[str, Any]:
    """解析 LLM 输出的记录 JSON；剥掉可能的 ```json 围栏；缺失三字段抛 ValueError。"""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"非 JSON: {text[:200]}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"JSON 顶层不是对象: {text[:200]}")
    summary = data.get("summary")
    counselor_work = data.get("counselor_work")
    topics = data.get("client_reported_topics")
    if not isinstance(summary, str) or not summary:
        raise ValueError("summary 缺失或非字符串")
    if not isinstance(counselor_work, str) or not counselor_work:
        raise ValueError("counselor_work 缺失或非字符串")
    if not isinstance(topics, list):
        raise ValueError("client_reported_topics 缺失或非数组")
    return data


def store_record(db, session_id: int, settings: Settings, data: dict[str, Any]) -> Record:
    """records 落库：basic_info 存 provider/model/prompt_version/session_id。"""
    session = db.get(Session, session_id)
    record = Record(
        user_id=settings.dev_user_id,
        client_id=session.client_id if session is not None else None,
        session_id=session_id,
        record_time=datetime.now(timezone.utc).replace(tzinfo=None),
        status="draft",
        basic_info={
            "provider": settings.llm_provider,
            "model": settings.llm_model,
            "prompt_version": "v1",
            "session_id": session_id,
            "client_reported_topics": data["client_reported_topics"],
        },
        summary=data["summary"],
        therapist_work=data["counselor_work"],
        notes="",
    )
    db.add(record)
    db.commit()
    return record
