"""会话处理服务：S0 最简主链路后台任务（转写 → 清理 → 记录生成）。

任务卡路线决策：
- 后台执行：FastAPI BackgroundTasks 跑一个任务函数串行执行三段；不引队列中间件。
- jobs 表记录形态：每个会话三个阶段各一行（type=transcribe/clean/record），
  每行独立记录 provider 与状态/错误，便于故障定位与追溯。
- 清理阶段（T-S1.3 起）按语义重拼段落：≤60 段单次调用，>60 段分块调用；
  每块独立判定角色，坏 JSON/校验失败重试 1 次，任一块仍失败则整体失败。
  T-S1.5 起 clean 阶段走 clean_llm_provider（默认 deepseek）+ clean prompt v4；
  T-S1.5b 起 record 阶段走 record_llm_provider（默认 deepseek），record prompt v2 不变。
- 会话状态机最小版：uploading（创建即写）→ transcribing（后台开始）→ done/failed。
  失败时对应 job.error 记原因；会话可重交（复用 POST /sessions，幂等清空旧 segments）。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from .config import Settings
from .enums import JobType, PipelineMode, Role, SessionStatus
from .jobs import add_job, mark_job_done, mark_job_failed, mark_job_running
from .models import Record, Segment, Session
from .prompts import render_prompt
from .providers.omni import OMNI_TRANSCRIBE_PROMPT, parse_omni_transcript
from .segments import (
    apply_omni_segments_to_session,
    apply_segments_to_session,
    build_cleaned_text,
    build_transcript_lines_from_segments,
    clear_segments,
    get_segments,
)

logger = logging.getLogger(__name__)

# T-S1.3 分块阈值：≤60 段走单次调用（现状路径），>60 段分块，每块 ≤50 段。
CLEAN_SINGLE_CALL_LIMIT = 60
CLEAN_CHUNK_SIZE = 50


def run_background_pipeline(
    session_id: int,
    session_factory: Any,
    settings: Settings,
    audio_path: str,
    asr: Any,
    clean_llm: Any,
    record_llm: Any,
    *,
    pipeline_mode: str = PipelineMode.ASR,
    omni: Any = None,
    record_settings: Settings | None = None,
) -> None:
    """S0 主链路后台任务：按 pipeline_mode 分叉执行。

    - asr（现状完全不变）：转写 → segments 落库 → 清理+角色判定 → 记录生成。
    - omni（T-S1.6）：qwen3.5-omni-plus 直转（转写+清理+角色判定一步到位）
      → segments 落库 → 记录生成（deepseek，输入=按 segments 拼的清理稿）。
      无 clean 阶段，不建 clean job。

    幂等：支持同一会话重交（失败/无 segments 时重跑，旧 segments 先清空）。
    任一阶段异常都捕获 → session.status=failed，对应 job.error 记原因。

    asr/clean_llm/record_llm 为 provider 实例；测试可传 fake，生产由工厂创建。
    omni 为 QwenOmniLLM 实例（omni 模式必传）。
    record_settings：record 阶段独立模型设置（T-S1.5b，deepseek），用于 store_record
    如实落库 provider/model；缺省时回退为全局 settings（旧调用方/直连测试）。
    """
    if record_settings is None:
        record_settings = settings
    db = session_factory()

    if pipeline_mode == PipelineMode.OMNI:
        _run_omni_pipeline(
            db,
            session_id,
            settings,
            audio_path,
            omni,
            record_llm,
            record_settings,
        )
        return

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
        db, session_id, record_job, record_settings, cleaned_text, record_llm
    )
    if record_data is None:
        _set_session_status(db, session_id, SessionStatus.FAILED)
        db.close()
        return

    _set_session_status(db, session_id, SessionStatus.DONE)
    db.close()


def _run_omni_pipeline(
    db,
    session_id: int,
    settings: Settings,
    audio_path: str,
    omni: Any,
    record_llm: Any,
    record_settings: Settings,
) -> None:
    """omni 路径：直转（重试 1 次）→ segments 落库 → 记录生成（deepseek）。

    - transcribe job 内调 QwenOmniLLM.transcribe_audio，provider 记 qwen3.5-omni-plus。
    - raw_transcript 存 omni 原始输出；解析出 0 轮视为失败并重试 1 次。
    - 无 clean 阶段（不建 clean job）；record 阶段与 asr 路径完全一致。
    """
    if omni is None:
        raise RuntimeError("omni 模式缺少 omni provider")

    transcribe_job = add_job(db, session_id, JobType.TRANSCRIBE, omni.name)
    db.commit()
    _set_session_status(db, session_id, SessionStatus.TRANSCRIBING)

    last_error: str | None = None
    for attempt in (1, 2):
        try:
            mark_job_running(db, transcribe_job.id)
            raw_text = omni.transcribe_audio(audio_path, OMNI_TRANSCRIBE_PROMPT)
            session = db.get(Session, session_id)
            if session is not None:
                session.raw_transcript = raw_text
                db.commit()
            segments = parse_omni_transcript(raw_text)
            if not segments:
                raise RuntimeError("omni 输出解析出 0 轮")
            apply_omni_segments_to_session(
                db, session_id, settings.dev_user_id, segments
            )
            db.commit()
            mark_job_done(db, transcribe_job.id)
            break
        except Exception as exc:  # noqa: BLE001 —— 主链路任何失败都收敛为 failed
            last_error = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "会话 %s omni 转写失败（第 %d 次）: %s", session_id, attempt, exc
            )
    else:
        mark_job_failed(
            db, transcribe_job.id, f"omni 转写失败（重试后仍失败）: {last_error}"
        )
        _set_session_status(db, session_id, SessionStatus.FAILED)
        db.close()
        return

    # 清理稿：omni 无 clean 阶段，直接按 segments 拼（record 阶段输入，同 asr 语义）
    cleaned_text = build_cleaned_text(db, session_id)
    session = db.get(Session, session_id)
    if session is not None:
        session.cleaned_text = cleaned_text
    db.commit()

    # ── 记录（同 asr：deepseek，坏 JSON 重试 1 次，成功落库）──────
    record_job = add_job(db, session_id, JobType.RECORD, record_llm.name)
    db.commit()
    record_data = _generate_record(
        db, session_id, record_job, record_settings, cleaned_text, record_llm
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
    """口语清理 + 角色判定 + 语义重拼。

    - 清理前把原始转写稿写入 sessions.raw_transcript（审计底稿，失败也保留）。
    - ≤60 段单次调用（现状路径）；>60 段分块（每块 ≤50 段、按说话人轮换边界切）。
    - 每块独立调用 clean v4 并校验；角色以首次出现块的判定为准；
      输入每块带全局 seq 编号（T-S1.4），模型逐字引用，source_seqs 直接拼接到全局。
    - 任一块重试 1 次后仍失败 → 整个 clean 失败（job.error 记原因，返回 None）。
    - 成功时用重组后的 paragraphs 替换 segments，并返回 cleaned_text 供 record 阶段。
    """
    segments = get_segments(db, session_id)
    if not segments:
        mark_job_failed(db, job.id, "清理输入为空：没有可清理的转写文本")
        return None

    # 审计底稿：清理前的原始转写稿先落库（后续 clean 失败也不丢）
    session = db.get(Session, session_id)
    if session is not None:
        session.raw_transcript = build_transcript_lines_from_segments(segments)
        db.commit()

    chunks = _split_clean_chunks(segments)
    merged_roles: dict[str, dict[str, str]] = {}
    merged_paragraphs: list[dict[str, Any]] = []

    try:
        for _chunk_start, chunk_segments in chunks:
            transcript = build_transcript_lines_from_segments(chunk_segments)
            roles, paragraphs = _clean_chunk_with_retry(
                db, job, settings, clean_llm, transcript, chunk_segments
            )
            # 角色冲突时以首次出现块的判定为准
            for code, info in roles.items():
                if code not in merged_roles:
                    merged_roles[code] = info
            for para in paragraphs:
                merged_paragraphs.append(
                    {
                        "speaker": para["speaker"],
                        # T-S1.4：输入显式带全局 seq，模型直接引用；不再做 +chunk_start 偏移
                        "source_seqs": list(para["source_seqs"]),
                        "text": para["text"],
                    }
                )

        _replace_segments_with_paragraphs(db, session_id, merged_roles, merged_paragraphs)
        mark_job_done(db, job.id)
        return build_cleaned_text(db, session_id)
    except Exception as exc:  # noqa: BLE001
        message = str(exc)
        if "清理失败" not in message:
            message = f"清理失败: {message}"
        mark_job_failed(db, job.id, message)
        return None


def _clean_chunk_with_retry(
    db,
    job,
    settings: Settings,
    clean_llm: Any,
    transcript: str,
    chunk_segments: list[Segment],
) -> tuple[dict[str, dict[str, str]], list[dict[str, Any]]]:
    """单个分块调用 clean v4，坏 JSON/校验失败重试 1 次；仍失败抛 ValueError。"""
    prompt = render_prompt("clean", settings=settings, transcript=transcript)
    last_error: str | None = None
    for attempt in (1, 2):
        try:
            mark_job_running(db, job.id)
            text = clean_llm.complete(
                [{"role": "user", "content": prompt}], temperature=0.3
            )
            data = parse_clean_json(text)
            return validate_clean_result(data, chunk_segments)
        except Exception as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "会话 %s 清理失败（第 %d 次）: %s", job.session_id, attempt, exc
            )
    raise ValueError(f"清理失败（重试后仍失败）: {last_error}")


def _split_clean_chunks(segments: list[Segment]) -> list[tuple[int, list[Segment]]]:
    """按阈值切分待清理 segments。

    - ≤60 段：单块（现状路径）。
    - >60 段：每块 ≤50 段；优先在说话人轮换边界（连续同人 run 之间）切块，
      连续同人超过 50 段时硬切。
    返回 [(chunk_start_seq, chunk_segments), ...]，chunk_start_seq 为全局起始 seq。
    """
    if len(segments) <= CLEAN_SINGLE_CALL_LIMIT:
        return [(segments[0].seq, segments)]

    runs: list[list[Segment]] = []
    for seg in segments:
        if not runs or runs[-1][-1].speaker != seg.speaker:
            runs.append([seg])
        else:
            runs[-1].append(seg)

    chunks: list[list[Segment]] = []
    current: list[Segment] = []
    for run in runs:
        if len(run) > CLEAN_CHUNK_SIZE:
            if current:
                chunks.append(current)
                current = []
            # 硬切：同一人连续发言超过 50 段
            for i in range(0, len(run), CLEAN_CHUNK_SIZE):
                chunks.append(run[i : i + CLEAN_CHUNK_SIZE])
        elif not current or len(current) + len(run) <= CLEAN_CHUNK_SIZE:
            current.extend(run)
        else:
            chunks.append(current)
            current = list(run)
    if current:
        chunks.append(current)

    return [(chunk[0].seq, chunk) for chunk in chunks]


def parse_clean_json(text: str) -> dict[str, Any]:
    """解析 clean v4 的 JSON（roles + paragraphs）。

    可剥 ```json 围栏；顶层必须是对象，且含 roles（dict）与 paragraphs（list）。
    角色值/代号覆盖/source_seqs 覆盖的校验在 validate_clean_result 里做。
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
    paragraphs = data.get("paragraphs")
    if not isinstance(roles, dict) or not roles:
        raise ValueError("roles 缺失或非对象")
    if not isinstance(paragraphs, list):
        raise ValueError("paragraphs 缺失或非数组")
    return data


def validate_clean_result(
    data: dict[str, Any], segments: list[Segment]
) -> tuple[dict[str, dict[str, str]], list[dict[str, Any]]]:
    """校验 clean v4 契约（raise 即视为该次尝试失败），返回 (roles, paragraphs)。

    - roles 键覆盖输入中出现过的全部代号，role ∈ {T, P}，label 非空字符串；
    - 每个 paragraph 的 speaker 是已知代号、text 为非空字符串；
    - 所有 source_seqs 拼接后必须恰好等于输入段的 seq 序列 [seg.seq, …, seg.seq]
      （不重不漏、顺序不减）。T-S1.4：分块输入显式带全局 seq，故以 seg.seq 为准，
      不再假设从 0 连续——但严格覆盖校验本身不变。
    """
    roles = data["roles"]
    paragraphs = data["paragraphs"]
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

    flat_seqs: list[int] = []
    for idx, para in enumerate(paragraphs):
        if not isinstance(para, dict):
            raise ValueError(f"paragraphs[{idx}] 不是对象")
        speaker = para.get("speaker")
        source_seqs = para.get("source_seqs")
        text = para.get("text")
        if not isinstance(speaker, str) or not speaker:
            raise ValueError(f"paragraphs[{idx}].speaker 缺失或非字符串")
        if speaker not in roles:
            raise ValueError(f"paragraphs[{idx}].speaker 未知代号: {speaker!r}")
        if (
            not isinstance(source_seqs, list)
            or not source_seqs
            or not all(isinstance(seq, int) and not isinstance(seq, bool) for seq in source_seqs)
        ):
            raise ValueError(f"paragraphs[{idx}].source_seqs 缺失或非法")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"paragraphs[{idx}].text 缺失或非字符串")
        flat_seqs.extend(source_seqs)

    expected = [seg.seq for seg in segments]
    if flat_seqs != expected:
        raise ValueError(
            f"source_seqs 未覆盖全部输入段落（期望 {expected}，实际 {flat_seqs}）"
        )
    return roles, paragraphs


def _replace_segments_with_paragraphs(
    db,
    session_id: int,
    roles: dict[str, dict[str, str]],
    paragraphs: list[dict[str, Any]],
) -> None:
    """用重组后的 paragraphs 替换旧 segments（清空旧段后重建）。

    - 写入前再次做全局校验（roles 覆盖、source_seqs 恰好覆盖全部段 seq）；
    - 新段 seq 重排为 0..m-1，speaker/role/role_label/cleaned_content 来自 paragraph；
    - start_ms/end_ms 取 source_seqs 首/末段的时间戳；
    - content 保留 source_seqs 对应的原始文本（换行拼接），便于追溯。
    """
    segments = get_segments(db, session_id)
    if not segments:
        raise ValueError("无原始 segments 可重组")
    validate_clean_result({"roles": roles, "paragraphs": paragraphs}, segments)

    by_seq = {seg.seq: seg for seg in segments}
    user_id = segments[0].user_id
    clear_segments(db, session_id)
    for seq, para in enumerate(paragraphs):
        source_seqs = para["source_seqs"]
        first = by_seq[source_seqs[0]]
        last = by_seq[source_seqs[-1]]
        code_info = roles[para["speaker"]]
        db.add(
            Segment(
                session_id=session_id,
                user_id=user_id,
                seq=seq,
                speaker=para["speaker"],
                role=code_info["role"],
                role_label=code_info["label"],
                cleaned_content=para["text"],
                source="asr",
                content="\n".join(by_seq[seq_no].content for seq_no in source_seqs),
                start_ms=first.start_ms,
                end_ms=last.end_ms,
                confidence=None,
            )
        )
    db.flush()
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
    """解析 LLM 输出的记录 JSON；剥掉可能的 ```json 围栏；缺失三字段抛 ValueError。

    T-S1.11：brief/tags 为新增可选元数据，宽松解析——缺失/类型不对给默认值，
    不作为必填校验（避免模型偶发缺字段导致记录整体失败）。
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
    summary = data.get("summary")
    counselor_work = data.get("counselor_work")
    topics = data.get("client_reported_topics")
    if not isinstance(summary, str) or not summary:
        raise ValueError("summary 缺失或非字符串")
    if not isinstance(counselor_work, str) or not counselor_work:
        raise ValueError("counselor_work 缺失或非字符串")
    if not isinstance(topics, list):
        raise ValueError("client_reported_topics 缺失或非数组")

    brief = data.get("brief")
    tags = data.get("tags")
    data["brief"] = brief if isinstance(brief, str) else ""
    data["tags"] = [tag for tag in tags if isinstance(tag, str)] if isinstance(tags, list) else []
    return data


def store_record(db, session_id: int, settings: Settings, data: dict[str, Any]) -> Record:
    """records 落库：basic_info 存 provider/model/prompt_version/session_id。

    T-S1.11：同时把 brief/tags 回写到 sessions 行（omni 与 asr 共用本调用点）。
    """
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
            # 语义：clean prompt 版本（前端/示例脚本按此展示「清理提示词版本」）；record prompt 为 v3。
            "prompt_version": "v4",
            "session_id": session_id,
            "client_reported_topics": data["client_reported_topics"],
        },
        summary=data["summary"],
        therapist_work=data["counselor_work"],
        notes="",
    )
    db.add(record)
    if session is not None:
        session.brief = data.get("brief", "")
        session.tags = data.get("tags", [])
    db.commit()
    return record
