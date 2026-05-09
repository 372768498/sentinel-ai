from __future__ import annotations

import logging
import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .scanner import run_scan_and_push

logger = logging.getLogger(__name__)

ET_TZ = "America/New_York"

SESSIONS = (
    ("Pre-market", 9, 0),
    ("Mid-day", 12, 30),
    ("Post-close", 16, 30),
)


def _scanner_enabled() -> bool:
    return os.environ.get("SCANNER_ENABLED", "").lower() in ("1", "true", "yes")


def _bot_enabled() -> bool:
    return os.environ.get("BOT_ENABLED", "").lower() in ("1", "true", "yes")


def build_scheduler() -> AsyncIOScheduler | None:
    if not _scanner_enabled() and not _bot_enabled():
        print("[scheduler] disabled — set SCANNER_ENABLED or BOT_ENABLED to enable", flush=True)
        return None

    # All jobs use ET timezone — APScheduler handles DST automatically via pytz/zoneinfo
    scheduler = AsyncIOScheduler(timezone=ET_TZ)

    if _scanner_enabled():
        for label, hour, minute in SESSIONS:
            scheduler.add_job(
                run_scan_and_push,
                trigger=CronTrigger(
                    day_of_week="mon-fri",
                    hour=hour,
                    minute=minute,
                    timezone=ET_TZ,
                ),
                kwargs={"session_label": label},
                id=f"scan-{label.lower().replace(' ', '-')}",
                replace_existing=True,
                misfire_grace_time=300,
            )
            print(f"[scanner] {label} at {hour:02d}:{minute:02d} ET (mon-fri)", flush=True)

    if _bot_enabled():
        from .bot.alerter import dispatch_personal_alerts, process_queued_alerts
        from .bot.digest import personal_eod_digests, public_eod_digest, public_premarket_brief

        # ── Public channel ──────────────────────────────────────────────────
        scheduler.add_job(
            public_premarket_brief,
            trigger=CronTrigger(day_of_week="mon-fri", hour=8, minute=30, timezone=ET_TZ),
            id="brief-premarket-public",
            replace_existing=True,
            misfire_grace_time=300,
        )
        print("[bot] public pre-market brief at 08:30 ET (mon-fri)", flush=True)

        scheduler.add_job(
            public_eod_digest,
            trigger=CronTrigger(day_of_week="mon-fri", hour=16, minute=30, timezone=ET_TZ),
            id="digest-postclose-public",
            replace_existing=True,
            misfire_grace_time=300,
        )
        print("[bot] public post-close digest at 16:30 ET (mon-fri)", flush=True)

        # ── Personal alerts after each scanner session ──────────────────────
        for label, hour, minute in SESSIONS:
            # Run personal alerts 2 minutes after the scanner (prices settled)
            p_minute = (minute + 2) % 60
            p_hour = hour + ((minute + 2) // 60)
            scheduler.add_job(
                dispatch_personal_alerts,
                trigger=CronTrigger(
                    day_of_week="mon-fri",
                    hour=p_hour,
                    minute=p_minute,
                    timezone=ET_TZ,
                ),
                kwargs={"session_label": label},
                id=f"alerts-personal-{label.lower().replace(' ', '-')}",
                replace_existing=True,
                misfire_grace_time=300,
            )
            print(f"[bot] personal alerts after {label} at {p_hour:02d}:{p_minute:02d} ET", flush=True)

        # ── Personal EOD digest ─────────────────────────────────────────────
        scheduler.add_job(
            personal_eod_digests,
            trigger=CronTrigger(day_of_week="mon-fri", hour=16, minute=35, timezone=ET_TZ),
            id="digest-postclose-personal",
            replace_existing=True,
            misfire_grace_time=300,
        )
        print("[bot] personal EOD digests at 16:35 ET (mon-fri)", flush=True)

        # ── Queued alert processor (every 2 min) ───────────────────────────
        scheduler.add_job(
            process_queued_alerts,
            trigger=IntervalTrigger(minutes=2, timezone=ET_TZ),
            id="queued-alerts-processor",
            replace_existing=True,
            misfire_grace_time=60,
        )
        print("[bot] queued alert processor every 2 min", flush=True)

        # ── Whop daily forum post (16:45 ET, after EOD digests settle) ──────
        if os.environ.get("WHOP_API_KEY", "").strip():
            from .bot.whop_publisher import publish_daily_whop_post
            scheduler.add_job(
                publish_daily_whop_post,
                trigger=CronTrigger(
                    day_of_week="mon-fri",
                    hour=16, minute=45, timezone=ET_TZ,
                ),
                id="whop-daily-post",
                replace_existing=True,
                misfire_grace_time=600,
            )
            print("[bot] Whop daily forum post at 16:45 ET (mon-fri)", flush=True)
        else:
            print("[bot] Whop daily forum post DISABLED (WHOP_API_KEY not set)", flush=True)

    return scheduler
