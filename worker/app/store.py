from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class JobRecord:
    job_id: str
    history_id: str
    ticker: str
    email: str
    requested_mode: str
    deep_mode: str | None = None
    status: str = "queued"
    logs: list[str] = field(default_factory=list)
    result: dict | None = None
    markdown_report: str | None = None
    email_delivery_id: str | None = None
    error_message: str | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock = asyncio.Lock()

    async def create(self, record: JobRecord) -> None:
        async with self._lock:
            self._jobs[record.job_id] = record

    async def append_log(self, job_id: str, message: str) -> None:
        async with self._lock:
            job = self._jobs[job_id]
            job.logs.append(message)
            job.updated_at = datetime.now(timezone.utc).isoformat()

    async def mark_running(self, job_id: str) -> None:
        async with self._lock:
            job = self._jobs[job_id]
            job.status = "running"
            job.updated_at = datetime.now(timezone.utc).isoformat()

    async def complete(
        self,
        job_id: str,
        result: dict,
        markdown_report: str | None,
        email_delivery_id: str | None,
    ) -> None:
        async with self._lock:
            job = self._jobs[job_id]
            job.status = "completed"
            job.result = result
            job.markdown_report = markdown_report
            job.email_delivery_id = email_delivery_id
            job.updated_at = datetime.now(timezone.utc).isoformat()

    async def fail(self, job_id: str, error_message: str) -> None:
        async with self._lock:
            job = self._jobs[job_id]
            job.status = "failed"
            job.error_message = error_message
            job.updated_at = datetime.now(timezone.utc).isoformat()

    async def snapshot(self, job_id: str) -> JobRecord | None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None

            return JobRecord(
                job_id=job.job_id,
                history_id=job.history_id,
                ticker=job.ticker,
                email=job.email,
                requested_mode=job.requested_mode,
                deep_mode=job.deep_mode,
                status=job.status,
                logs=list(job.logs),
                result=job.result.copy() if isinstance(job.result, dict) else job.result,
                markdown_report=job.markdown_report,
                email_delivery_id=job.email_delivery_id,
                error_message=job.error_message,
                created_at=job.created_at,
                updated_at=job.updated_at,
            )
