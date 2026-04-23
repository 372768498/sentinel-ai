from __future__ import annotations

import asyncio
import json
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from .config import get_settings
from .models import AnalyzeAccepted, AnalyzeRequest
from .runner import run_analysis_job
from .store import JobRecord, JobStore

settings = get_settings()
store = JobStore()
app = FastAPI(title="Sentinel AI Worker", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/analyze", response_model=AnalyzeAccepted)
async def create_analysis_job(
    request: Request,
    payload: AnalyzeRequest,
    x_internal_token: str | None = Header(default=None),
) -> AnalyzeAccepted:
    if settings.worker_internal_token and x_internal_token != settings.worker_internal_token:
        raise HTTPException(status_code=401, detail="Unauthorized")

    job_id = str(uuid4())
    base_url = settings.worker_public_url or str(request.base_url).rstrip("/")

    record = JobRecord(
        job_id=job_id,
        history_id=payload.history_id,
        ticker=payload.ticker,
        email=payload.email,
        requested_mode=payload.requested_mode,
        deep_mode=payload.deep_mode,
        logs=[f">> Job {job_id} accepted", ">> 等待 Python 任务启动..."],
    )
    await store.create(record)
    asyncio.create_task(
        run_analysis_job(job_id=job_id, payload=payload, settings=settings, store=store)
    )

    return AnalyzeAccepted(
        jobId=job_id,
        status="queued",
        eventsUrl=f"{base_url}/api/analyze/{job_id}/events",
        pollUrl=f"{base_url}/api/analyze/{job_id}",
    )


@app.get("/api/analyze/{job_id}")
async def get_analysis_job(job_id: str):
    snapshot = await store.snapshot(job_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return snapshot


@app.get("/api/analyze/{job_id}/events")
async def get_analysis_events(job_id: str):
    snapshot = await store.snapshot(job_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_stream():
        last_log_index = 0
        result_sent = False

        while True:
            current = await store.snapshot(job_id)
            if current is None:
                yield "event: error\ndata: Job not found\n\n"
                break

            while last_log_index < len(current.logs):
                message = current.logs[last_log_index]
                yield f"event: log\ndata: {message}\n\n"
                last_log_index += 1

            if current.status == "completed" and not result_sent:
                yield f"event: result\ndata: {json.dumps(current.result, ensure_ascii=False)}\n\n"
                yield "event: done\ndata: completed\n\n"
                result_sent = True
                break

            if current.status == "failed":
                yield f"event: error\ndata: {current.error_message or 'Job failed'}\n\n"
                break

            yield ": keep-alive\n\n"
            await asyncio.sleep(1.0)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
