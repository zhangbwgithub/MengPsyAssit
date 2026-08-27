"""jobs 表辅助：三段任务（transcribe/clean/record）各一行，状态与错误记录。

T-S1.2 起补可观测性时间戳：running 时写 started_at，done/failed 时写 finished_at。
时区处理与 store_record 一致：UTC now 去 tzinfo（naive UTC，SQLite 友好）。
"""

from __future__ import annotations

from datetime import datetime, timezone

from .enums import JobStatus
from .models import Job


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def add_job(db, session_id: int, type_: str, provider: str | None) -> Job:
    """新建一行 pending job 并 flush 拿到 id。"""
    job = Job(type=type_, session_id=session_id, provider=provider, status=JobStatus.PENDING)
    db.add(job)
    db.flush()
    return job


def mark_job_running(db, job_id: int) -> None:
    job = db.get(Job, job_id)
    if job is not None:
        job.status = JobStatus.RUNNING
        # 重试场景只记第一次进入 running 的时刻，避免 started_at 被后一次尝试覆盖
        if job.started_at is None:
            job.started_at = _now()
        db.commit()


def mark_job_done(db, job_id: int) -> None:
    job = db.get(Job, job_id)
    if job is not None:
        job.status = JobStatus.DONE
        job.finished_at = _now()
        db.commit()


def mark_job_failed(db, job_id: int, error: str) -> None:
    job = db.get(Job, job_id)
    if job is not None:
        job.status = JobStatus.FAILED
        job.error = error
        job.finished_at = _now()
        db.commit()
