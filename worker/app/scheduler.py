from __future__ import annotations

import logging
import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

ET_TZ = "America/New_York"

# Personal alerts (Pro DM) still run after scanner-equivalent moments.
# Public channel pushes are owned by `bot.digest` (see _bot_enabled branch),
# never by `scanner.run_scan_and_push` (which now only serves /api/scan/run).
SESSIONS = (
    ("Pre-market", 8, 30),
    ("Mid-day", 12, 30),
    ("Post-close", 16, 30),
)


def _scanner_enabled() -> bool:
    return os.environ.get("SCANNER_ENABLED", "").lower() in ("1", "true", "yes")


def _bot_enabled() -> bool:
    return os.environ.get("BOT_ENABLED", "").lower() in ("1", "true", "yes")


def _marketing_enabled() -> bool:
    return os.environ.get("MARKETING_ENABLED", "").lower() in ("1", "true", "yes")


def _daily_draft_enabled() -> bool:
    return os.environ.get("MARKETING_DAILY_DRAFT_ENABLED", "").lower() in ("1", "true", "yes")


def _daily_draft_hour() -> int:
    raw = os.environ.get("MARKETING_DAILY_DRAFT_HOUR_ET", "9")
    try:
        hour = int(raw)
    except ValueError:
        return 9
    return max(0, min(23, hour))


def _queue_poll_enabled() -> bool:
    return os.environ.get("MARKETING_QUEUE_POLL_ENABLED", "").lower() in ("1", "true", "yes")


def _queue_poll_interval() -> int:
    raw = os.environ.get("MARKETING_QUEUE_POLL_INTERVAL_SECONDS", "300")
    try:
        return max(30, int(raw))  # never poll faster than 30s
    except ValueError:
        return 300


def _publish_is_live() -> bool:
    raw = os.environ.get("MARKETING_PUBLISH_DRY_RUN", "true").strip().lower()
    return raw in {"0", "false", "no", "off"}


def _daily_digest_enabled() -> bool:
    return os.environ.get("MARKETING_DAILY_DIGEST_ENABLED", "").lower() in ("1", "true", "yes")


def _email_daily_enabled() -> bool:
    return os.environ.get("MARKETING_EMAIL_DAILY_ENABLED", "").lower() in ("1", "true", "yes")


def _email_daily_hour_minute() -> tuple[int, int]:
    # Default 08:15 ET — fires 15 min before the Telegram public radar (08:30 ET)
    # so desktop users see the email first and Telegram is the reminder.
    hour_raw = os.environ.get("MARKETING_EMAIL_DAILY_HOUR_ET", "8")
    minute_raw = os.environ.get("MARKETING_EMAIL_DAILY_MINUTE_ET", "15")
    try:
        hour = max(0, min(23, int(hour_raw)))
    except ValueError:
        hour = 8
    try:
        minute = max(0, min(59, int(minute_raw)))
    except ValueError:
        minute = 15
    return hour, minute


def _daily_digest_hour_minute() -> tuple[int, int]:
    hour_raw = os.environ.get("MARKETING_DAILY_DIGEST_HOUR_ET", "16")
    minute_raw = os.environ.get("MARKETING_DAILY_DIGEST_MINUTE_ET", "30")
    try:
        hour = max(0, min(23, int(hour_raw)))
    except ValueError:
        hour = 16
    try:
        minute = max(0, min(59, int(minute_raw)))
    except ValueError:
        minute = 30
    return hour, minute


