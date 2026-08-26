"""jobs 表辅助：三段任务（transcribe/clean/record）各一行，状态与错误记录。"""

from __future__ import annotations

from .enums import JobStatus
from .models import Job


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
        db.commit()


def mark_job_done(db, job_id: int) -> None:
    job = db.get(Job, job_id)
    if job is not None:
        job.status = JobStatus.DONE
        db.commit()


def mark_job_failed(db, job_id: int, error: str) -> None:
    job = db.get(Job, job_id)
    if job is not None:
        job.status = JobStatus.FAILED
        job.error = error
        db.commit()
