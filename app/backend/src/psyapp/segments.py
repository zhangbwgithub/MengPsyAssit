"""segments 辅助：说话人映射 + 落库 + 查询。"""

from __future__ import annotations

from typing import Any

from .models import Segment


def apply_speaker_mapping(segments: list[Any], speaker_zero: str) -> list[dict[str, Any]]:
    """把 ASR Segment 的编号 speaker 映射为 T/P，其余编号 → U。

    路线决策 1：speaker "0" → speaker_zero，"1" → 另一个；>1 无法确定 → U（待确认）。
    """
    other = "P" if speaker_zero == "T" else "T"
    mapping = {"0": speaker_zero, "1": other}
    out: list[dict[str, Any]] = []
    for seg in segments:
        out.append(
            {
                "speaker": mapping.get(seg.speaker, "U"),
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


def apply_segments_to_session(db, session_id: int, user_id: int, segments: list[Any], speaker_zero: str) -> None:
    """映射 + 按 seq 落库（幂等：先清空旧数据）。"""
    mapped = apply_speaker_mapping(segments, speaker_zero)
    clear_segments(db, session_id)
    for seq, m in enumerate(mapped):
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


def build_transcript_lines(db, session_id: int) -> str:
    """segments 拼成逐行转写稿：`T: 文本` / `P: 文本`。"""
    return "\n".join(f"{seg.speaker}: {seg.content}" for seg in get_segments(db, session_id))