def build_scheduler() -> AsyncIOScheduler | None:
    if (
        not _scanner_enabled()
        and not _bot_enabled()
        and not _marketing_enabled()
        and not _daily_draft_enabled()
        and not _queue_poll_enabled()
        and not _daily_digest_enabled()
        and not _email_daily_enabled()
    ):
        print(
            "[scheduler] disabled — set SCANNER_ENABLED / BOT_ENABLED / "
            "MARKETING_ENABLED / MARKETING_DAILY_DRAFT_ENABLED / "
            "MARKETING_QUEUE_POLL_ENABLED / MARKETING_DAILY_DIGEST_ENABLED / "
            "MARKETING_EMAIL_DAILY_ENABLED",
            flush=True,
        )
        return None

    # All jobs use ET timezone — APScheduler handles DST automatically via pytz/zoneinfo
    scheduler = AsyncIOScheduler(timezone=ET_TZ)

    # NOTE (2026-05-14): scanner.run_scan_and_push is no longer wired into a cron.
    # It used to duplicate the public-channel pushes already owned by bot.digest,
    # and emitted stale "previous-day close" numbers in the pre-market slot because
    # yfinance's "2d/1d" history can't see the live pre-market quote. The function
    # is kept for /api/scan/run manual ops; the cron path is gone on purpose.
    # See worker/app/bot/digest.py for the authoritative public-channel jobs.
    _ = _scanner_enabled()  # touched only so legacy env flag stays valid

    if _bot_enabled():
        from .bot.alerter import dispatch_personal_alerts, process_queued_alerts
        from .bot.digest import (
            personal_eod_digests,
            personal_pro_daily_brief,
            public_eod_digest,
            public_midday_brief,
            public_premarket_brief,
        )

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
            public_midday_brief,
            trigger=CronTrigger(day_of_week="mon-fri", hour=12, minute=30, timezone=ET_TZ),
            id="brief-midday-public",
            replace_existing=True,
            misfire_grace_time=300,
        )
        print("[bot] public mid-day brief at 12:30 ET (mon-fri)", flush=True)

        # ── Pro DM detail card (09:00 ET) ───────────────────────────────────
        # Fires 30 min after the public pre-market radar. Each Pro user gets
        # ONE personalized DM containing the top mover in their watchlist
        # with the 10-dim Sentinel breakdown.
        scheduler.add_job(
            personal_pro_daily_brief,
            trigger=CronTrigger(day_of_week="mon-fri", hour=9, minute=0, timezone=ET_TZ),
            id="brief-pro-daily-personal",
            replace_existing=True,
            misfire_grace_time=300,
        )
        print("[bot] Pro DM daily brief at 09:00 ET (mon-fri)", flush=True)

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

    if _marketing_enabled():
        from .marketing.jobs import publish_marketing_alerts

        # Marketing dispatch: 3 min after each scanner session so prices settle
        # and the official channel/Pro DM has already gone out first.
        for label, hour, minute in SESSIONS:
            m_minute = (minute + 3) % 60
            m_hour = hour + ((minute + 3) // 60)
            scheduler.add_job(
                publish_marketing_alerts,
                trigger=CronTrigger(
                    day_of_week="mon-fri",
                    hour=m_hour,
                    minute=m_minute,
                    timezone=ET_TZ,
                ),
                kwargs={"session_label": label},
                id=f"marketing-x-{label.lower().replace(' ', '-')}",
                replace_existing=True,
                misfire_grace_time=300,
            )
            print(
                f"[marketing] X dispatch after {label} at {m_hour:02d}:{m_minute:02d} ET",
                flush=True,
            )

    if _daily_draft_enabled():
        from .marketing.jobs import generate_daily_review_drafts

        # Daily draft generation runs once per US trading day at 09:00 ET
        # (configurable via MARKETING_DAILY_DRAFT_HOUR_ET). This is US stock
        # market local time (America/New_York) — APScheduler handles DST.
        hour = _daily_draft_hour()
        scheduler.add_job(
            generate_daily_review_drafts,
            trigger=CronTrigger(
                day_of_week="mon-fri",
                hour=hour,
                minute=0,
                timezone=ET_TZ,
            ),
            kwargs={"session_label": f"daily_{hour:02d}00_et"},
            id="marketing-daily-drafts",
            replace_existing=True,
            misfire_grace_time=600,
        )
        print(
            f"[marketing] daily review-draft generation at {hour:02d}:00 ET (mon-fri)",
            flush=True,
        )

    if _queue_poll_enabled():
        from .marketing.review_poller import run_once as poll_review_queue

        interval = _queue_poll_interval()
        live = _publish_is_live()
        scheduler.add_job(
            poll_review_queue,
            trigger=IntervalTrigger(seconds=interval, timezone=ET_TZ),
            id="marketing-review-poller",
            replace_existing=True,
            misfire_grace_time=interval,
        )
        mode = "LIVE" if live else "DRY-RUN"
        print(
            f"[marketing] review-queue poller every {interval}s — Telegram publisher {mode} "
            f"(MARKETING_PUBLISH_DRY_RUN={'false' if live else 'true'})",
            flush=True,
        )

    if _daily_digest_enabled():
        from .marketing.kpi_aggregator import aggregate_and_push_digest

        # Daily Growth Digest — defaults to 16:30 ET (post-close). Window covers
        # 00:00 ET → fire time, attributing same-day clicks/emails to
        # content_ids generated by the morning daily-draft job.
        digest_hour, digest_minute = _daily_digest_hour_minute()
        scheduler.add_job(
            aggregate_and_push_digest,
            trigger=CronTrigger(
                day_of_week="mon-fri",
                hour=digest_hour,
                minute=digest_minute,
                timezone=ET_TZ,
            ),
            id="marketing-daily-digest",
            replace_existing=True,
            misfire_grace_time=900,
        )
        print(
            f"[marketing] daily growth digest at {digest_hour:02d}:{digest_minute:02d} ET (mon-fri)",
            flush=True,
        )

    if _email_daily_enabled():
        from .marketing.email_jobs import run_scheduled_email_digest

        # Free Email Daily Radar — defaults to 07:00 ET (pre-market). The job
        # itself is double-gated: MARKETING_EMAIL_DAILY_DRY_RUN=true skips the
        # Resend POST, and MARKETING_EMAIL_DAILY_ALLOW_BULK=false refuses bulk
        # live sends. Both must be flipped before real fan-out happens.
        email_hour, email_minute = _email_daily_hour_minute()
        scheduler.add_job(
            run_scheduled_email_digest,
            trigger=CronTrigger(
                day_of_week="mon-fri",
                hour=email_hour,
                minute=email_minute,
                timezone=ET_TZ,
            ),
            id="marketing-email-daily",
            replace_existing=True,
            misfire_grace_time=900,
        )
        dry_flag = os.environ.get("MARKETING_EMAIL_DAILY_DRY_RUN", "true").strip().lower()
        bulk_flag = os.environ.get("MARKETING_EMAIL_DAILY_ALLOW_BULK", "false").strip().lower()
        print(
            f"[marketing] email daily radar at {email_hour:02d}:{email_minute:02d} ET (mon-fri) "
            f"— dry_run={dry_flag} allow_bulk={bulk_flag}",
            flush=True,
        )

    return scheduler
