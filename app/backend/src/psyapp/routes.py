"""S0 主链路 REST 路由：POST /sessions（上传+后台任务）、GET 会话查询。"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, Request, UploadFile
from pydantic import BaseModel

from .audio import probe_duration_seconds, save_upload_to_audio_dir, validate_audio_ext
from .config import Settings
from .enums import ClientStatus, PipelineMode, SessionMode, SessionStatus
from .models import Client, Job, Record, Segment, Session, SessionGroup
from .providers import get_asr_provider, get_llm_provider
from .providers.omni import QwenOmniLLM
from .response import ApiError, ok
from .segments import build_cleaned_text, get_segments
from .services import run_background_pipeline

router = APIRouter()

_MODEL_DISPLAY = {
    PipelineMode.OMNI: "qwen3.5-omni-plus",
    PipelineMode.ASR: "paraformer-v2 + deepseek-v4-flash",
}

_CLIENT_STATUSES = (ClientStatus.ACTIVE, ClientStatus.DISABLED)


class SessionPatch(BaseModel):
    """PATCH /sessions/{id}：只更新 body 中显式传入的字段。"""

    tags: list[str] | None = None
    brief: str | None = None
    group_id: int | None = None
    # T-S1.17：显式传入才更新；非空值须存在且同用户，否则 404
    client_id: int | None = None


class ClientCreate(BaseModel):
    """POST /clients：name 必填，其余可选。"""

    name: str
    code: str | None = None
    gender: str | None = None
    age: int | None = None
    phone: str | None = None
    emergency_contact: str | None = None
    emergency_phone: str | None = None
    start_date: str | None = None
    status: str | None = None
    note: str | None = None


class ClientPatch(BaseModel):
    """PATCH /clients/{id}：只更新显式传入字段（model_fields_set 口径）。"""

    name: str | None = None
    code: str | None = None
    gender: str | None = None
    age: int | None = None
    phone: str | None = None
    emergency_contact: str | None = None
    emergency_phone: str | None = None
    start_date: str | None = None
    status: str | None = None
    note: str | None = None
    session_count_manual: int | None = None


class GroupCreate(BaseModel):
    name: str
    tags: list[str] | None = None
    note: str | None = None


class GroupPatch(BaseModel):
    name: str | None = None
    tags: list[str] | None = None
    note: str | None = None


class BulkDeleteBody(BaseModel):
    session_ids: list[int]


class SegmentPatch(BaseModel):
    text: str


def _settings_of(request: Request) -> Settings:
    return request.app.state.settings


def _session_factory_of(request: Request):
    return request.app.state.session_factory


def _settings_for_clean(settings: Settings) -> Settings:
    """T-S1.5：clean 阶段独立模型配置。

    clean 用 clean_llm_provider/clean_llm_model 构造 LLM。
    clean_llm_model 已在 Settings validator 里解析为 provider 默认模型。
    """
    return settings.model_copy(
        update={
            "llm_provider": settings.clean_llm_provider,
            "llm_model": settings.clean_llm_model,
        }
    )


def _settings_for_record(settings: Settings) -> Settings:
    """T-S1.5b：record 阶段独立模型配置（与 clean 对称）。"""
    return settings.model_copy(
        update={
            "llm_provider": settings.record_llm_provider,
            "llm_model": settings.record_llm_model,
        }
    )


def _get_dev_user_id(request: Request) -> int:
    return request.app.state.settings.dev_user_id


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _open_db(request: Request):
    return request.app.state.session_factory()


def _get_group_or_404(db, group_id: int, user_id: int) -> SessionGroup:
    group = db.get(SessionGroup, group_id)
    if group is None or group.user_id != user_id:
        raise ApiError("not_found", f"分组不存在: {group_id}", http_status=404)
    return group


def _group_payload(group: SessionGroup, member_count: int) -> dict:
    return {
        "group_id": group.id,
        "name": group.name,
        "tags": group.tags or [],
        "note": group.note,
        "created_at": group.created_at.isoformat() if group.created_at else None,
        "member_count": member_count,
    }


# ── T-S1.17 来访者档案 ───────────────────────────────────────────


def _get_client_or_404(db, client_id: int, user_id: int) -> Client:
    client = db.get(Client, client_id)
    if client is None or client.user_id != user_id:
        raise ApiError("not_found", f"来访者不存在: {client_id}", http_status=404)
    return client


def _parse_start_date(value: str | None) -> date | None:
    """YYYY-MM-DD 解析；非法格式抛 422（create/patch 共用）。"""
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ApiError(
            "validation_error",
            f"start_date 非法: {value!r}（须为 YYYY-MM-DD）",
            http_status=422,
        ) from None


def _session_count_auto(db, client_id: int, user_id: int) -> int:
    """来访者名下会话数（所有状态）；与 group 的 member_count 同口径带 user_id。"""
    return (
        db.query(Session)
        .filter(Session.user_id == user_id, Session.client_id == client_id)
        .count()
    )


def _client_payload(db, client: Client, user_id: int) -> dict:
    auto = _session_count_auto(db, client.id, user_id)
    return {
        "client_id": client.id,
        "code": client.code,
        "name": client.name,
        "gender": client.gender,
        "age": client.age,
        "phone": client.phone,
        "emergency_contact": client.emergency_contact,
        "emergency_phone": client.emergency_phone,
        "status": client.status,
        "start_date": client.start_date.isoformat() if client.start_date else None,
        "session_count_manual": client.session_count_manual,
        "session_count_auto": auto,
        "session_count": (
            client.session_count_manual if client.session_count_manual is not None else auto
        ),
        "note": client.note,
    }


def _check_client_name_unique(db, user_id: int, name: str, exclude_id: int | None = None) -> None:
    """同用户名查重（建/PATCH 重名共用），精确匹配，不 trim 语义差异。"""
    query = db.query(Client).filter(Client.user_id == user_id, Client.name == name)
    if exclude_id is not None:
        query = query.filter(Client.id != exclude_id)
    if query.first() is not None:
        raise ApiError("validation_error", f"来访者姓名重复: {name}", http_status=422)


def _session_detail_data(db, session: Session) -> dict:
    """构造 GET /sessions/{id} 与导出共用的会话详情 payload。"""
    pipeline_mode = session.pipeline_mode or PipelineMode.ASR
    is_omni = pipeline_mode == PipelineMode.OMNI
    client_name = None
    if session.client_id is not None:
        client = db.get(Client, session.client_id)
        client_name = client.name if client is not None else None
    segments = [
        {
            "seq": seg.seq,
            "speaker": seg.speaker,
            "role": seg.role,
            "role_label": seg.role_label,
            "cleaned_content": seg.cleaned_content,
            "content": seg.content,
            # omni 无时间戳，API 返回 null（前端不渲染时间行）
            "start_ms": None if is_omni else seg.start_ms,
            "end_ms": None if is_omni else seg.end_ms,
            "confidence": seg.confidence,
        }
        for seg in get_segments(db, session.id)
    ]
    # cleaned_text：直接读会话落库的清理结果（清理阶段写入）
    data = {
        "session_id": session.id,
        "status": session.status,
        "mode": session.mode,
        "pipeline_mode": pipeline_mode,
        "model_display": _MODEL_DISPLAY.get(pipeline_mode, _MODEL_DISPLAY[PipelineMode.ASR]),
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "audio_path": session.audio_path,
        "segments": segments,
        "cleaned_text": session.cleaned_text,
        # T-S1.11：记录元数据（标签/摘要/分组）
        "tags": session.tags or [],
        "brief": session.brief,
        "group_id": session.group_id,
        # T-S1.17：来访者档案关联
        "client_id": session.client_id,
        "client_name": client_name,
        "record": None,
    }

    record = (
        db.query(Record)
        .filter(Record.session_id == session.id)
        .order_by(Record.id.desc())
        .first()
    )
    if record is not None:
        data["record"] = {
            "record_id": record.id,
            "summary": record.summary,
            "counselor_work": record.therapist_work,
            "client_reported_topics": record.basic_info.get("client_reported_topics", []),
            "basic_info": record.basic_info,
            "status": record.status,
        }
    return data


def _hard_delete_session(db, session: Session, user_id: int) -> int:
    """T-S1.13：单会话硬删级联（行 + 音频文件），供单删/组联删/批量删复用。

    与 delete_session 原行为一致：删 segments/records/jobs/sessions 行，
    commit 后 unlink 音频文件。返回被删 session_id；非本人会话抛 404。
    """
    if session is None or session.user_id != user_id:
        raise ApiError("not_found", "会话不存在", http_status=404)

    session_id = session.id
    audio_path = session.audio_path
    db.query(Segment).filter(Segment.session_id == session_id).delete(
        synchronize_session=False
    )
    db.query(Record).filter(Record.session_id == session_id).delete(
        synchronize_session=False
    )
    db.query(Job).filter(Job.session_id == session_id).delete(
        synchronize_session=False
    )
    db.delete(session)
    db.commit()
    if audio_path:
        Path(audio_path).unlink(missing_ok=True)
    return session_id


@router.post("/sessions")
async def create_session(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    mode: str = Form(PipelineMode.OMNI),
):
    """上传音频 → 校验 → 随机名落盘 → 建 sessions 行 → 起后台任务。

    T-S1.6：mode 可选（默认 omni）。omni=qwen3.5-omni-plus 多模态直转；
    asr=paraformer-v2 + clean/record（deepseek）三段管线。
    返回 {session_id, status=uploading}；后台任务接续 transcribing → done/failed。
    会话可重交：复用本端点，重建 job 行并幂等清空旧 segments。
    T-S1.1 起不再接收说话人映射参数（多余表单字段忽略）。
    """
    if mode not in (PipelineMode.OMNI, PipelineMode.ASR):
        raise ApiError(
            "validation_error",
            f"mode 非法: {mode!r}（可选值: 'omni' / 'asr'）",
            http_status=400,
        )

    settings = _settings_of(request)
    audio_dir = Path(settings.data_dir) / "audio"

    original_filename = file.filename
    suffix = validate_audio_ext(original_filename)
    # 大小在流式写入途中校验（超限中断并 413），不需要二次 stat
    audio_path = await save_upload_to_audio_dir(file, audio_dir, suffix)
    # T-S1.11：ffprobe 探测时长（失败兜底 0，不阻塞上传），在建行前同步完成
    duration_sec = probe_duration_seconds(audio_path)

    db = _open_db(request)
    try:
        session = Session(
            user_id=_get_dev_user_id(request),
            client_id=None,
            mode=SessionMode.IN_PERSON,
            pipeline_mode=mode,
            status=SessionStatus.UPLOADING,
            started_at=_now(),
            duration_sec=duration_sec,
            audio_path=audio_path,
            original_filename=original_filename,
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        session_id = session.id

        if mode == PipelineMode.OMNI:
            record_settings = _settings_for_record(settings)
            record_llm = get_llm_provider(record_settings)
            omni = QwenOmniLLM(api_key=settings.dashscope_api_key)
            background_tasks.add_task(
                run_background_pipeline,
                session_id,
                _session_factory_of(request),
                settings,
                audio_path,
                None,
                None,
                record_llm,
                pipeline_mode=PipelineMode.OMNI,
                omni=omni,
                record_settings=record_settings,
            )
        else:
            # T-S1.5：clean 独立走 clean_llm_provider，record 独立走 record_llm_provider（默认均 deepseek）。
            # 保持历史调用顺序：先 clean、后 record（测试与工厂语义依赖）。
            asr = get_asr_provider(settings)
            clean_llm = get_llm_provider(_settings_for_clean(settings))
            record_settings = _settings_for_record(settings)
            record_llm = get_llm_provider(record_settings)
            background_tasks.add_task(
                run_background_pipeline,
                session_id,
                _session_factory_of(request),
                settings,
                audio_path,
                asr,
                clean_llm,
                record_llm,
                pipeline_mode=PipelineMode.ASR,
                record_settings=record_settings,
            )
        return ok({"session_id": session_id, "status": SessionStatus.UPLOADING})
    except Exception:
        # 落库/起任务异常时清掉已落盘音频（避免孤儿文件残留）
        Path(audio_path).unlink(missing_ok=True)
        raise
    finally:
        db.close()


@router.get("/sessions/{session_id}")
def get_session(request: Request, session_id: int):
    """会话详情：状态 + segments（按 seq，含代号/角色/清理文本）+ record（若有）。"""
    db = _open_db(request)
    try:
        session = db.get(Session, session_id)
        user_id = _get_dev_user_id(request)
        if session is None or session.user_id != user_id:
            raise ApiError("not_found", f"会话不存在: {session_id}", http_status=404)
        return ok(_session_detail_data(db, session))
    finally:
        db.close()


@router.get("/sessions")
def list_sessions(request: Request):
    """会话列表（dev 用户）：id/status/时间 + T-S1.11 富化字段。"""
    db = _open_db(request)
    try:
        user_id = _get_dev_user_id(request)
        rows = (
            db.query(Session)
            .filter(Session.user_id == user_id)
            .order_by(Session.started_at.desc())
            .all()
        )
        groups = db.query(SessionGroup).filter(SessionGroup.user_id == user_id).all()
        group_names = {g.id: g.name for g in groups}
        clients = db.query(Client).filter(Client.user_id == user_id).all()
        client_names = {c.id: c.name for c in clients}
        return ok(
            {
                "sessions": [
                    {
                        "session_id": s.id,
                        "status": s.status,
                        "started_at": s.started_at.isoformat() if s.started_at else None,
                        "original_filename": s.original_filename,
                        "duration_sec": s.duration_sec,
                        "word_count": len(s.cleaned_text or ""),
                        "tags": s.tags or [],
                        "brief": s.brief,
                        "group_id": s.group_id,
                        "group_name": group_names.get(s.group_id),
                        "client_id": s.client_id,
                        "client_name": client_names.get(s.client_id),
                    }
                    for s in rows
                ]
            }
        )
    finally:
        db.close()


# ── T-S1.15 工作台统计 ──────────────────────────────────────────


def _week_start(dt: datetime) -> datetime:
    """本周一 00:00（本地服务器时间，与 datetime.now 口径一致）。"""
    return (dt - timedelta(days=dt.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def _dashboard_summary_data(db, user_id: int) -> dict:
    """聚合工作台 KPI + 数据看板（单用户全量内存聚合，S0 数据量足够）。"""
    now = datetime.now()
    week_start = _week_start(now)
    prev_week_start = week_start - timedelta(days=7)

    sessions = db.query(Session).filter(Session.user_id == user_id).all()
    groups_count = (
        db.query(SessionGroup).filter(SessionGroup.user_id == user_id).count()
    )

    def _count_week(start: datetime) -> tuple[int, int]:
        """返回 (窗口内会话数, 窗口内总时长秒数)，窗口 = [start, start+7天)。"""
        end = start + timedelta(days=7)
        total_sec = 0
        count = 0
        for s in sessions:
            if s.started_at is not None and start <= s.started_at < end:
                count += 1
                total_sec += s.duration_sec or 0
        return count, total_sec

    week_count, week_sec = _count_week(week_start)
    prev_count, prev_sec = _count_week(prev_week_start)

    # status_dist：processing = 所有非 done/failed 中间态之和；顺序固定。
    done_count = sum(1 for s in sessions if s.status == SessionStatus.DONE)
    failed_count = sum(1 for s in sessions if s.status == SessionStatus.FAILED)
    processing_count = len(sessions) - done_count - failed_count

    # tag_cloud：tags 数组展开词频，降序 Top 20（同频按标签名升序保证稳定）。
    tag_counter: dict[str, int] = {}
    for s in sessions:
        for tag in s.tags or []:
            if isinstance(tag, str) and tag:
                tag_counter[tag] = tag_counter.get(tag, 0) + 1
    tag_cloud = [
        {"tag": tag, "count": count}
        for tag, count in sorted(
            tag_counter.items(), key=lambda item: (-item[1], item[0])
        )[:20]
    ]

    # trend：近 14 天（含今天）逐日聚合，无记录日期补 0，日期升序。
    today = now.date()
    days = [today - timedelta(days=offset) for offset in range(13, -1, -1)]
    day_set = set(days)
    trend_map: dict[date, list[int]] = {d: [0, 0] for d in days}
    for s in sessions:
        if s.started_at is not None:
            d = s.started_at.date()
            if d in day_set:
                trend_map[d][0] += s.duration_sec or 0
                trend_map[d][1] += 1

    # todos：no_brief / no_tags 只统计 done；failed 单独计。
    no_brief = sum(
        1
        for s in sessions
        if s.status == SessionStatus.DONE and not (s.brief or "").strip()
    )
    no_tags = sum(
        1
        for s in sessions
        if s.status == SessionStatus.DONE and not (s.tags or [])
    )

    return {
        "week": {
            "start": week_start.date().isoformat(),
            "end": (week_start + timedelta(days=6)).date().isoformat(),
            "sessions": week_count,
            "sessions_prev": prev_count,
            "hours": round(week_sec / 3600, 1) if week_count else 0,
            "hours_prev": round(prev_sec / 3600, 1) if prev_count else 0,
            "avg_minutes": round(week_sec / 60 / week_count, 1) if week_count else 0,
            "avg_minutes_prev": round(prev_sec / 60 / prev_count, 1) if prev_count else 0,
        },
        "totals": {"sessions": len(sessions), "groups": groups_count},
        "status_dist": [
            {"status": "done", "label": "完成", "count": done_count},
            {"status": "processing", "label": "处理中", "count": processing_count},
            {"status": "failed", "label": "失败", "count": failed_count},
        ],
        "tag_cloud": tag_cloud,
        "trend": [
            {
                "date": d.isoformat(),
                "minutes": round(trend_map[d][0] / 60, 1),
                "sessions": trend_map[d][1],
            }
            for d in days
        ],
        "todos": {
            "no_brief": no_brief,
            "no_tags": no_tags,
            "failed": failed_count,
        },
    }


@router.get("/dashboard/summary")
def dashboard_summary(request: Request):
    """T-S1.15：工作台单端点聚合（KPI + 状态分布 + 词云 + 趋势 + 待办）。"""
    db = _open_db(request)
    try:
        return ok(_dashboard_summary_data(db, _get_dev_user_id(request)))
    finally:
        db.close()


@router.post("/sessions/bulk-delete")
def bulk_delete_sessions(request: Request, body: BulkDeleteBody):
    """T-S1.13：批量硬删会话；空列表 422，不存在/非本人 id 记入 missing。"""
    if not body.session_ids:
        raise ApiError("validation_error", "session_ids 不能为空", http_status=422)

    db = _open_db(request)
    try:
        user_id = _get_dev_user_id(request)
        deleted: list[int] = []
        missing: list[int] = []
        for session_id in body.session_ids:
            session = db.get(Session, session_id)
            if session is None or session.user_id != user_id:
                missing.append(session_id)
                continue
            deleted.append(_hard_delete_session(db, session, user_id))
        return ok({"deleted": deleted, "missing": missing})
    finally:
        db.close()


@router.get("/export/sessions")
def export_sessions(request: Request):
    """T-S1.13：全量导出当前用户会话详情（started_at 倒序）。"""
    db = _open_db(request)
    try:
        user_id = _get_dev_user_id(request)
        sessions = (
            db.query(Session)
            .filter(Session.user_id == user_id)
            .order_by(Session.started_at.desc())
            .all()
        )
        groups = db.query(SessionGroup).filter(SessionGroup.user_id == user_id).all()
        group_names = {g.id: g.name for g in groups}

        payload = []
        for session in sessions:
            item = _session_detail_data(db, session)
            item["original_filename"] = session.original_filename
            item["duration_sec"] = session.duration_sec
            item["group_name"] = group_names.get(session.group_id)
            payload.append(item)
        return ok(
            {
                "exported_at": _now().isoformat(),
                "count": len(payload),
                "sessions": payload,
            }
        )
    finally:
        db.close()


@router.patch("/sessions/{session_id}")
def patch_session(
    request: Request, session_id: int, patch: SessionPatch | None = None
):
    """T-S1.11：编辑记录元数据（tags/brief/group_id），只更新传入字段。"""
    patch = patch or SessionPatch()
    db = _open_db(request)
    try:
        session = db.get(Session, session_id)
        user_id = _get_dev_user_id(request)
        if session is None or session.user_id != user_id:
            raise ApiError("not_found", f"会话不存在: {session_id}", http_status=404)

        fields = patch.model_fields_set
        if "brief" in fields:
            if patch.brief is not None and len(patch.brief) > 100:
                raise ApiError(
                    "validation_error", "brief 不能超过 100 字", http_status=422
                )
            session.brief = patch.brief
        if "tags" in fields:
            session.tags = patch.tags
        if "group_id" in fields:
            if patch.group_id is None:
                session.group_id = None
            else:
                _get_group_or_404(db, patch.group_id, user_id)
                session.group_id = patch.group_id
        if "client_id" in fields:
            if patch.client_id is None:
                session.client_id = None
            else:
                _get_client_or_404(db, patch.client_id, user_id)
                session.client_id = patch.client_id

        db.commit()
        db.refresh(session)
        return ok(
            {
                "session_id": session.id,
                "tags": session.tags or [],
                "brief": session.brief,
                "group_id": session.group_id,
                "client_id": session.client_id,
            }
        )
    finally:
        db.close()


@router.patch("/sessions/{session_id}/segments/{seq}")
def patch_segment(request: Request, session_id: int, seq: int, body: SegmentPatch):
    """T-S1.13：精确编辑转写段（表格视图）——只改 cleaned_content，原文保留。"""
    text = body.text
    if not text.strip():
        raise ApiError("validation_error", "text 不能为空或纯空白", http_status=422)

    db = _open_db(request)
    try:
        user_id = _get_dev_user_id(request)
        session = db.get(Session, session_id)
        if session is None or session.user_id != user_id:
            raise ApiError("not_found", f"会话不存在: {session_id}", http_status=404)

        segment = (
            db.query(Segment)
            .filter(Segment.session_id == session_id, Segment.seq == seq)
            .first()
        )
        if segment is None:
            raise ApiError("not_found", f"转写段不存在: seq={seq}", http_status=404)

        segment.cleaned_content = text
        db.flush()
        session.cleaned_text = build_cleaned_text(db, session_id)
        db.commit()
        db.refresh(session)
        return ok(
            {
                "session_id": session_id,
                "seq": seq,
                "word_count": len(session.cleaned_text or ""),
            }
        )
    finally:
        db.close()


@router.delete("/sessions/{session_id}")
def delete_session(request: Request, session_id: int):
    """T-S1.11：硬删会话（segments/records/jobs/sessions 行 + 音频文件）。"""
    db = _open_db(request)
    try:
        session = db.get(Session, session_id)
        user_id = _get_dev_user_id(request)
        if session is None or session.user_id != user_id:
            raise ApiError("not_found", f"会话不存在: {session_id}", http_status=404)
        return ok({"deleted": _hard_delete_session(db, session, user_id)})
    finally:
        db.close()


@router.get("/clients")
def list_clients(request: Request):
    """T-S1.17：来访者列表，active 优先 + start_date 降序（无日期按 id 降序兜底）。

    每条含档案全字段 + session_count_auto/session_count（手工值优先）。
    """
    db = _open_db(request)
    try:
        user_id = _get_dev_user_id(request)
        rows = (
            db.query(Client)
            .filter(Client.user_id == user_id)
            .order_by(
                (Client.status == ClientStatus.ACTIVE).desc(),
                Client.start_date.desc(),
                Client.id.desc(),
            )
            .all()
        )
        return ok({"clients": [_client_payload(db, c, user_id) for c in rows]})
    finally:
        db.close()


@router.post("/clients")
def create_client(request: Request, body: ClientCreate):
    """新建来访者；name 空/同用户重名 → 422；start_date 非法 → 422。

    未传 code 时自动生成 `C+client_id` 回填。
    """
    db = _open_db(request)
    try:
        user_id = _get_dev_user_id(request)
        name = body.name.strip()
        if not name:
            raise ApiError("validation_error", "来访者姓名不能为空", http_status=422)
        _check_client_name_unique(db, user_id, name)

        start_date = _parse_start_date(body.start_date)
        status = body.status if body.status is not None else ClientStatus.ACTIVE
        if status not in _CLIENT_STATUSES:
            raise ApiError(
                "validation_error",
                f"status 非法: {status!r}（可选值: 'active' / 'disabled'）",
                http_status=422,
            )

        client = Client(
            user_id=user_id,
            code=(body.code or "").strip(),
            name=name,
            gender=body.gender,
            age=body.age,
            phone=body.phone,
            emergency_contact=body.emergency_contact,
            emergency_phone=body.emergency_phone,
            start_date=start_date,
            status=status,
            note=body.note,
        )
        db.add(client)
        db.commit()
        db.refresh(client)
        # 未传 code 时后端回填 C+client_id
        if not client.code:
            client.code = f"C{client.id}"
            db.commit()
            db.refresh(client)
        return ok(_client_payload(db, client, user_id))
    finally:
        db.close()


@router.patch("/clients/{client_id}")
def patch_client(request: Request, client_id: int, body: ClientPatch | None = None):
    """编辑来访者：只更新显式传入字段；name 重名/非法 status → 422。"""
    body = body or ClientPatch()
    db = _open_db(request)
    try:
        user_id = _get_dev_user_id(request)
        client = _get_client_or_404(db, client_id, user_id)

        fields = body.model_fields_set
        if "name" in fields:
            name = (body.name or "").strip()
            if not name:
                raise ApiError("validation_error", "来访者姓名不能为空", http_status=422)
            _check_client_name_unique(db, user_id, name, exclude_id=client_id)
            client.name = name
        if "code" in fields:
            client.code = (body.code or "").strip() or f"C{client.id}"
        if "gender" in fields:
            client.gender = body.gender
        if "age" in fields:
            client.age = body.age
        if "phone" in fields:
            client.phone = body.phone
        if "emergency_contact" in fields:
            client.emergency_contact = body.emergency_contact
        if "emergency_phone" in fields:
            client.emergency_phone = body.emergency_phone
        if "start_date" in fields:
            client.start_date = _parse_start_date(body.start_date)
        if "session_count_manual" in fields:
            client.session_count_manual = body.session_count_manual
        if "status" in fields:
            status = body.status
            if status not in _CLIENT_STATUSES:
                raise ApiError(
                    "validation_error",
                    f"status 非法: {status!r}（可选值: 'active' / 'disabled'）",
                    http_status=422,
                )
            client.status = status
        if "note" in fields:
            client.note = body.note

        db.commit()
        db.refresh(client)
        return ok(_client_payload(db, client, user_id))
    finally:
        db.close()


@router.delete("/clients/{client_id}")
def delete_client(request: Request, client_id: int):
    """硬删来访者；名下会话 client_id 置 null（记录保留）。"""
    db = _open_db(request)
    try:
        user_id = _get_dev_user_id(request)
        client = _get_client_or_404(db, client_id, user_id)
        affected = (
            db.query(Session)
            .filter(Session.user_id == user_id, Session.client_id == client_id)
            .update({"client_id": None}, synchronize_session=False)
        )
        db.delete(client)
        db.commit()
        return ok({"deleted": client_id, "affected_sessions": affected})
    finally:
        db.close()


# ── T-S1.11 分组 CRUD ──────────────────────────────────────────


@router.get("/groups")
def list_groups(request: Request):
    """分组列表：created_at 倒序，含组内会话数。"""
    db = _open_db(request)
    try:
        user_id = _get_dev_user_id(request)
        groups = (
            db.query(SessionGroup)
            .filter(SessionGroup.user_id == user_id)
            .order_by(SessionGroup.created_at.desc())
            .all()
        )
        payload = []
        for group in groups:
            member_count = (
                db.query(Session)
                .filter(Session.user_id == user_id, Session.group_id == group.id)
                .count()
            )
            payload.append(_group_payload(group, member_count))
        return ok({"groups": payload})
    finally:
        db.close()


@router.post("/groups")
def create_group(request: Request, body: GroupCreate):
    """新建分组；name 空或同用户内重名 → 422。"""
    db = _open_db(request)
    try:
        user_id = _get_dev_user_id(request)
        name = body.name.strip()
        if not name:
            raise ApiError("validation_error", "组名不能为空", http_status=422)
        exists = (
            db.query(SessionGroup)
            .filter(SessionGroup.user_id == user_id, SessionGroup.name == name)
            .first()
        )
        if exists is not None:
            raise ApiError("validation_error", f"组名重复: {name}", http_status=422)

        group = SessionGroup(
            user_id=user_id,
            name=name,
            tags=body.tags,
            note=body.note,
            created_at=_now(),
        )
        db.add(group)
        db.commit()
        db.refresh(group)
        return ok(_group_payload(group, 0))
    finally:
        db.close()


@router.patch("/groups/{group_id}")
def patch_group(request: Request, group_id: int, body: GroupPatch | None = None):
    """编辑分组 name/tags/note。"""
    body = body or GroupPatch()
    db = _open_db(request)
    try:
        user_id = _get_dev_user_id(request)
        group = _get_group_or_404(db, group_id, user_id)

        fields = body.model_fields_set
        if "name" in fields:
            name = (body.name or "").strip()
            if not name:
                raise ApiError("validation_error", "组名不能为空", http_status=422)
            exists = (
                db.query(SessionGroup)
                .filter(
                    SessionGroup.user_id == user_id,
                    SessionGroup.name == name,
                    SessionGroup.id != group_id,
                )
                .first()
            )
            if exists is not None:
                raise ApiError("validation_error", f"组名重复: {name}", http_status=422)
            group.name = name
        if "tags" in fields:
            group.tags = body.tags
        if "note" in fields:
            group.note = body.note

        db.commit()
        db.refresh(group)
        member_count = (
            db.query(Session)
            .filter(Session.user_id == user_id, Session.group_id == group.id)
            .count()
        )
        return ok(_group_payload(group, member_count))
    finally:
        db.close()


@router.delete("/groups/{group_id}")
def delete_group(request: Request, group_id: int, mode: str = "dissolve"):
    """T-S1.13：删除分组双模式。

    dissolve（默认，向后兼容）：组内 sessions 的 group_id 置 null，记录保留；
    with_records：先按单会话硬删级联清空组内每个会话，再删组。
    """
    if mode not in ("dissolve", "with_records"):
        raise ApiError(
            "validation_error",
            f"mode 非法: {mode!r}（可选值: 'dissolve' / 'with_records'）",
            http_status=422,
        )

    db = _open_db(request)
    try:
        user_id = _get_dev_user_id(request)
        group = _get_group_or_404(db, group_id, user_id)

        members = (
            db.query(Session)
            .filter(Session.user_id == user_id, Session.group_id == group_id)
            .all()
        )
        deleted_sessions: list[int] = []
        if mode == "dissolve":
            db.query(Session).filter(
                Session.user_id == user_id, Session.group_id == group_id
            ).update({"group_id": None}, synchronize_session=False)
        else:
            for session in members:
                deleted_sessions.append(_hard_delete_session(db, session, user_id))

        db.delete(group)
        db.commit()
        return ok(
            {
                "deleted": group_id,
                "mode": mode,
                "deleted_sessions": deleted_sessions,
            }
        )
    finally:
        db.close()
