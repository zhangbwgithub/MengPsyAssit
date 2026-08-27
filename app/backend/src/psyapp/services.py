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
from .enums import JobType, Role, SessionStatus
from .jobs import add_job, mark_job_done, mark_job_failed, mark_job_running
from .models import Record, Session
from .prompts import render_prompt
from .segments import (
    apply_segments_to_session,
    build_cleaned_text,
    build_transcript_lines,
    get_segments,
)

logger = logging.getLogger(__name__)


def run_background_pipeline(
    session_id: int,
    session_factory: Any,
    settings: Settings,
    audio_path: str,
    asr: Any,
    clean_llm: Any,
    record_llm: Any,
) -> None:
    """S0 主链路后台任务：转写 → segments 落库 → 清理+角色判定 → 记录生成。

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
        mark_job_running(db, transcribe_job.id)
        result = asr.transcribe(audio_path)
        if not result.segments:
            raise RuntimeError("ASR 返回 0 个分段")
        apply_segments_to_session(db, session_id, settings.dev_user_id, result.segments)
        db.commit()
        mark_job_done(db, transcribe_job.id)
    except Exception as exc:  # noqa: BLE001 —— 主链路任何失败都收敛为 failed
        logger.exception("会话 %s 转写失败", session_id)
        mark_job_failed(db, transcribe_job.id, str(exc))
        _set_session_status(db, session_id, SessionStatus.FAILED)
        db.close()
        return

    # ── 清理 + 角色判定（一次整体调用，坏 JSON/异常重试 1 次）────
    clean_job = add_job(db, session_id, JobType.CLEAN, clean_llm.name)
    db.commit()
    cleaned_text = _clean_transcript(db, session_id, clean_job, settings, clean_llm)
    if cleaned_text is None:
        _set_session_status(db, session_id, SessionStatus.FAILED)
        db.close()
        return
    session = db.get(Session, session_id)
    if session is not None:
        session.cleaned_text = cleaned_text
    db.commit()

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


def _clean_transcript(db, session_id: int, job, settings: Settings, clean_llm: Any) -> str | None:
    """口语清理 + 角色判定：一次整体调用。失败重试 1 次；仍失败记 job.error 返回 None。

    成功时把 roles.role/role_label 与 cleaned.text 写回 segments，
    并返回带角色标签的 cleaned_text（供 record 阶段与调试）。
    """
    transcript = build_transcript_lines(db, session_id)
    if not transcript:
        mark_job_failed(db, job.id, "清理输入为空：没有可清理的转写文本")
        return None
    prompt = render_prompt("clean", settings=settings, transcript=transcript)
    last_error: str | None = None
    for attempt in (1, 2):
        try:
            mark_job_running(db, job.id)
            text = clean_llm.complete(
                [{"role": "user", "content": prompt}], temperature=0.3
            )
            data = parse_clean_json(text)
            _apply_clean_result(db, session_id, data)
            mark_job_done(db, job.id)
            return build_cleaned_text(db, session_id)
        except Exception as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__}: {exc}"
            logger.warning("会话 %s 清理失败（第 %d 次）: %s", session_id, attempt, exc)
    mark_job_failed(db, job.id, f"清理失败（重试后仍失败）: {last_error}")
    return None


def parse_clean_json(text: str) -> dict[str, Any]:
    """解析 clean v2 的 JSON（角色 + 逐段清理文本）。

    可剥 ```json 围栏；顶层必须是对象，且含 roles（dict）与 cleaned（list）。
    角色值/代号覆盖/seq 对齐的校验在 _apply_clean_result 里结合落库数据做。
    """
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
    roles = data.get("roles")
    cleaned = data.get("cleaned")
    if not isinstance(roles, dict) or not roles:
        raise ValueError("roles 缺失或非对象")
    if not isinstance(cleaned, list):
        raise ValueError("cleaned 缺失或非数组")
    return data


def _apply_clean_result(db, session_id: int, data: dict[str, Any]) -> None:
    """把 clean 结果写回 segments 并做严格校验（raise 即视为该次尝试失败）。

    - roles 键必须覆盖输入中出现过的全部代号，role ∈ {T, P}；
    - cleaned 与 segments 逐段对应（seq 为 0..n-1 且每段 text 为字符串）；
    - text 允许为空字符串：纯语气词段（如整段只有"嗯……"）回退保留原 content，
      避免因模型按规则清成空串而让整次清理失败（FB-002 根因修复）。
    """
    segments = get_segments(db, session_id)
    roles = data["roles"]
    codes_seen = {seg.speaker for seg in segments}
    if not codes_seen <= set(roles):
        missing = sorted(codes_seen - set(roles))
        raise ValueError(f"roles 未覆盖全部说话人代号，缺失: {missing}")
    for code, value in roles.items():
        if not isinstance(value, dict):
            raise ValueError(f"roles[{code!r}] 不是对象")
        role = value.get("role")
        label = value.get("label")
        if role not in (Role.THERAPIST, Role.PATIENT):
            raise ValueError(f"roles[{code!r}].role 非法: {role!r}")
        if not isinstance(label, str) or not label:
            raise ValueError(f"roles[{code!r}].label 缺失或非字符串")

    cleaned = data["cleaned"]
    if len(cleaned) != len(segments) or [item.get("seq") for item in cleaned] != list(
        range(len(segments))
    ):
        got = [item.get("seq") for item in cleaned if isinstance(item, dict)]
        raise ValueError(f"cleaned seq 未与 segments 对齐（段数 {len(segments)}）: {got}")
    for idx, seg in enumerate(segments):
        item = cleaned[idx]
        if not isinstance(item, dict):
            raise ValueError(f"cleaned[{idx}] 不是对象")
        text = item.get("text")
        if not isinstance(text, str):
            raise ValueError(f"cleaned[{idx}].text 缺失或非字符串")

    for idx, seg in enumerate(segments):
        code_info = roles[seg.speaker]
        seg.role = code_info["role"]
        seg.role_label = code_info["label"]
        # 空串容错：纯语气词段保留原始 content，不再抛错导致重试
        cleaned_text = cleaned[idx]["text"]
        seg.cleaned_content = cleaned_text if cleaned_text else seg.content
    db.commit()


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
            "prompt_version": "v2",
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
