from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

# Load .env.local from project root before anything else reads os.environ
try:
    from dotenv import load_dotenv
    _project_root = Path(__file__).resolve().parents[2]
    for env_file in (_project_root / ".env.local", _project_root / ".env"):
        if env_file.exists():
            load_dotenv(env_file, override=False)
            print(f"[env] loaded {env_file}", flush=True)
            break
except ImportError:
    pass

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from .config import get_settings
from .models import AnalyzeAccepted, AnalyzeRequest, PushAlertRequest
from .runner import run_analysis_job
from .scanner import run_scan_and_push
from .scheduler import build_scheduler
from .store import JobRecord, JobStore

logger = logging.getLogger(__name__)

settings = get_settings()
store = JobStore()


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = build_scheduler()
    if scheduler is not None:
        scheduler.start()
        print("[scheduler] started", flush=True)
        from .bot.tz_check import verify_timezones
        verify_timezones(scheduler)

    bot_app = None
    from .bot.bot import build_application, is_bot_enabled, start_bot, stop_bot
    if is_bot_enabled():
        try:
            bot_app = build_application()
            await start_bot(bot_app)
        except Exception as exc:
            print(f"[bot] failed to start: {exc}", flush=True)
            bot_app = None

    try:
        yield
    finally:
        if bot_app is not None:
            await stop_bot(bot_app)
        if scheduler is not None:
            scheduler.shutdown(wait=False)
            print("[scheduler] stopped", flush=True)


app = FastAPI(title="Sentinel AI Worker", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_allowed_origins),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _require_internal_token(x_internal_token: str | None) -> None:
    if not settings.worker_internal_token:
        raise HTTPException(status_code=503, detail="WORKER_INTERNAL_TOKEN is not configured")
    if x_internal_token != settings.worker_internal_token:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _require_job_token(snapshot: JobRecord, token: str | None) -> None:
    if not token or token != snapshot.access_token:
        raise HTTPException(status_code=401, detail="Unauthorized job access")


@app.get("/api/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/scan/run")
async def trigger_scan(
    session_label: str = "Manual",
    x_internal_token: str | None = Header(default=None),
) -> dict:
    _require_internal_token(x_internal_token)
    return await run_scan_and_push(session_label)


@app.post("/api/bot/push-alert")
async def push_alert(
    payload: PushAlertRequest,
    x_internal_token: str | None = Header(default=None),
) -> dict:
    """
    Operator-triggered caught-moment alert.
    Used during 14-day public test for hand-curated moments where AI can't be trusted yet.
    Sends to all active VIP users (target=all) or only those watching the ticker (target=watchers).
    """
    _require_internal_token(x_internal_token)

    from .bot import db
    from .bot.alerter import _default_sender
    from .bot.templates.telegram_messages import (
        AlertPriority,
        caught_moment_alert,
        compute_priority,
    )

    profiles = await db.get_all_active_profiles()
    if payload.target == "watchers":
        ticker_upper = payload.ticker.upper()
        profiles = [p for p in profiles if ticker_upper in (p.get("watchlist") or [])]

    if not profiles:
        return {"target_count": 0, "sent": 0, "target": payload.target}

    text = caught_moment_alert(
        ticker=payload.ticker.upper(),
        headline=payload.headline,
        detail=payload.detail,
        source_url=payload.source_url,
        change_pct=payload.change_pct,
    )
    priority = compute_priority(payload.change_pct)

    sent_count = 0
    for profile in profiles:
        result = await _default_sender(
            profile["telegram_user_id"], text, priority,
        )
        if result:
            sent_count += 1

    return {
        "target_count": len(profiles),
        "sent": sent_count,
        "target": payload.target,
        "ticker": payload.ticker.upper(),
        "priority": priority.value,
    }


@app.post("/api/analyze", response_model=AnalyzeAccepted)
async def create_analysis_job(
    request: Request,
    payload: AnalyzeRequest,
    x_internal_token: str | None = Header(default=None),
) -> AnalyzeAccepted:
    _require_internal_token(x_internal_token)

    job_id = str(uuid4())
    base_url = settings.worker_public_url or str(request.base_url).rstrip("/")

    record = JobRecord(
        job_id=job_id,
        history_id=payload.history_id,
        access_token=payload.access_token,
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
        eventsUrl=f"{base_url}/api/analyze/{job_id}/events?token={payload.access_token}",
        pollUrl=f"{base_url}/api/analyze/{job_id}?token={payload.access_token}",
    )


@app.get("/api/analyze/{job_id}")
async def get_analysis_job(job_id: str, token: str | None = Query(default=None)):
    snapshot = await store.snapshot(job_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Job not found")
    _require_job_token(snapshot, token)
    return snapshot


@app.get("/api/analyze/{job_id}/events")
async def get_analysis_events(job_id: str, token: str | None = Query(default=None)):
    snapshot = await store.snapshot(job_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Job not found")
    _require_job_token(snapshot, token)

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
