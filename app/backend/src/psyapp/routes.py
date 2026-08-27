"""S0 主链路 REST 路由：POST /sessions（上传+后台任务）、GET 会话查询。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, Request, UploadFile

from .audio import save_upload_to_audio_dir, validate_audio_ext
from .config import Settings
from .enums import PipelineMode, SessionMode, SessionStatus
from .models import Record, Session
from .providers import get_asr_provider, get_llm_provider
from .providers.omni import QwenOmniLLM
from .response import ApiError, ok
from .segments import get_segments
from .services import run_background_pipeline

router = APIRouter()

_MODEL_DISPLAY = {
    PipelineMode.OMNI: "qwen3.5-omni-plus",
    PipelineMode.ASR: "paraformer-v2 + deepseek-v4-flash",
}


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

    suffix = validate_audio_ext(file.filename)
    # 大小在流式写入途中校验（超限中断并 413），不需要二次 stat
    audio_path = await save_upload_to_audio_dir(file, audio_dir, suffix)

    db = _open_db(request)
    try:
        session = Session(
            user_id=_get_dev_user_id(request),
            client_id=None,
            mode=SessionMode.IN_PERSON,
            pipeline_mode=mode,
            status=SessionStatus.UPLOADING,
            started_at=_now(),
            duration_sec=0,
            audio_path=audio_path,
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

        pipeline_mode = session.pipeline_mode or PipelineMode.ASR
        is_omni = pipeline_mode == PipelineMode.OMNI
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
            for seg in get_segments(db, session_id)
        ]
        # cleaned_text：直接读会话落库的清理结果（清理阶段写入）
        data = {
            "session_id": session.id,
            "status": session.status,
            "mode": session.mode,
            "pipeline_mode": pipeline_mode,
            "model_display": _MODEL_DISPLAY.get(
                pipeline_mode, _MODEL_DISPLAY[PipelineMode.ASR]
            ),
            "started_at": session.started_at.isoformat() if session.started_at else None,
            "audio_path": session.audio_path,
            "segments": segments,
            "cleaned_text": session.cleaned_text,
            "record": None,
        }

        record = (
            db.query(Record)
            .filter(Record.session_id == session_id)
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
        return ok(data)
    finally:
        db.close()


@router.get("/sessions")
def list_sessions(request: Request):
    """会话列表（dev 用户）：id/status/时间。"""
    db = _open_db(request)
    try:
        user_id = _get_dev_user_id(request)
        rows = (
            db.query(Session)
            .filter(Session.user_id == user_id)
            .order_by(Session.started_at.desc())
            .all()
        )
        return ok(
            {
                "sessions": [
                    {
                        "session_id": s.id,
                        "status": s.status,
                        "started_at": s.started_at.isoformat() if s.started_at else None,
                    }
                    for s in rows
                ]
            }
        )
    finally:
        db.close()
