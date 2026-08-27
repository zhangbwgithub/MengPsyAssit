"""segments 辅助：说话人代号分配 + 落库 + 查询 + 清理后文本拼接。"""

from __future__ import annotations

from typing import Any

from .models import Segment

_CODE_START = ord("A")


def assign_speaker_codes(segments: list[Any]) -> list[dict[str, Any]]:
    """把 ASR 的说话人编号按首现顺序映射为代号 A/B/C…

    路线决策（T-S1.1）：转写阶段不预设角色，segments.speaker 只存代号；
    "谁是咨询师" 的判定交给 clean 阶段 LLM，写回 role/role_label。
    """
    code_by_id: dict[str, str] = {}
    next_index = 0
    out: list[dict[str, Any]] = []
    for seg in segments:
        speaker_id = seg.speaker
        if speaker_id not in code_by_id:
            code_by_id[speaker_id] = chr(_CODE_START + next_index)
            next_index += 1
        out.append(
            {
                "speaker": code_by_id[speaker_id],
                "content": seg.text,
                "start_ms": seg.start_ms,
                "end_ms": seg.end_ms,
                "confidence": seg.confidence,
            }
        )
    return out


def clear_segments(db, session_id: int) -> None:
    """清空会话旧 segments（用于重交幂等）。"""
    db.query(Segment).filter(Segment.session_id == session_id).delete()
    db.flush()


def apply_segments_to_session(db, session_id: int, user_id: int, segments: list[Any]) -> None:
    """分配说话人代号 + 按 seq 落库（幂等：先清空旧数据）。"""
    coded = assign_speaker_codes(segments)
    clear_segments(db, session_id)
    for seq, m in enumerate(coded):
        db.add(
            Segment(
                session_id=session_id,
                user_id=user_id,
                seq=seq,
                speaker=m["speaker"],
                source="asr",
                content=m["content"],
                start_ms=m["start_ms"] or 0,
                end_ms=m["end_ms"] or 0,
                confidence=m["confidence"],
            )
        )
    db.flush()


def get_segments(db, session_id: int) -> list[Segment]:
    """按 seq 顺序取会话 segments。"""
    return (
        db.query(Segment)
        .filter(Segment.session_id == session_id)
        .order_by(Segment.seq)
        .all()
    )


def build_transcript_lines_from_segments(segments: list[Segment]) -> str:
    """把 segments 列表拼成逐行转写稿：`A: 文本` / `B: 文本`（代号，供 clean prompt 输入）。"""
    return "\n".join(f"{seg.speaker}: {seg.content}" for seg in segments)


def build_cleaned_text(db, session_id: int) -> str:
    """把清理后 segments 拼成带角色标签的文本：`咨询师: …` / `来访者: …`。

    供 record 阶段输入与 GET 调试；每段取 cleaned_content（清理后）或 content（回退）。
    """
    lines: list[str] = []
    for seg in get_segments(db, session_id):
        label = seg.role_label or f"说话人 {seg.speaker}"
        text = seg.cleaned_content if seg.cleaned_content is not None else seg.content
        lines.append(f"{label}: {text}")
    return "\n".join(lines)
