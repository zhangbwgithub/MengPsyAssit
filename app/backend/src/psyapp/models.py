"""数据模型（方案文档 §5）——SQLAlchemy 2.0 typed/Mapped 风格。

S0 dev 单用户模式：所有业务表从第一天预留 user_id 多用户隔离列。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .enums import (
    ClientStatus,
    JobStatus,
    RecordStatus,
    SegmentSource,
    SessionStatus,
    SpeakerCode,
)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False, default="")


class Client(Base):
    __tablename__ = "clients"
    __table_args__ = (UniqueConstraint("user_id", "code", name="uq_clients_user_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ClientStatus.ACTIVE
    )
    # T-S1.17 来访者档案：姓名必填（API 层校验）；code 保留作内部代号。
    name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    gender: Mapped[str | None] = mapped_column(String(8), nullable=True)
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    emergency_contact: Mapped[str | None] = mapped_column(String(64), nullable=True)
    emergency_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # 小节数手工修正值；为空表示自动计（名下会话数）。
    session_count_manual: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    client_id: Mapped[int | None] = mapped_column(
        ForeignKey("clients.id"), nullable=True, index=True
    )
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    # T-S1.6：双模式管线（omni=多模态直转 / asr=paraformer+LLM）；旧数据无值按 asr 展示
    pipeline_mode: Mapped[str | None] = mapped_column(String(8), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=SessionStatus.RECORDING
    )
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    duration_sec: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    audio_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    cleaned_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 审计底稿：清理前的原始转写稿（`代号: 文本` 逐行），T-S1.3 起持久化
    raw_transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    # T-S1.11：记录元数据（来源文件名/标签/摘要/分组）
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    brief: Mapped[str | None] = mapped_column(Text, nullable=True)
    group_id: Mapped[int | None] = mapped_column(
        ForeignKey("session_groups.id"), nullable=True, index=True
    )


class SessionGroup(Base):
    """T-S1.11：同一音频的记录分组（组名/标签/备注，可增删改查）。"""

    __tablename__ = "session_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)


class Segment(Base):
    __tablename__ = "segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.id"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker: Mapped[str] = mapped_column(
        String(8), nullable=False, default=SpeakerCode.UNKNOWN
    )
    role: Mapped[str | None] = mapped_column(String(1), nullable=True)
    role_label: Mapped[str | None] = mapped_column(String(16), nullable=True)
    cleaned_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default=SegmentSource.ASR)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)


class Record(Base):
    __tablename__ = "records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    client_id: Mapped[int | None] = mapped_column(
        ForeignKey("clients.id"), nullable=True, index=True
    )
    session_id: Mapped[int | None] = mapped_column(
        ForeignKey("sessions.id"), nullable=True, index=True
    )
    record_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=RecordStatus.DRAFT)
    basic_info: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    therapist_work: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Theme(Base):
    __tablename__ = "themes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    record_id: Mapped[int] = mapped_column(
        ForeignKey("records.id"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.id"), nullable=False, index=True
    )
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=JobStatus.PENDING)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
