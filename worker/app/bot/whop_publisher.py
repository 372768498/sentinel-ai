"""
Whop forum auto-publisher.
Runs at 16:45 ET each NYSE trading day.
Routes to one of 5 templates by weekday and posts via whop-sdk.
"""
from __future__ import annotations

import logging
import os
from collections import Counter
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import db
from .market_calendar import is_trading_day, today_et
from .templates.whop_education_posts import education_post_for_week
from .templates.whop_post_templates import (
    fallback_quiet_day,
    friday_week_review,
    monday_week_ahead,
    tuesday_caught_recap,
    wednesday_behind_scenes,
)

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")
_UTC = ZoneInfo("UTC")


def _required_env(name: str) -> str | None:
    val = os.environ.get(name, "").strip()
    return val or None


def _et_window_for_day(day_et: datetime) -> tuple[datetime, datetime]:
    """Return [start, end) UTC datetimes covering one ET trading day."""
    start_et = day_et.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=_ET)
    end_et = start_et + timedelta(days=1)
    return start_et.astimezone(_UTC), end_et.astimezone(_UTC)


# ── Data gatherers ────────────────────────────────────────────────────────────

async def _scanned_count_estimate() -> int:
    """Rough estimate: distinct tickers across all active profiles × 3 sessions."""
    try:
        profiles = await db.get_all_active_profiles()
    except Exception as exc:
        logger.warning("scanned_count: db unavailable: %s", exc)
        return 0
    tickers: set[str] = set()
    for p in profiles:
        tickers.update(p.get("watchlist") or [])
    return len(tickers) * 3   # 3 scan sessions per trading day


async def _gather_alerts(start_utc, end_utc) -> list[dict]:
    try:
        return await db.alerts_in_window(start_utc, end_utc)
    except Exception as exc:
        logger.warning("alerts_in_window failed: %s", exc)
        return []


def _summarize_alerts_by_ticker(alerts: list[dict], top_n: int = 5) -> str:
    """Return a Whop-Markdown summary line per ticker (no user-level info)."""
    if not alerts:
        return ""
    by_ticker: dict[str, list[float]] = {}
    for a in alerts:
        by_ticker.setdefault(a["ticker"], []).append(a["change_pct"])
    rows = []
    for ticker, pcts in by_ticker.items():
        peak = max(pcts, key=abs)
        sign = "+" if peak > 0 else ""
        rows.append((abs(peak), f"• **{ticker}** {sign}{peak:.2f}% (alerted "
                                f"{len(pcts)}× to Pro users)"))
    rows.sort(reverse=True)
    return "\n".join(line for _, line in rows[:top_n])


# ── Template routers ──────────────────────────────────────────────────────────

async def _build_post_for_weekday(now_et: datetime) -> dict:
    weekday = now_et.weekday()    # 0 = Monday … 4 = Friday
    month_day = now_et.strftime("%b %d")

    today_start_utc, today_end_utc = _et_window_for_day(now_et)

    if weekday == 0:    # Monday — week ahead
        return monday_week_ahead(month_day=month_day)

    if weekday == 1:    # Tuesday — yesterday's catch
        yesterday_et = now_et - timedelta(days=1)
        # Walk back to last trading day if Mon Tue was after a holiday/weekend
        for back in range(1, 5):
            cand = (now_et - timedelta(days=back)).date()
            if is_trading_day(cand):
                yesterday_et = now_et - timedelta(days=back)
                break
        y_start, y_end = _et_window_for_day(yesterday_et)
        alerts = await _gather_alerts(y_start, y_end)
        scanned = await _scanned_count_estimate()
        return tuesday_caught_recap(
            alert_count=len(alerts),
            alerts_summary=_summarize_alerts_by_ticker(alerts),
            scanned_count=max(scanned, len(alerts)),
        )

    if weekday == 2:    # Wednesday — behind the scenes (today's run)
        alerts = await _gather_alerts(today_start_utc, today_end_utc)
        scanned = await _scanned_count_estimate()
        crossed = len(alerts)
        return wednesday_behind_scenes(
            scanned_count=max(scanned, crossed),
            filtered_count=max(scanned - crossed, 0),
            crossed_count=crossed,
            crossed_details=_summarize_alerts_by_ticker(alerts),
            closest_miss="",   # Future: requires capturing near-misses from scanner
        )

    if weekday == 3:    # Thursday — education
        return education_post_for_week(now_et.isocalendar().week)

    if weekday == 4:    # Friday — week-in-review
        return await _build_friday_review(now_et)

    # Weekend (shouldn't fire — scheduler is mon-fri only)
    return fallback_quiet_day(month_day=month_day)


async def _build_friday_review(now_et: datetime) -> dict:
    """Aggregate Mon–Fri of the current ISO week from alert_log."""
    monday_et = now_et - timedelta(days=now_et.weekday())
    days = [monday_et + timedelta(days=i) for i in range(5)]
    daily_counts: list[tuple[str, int]] = []
    total_alerts = 0
    all_alerts: list[dict] = []

    for d in days:
        if not is_trading_day(d.date()):
            daily_counts.append((d.strftime("%a"), 0))
            continue
        s, e = _et_window_for_day(d)
        rows = await _gather_alerts(s, e)
        all_alerts.extend(rows)
        daily_counts.append((d.strftime("%a"), len(rows)))
        total_alerts += len(rows)

    scanned_per_day = await _scanned_count_estimate()
    weekly_scanned = scanned_per_day * sum(1 for d in days if is_trading_day(d.date()))
    weekly_filtered = max(weekly_scanned - total_alerts, 0)

    if daily_counts:
        loudest = max(daily_counts, key=lambda x: x[1])
        # quietest = lowest count among trading days; ignore zero-count placeholder weekend
        trading_only = [(d, c) for d, c in daily_counts
                        if is_trading_day((monday_et + timedelta(
                            days=["Mon", "Tue", "Wed", "Thu", "Fri"].index(d)
                        )).date())]
        quietest = min(trading_only, key=lambda x: x[1]) if trading_only else loudest
    else:
        loudest = quietest = ("Mon", 0)

    summary = ""
    if total_alerts > 0:
        peak_alert = max(all_alerts, key=lambda a: abs(a["change_pct"]))
        sign = "+" if peak_alert["change_pct"] > 0 else ""
        summary = (
            f"**Biggest single move:** {peak_alert['ticker']} "
            f"{sign}{peak_alert['change_pct']:.2f}%"
        )

    return friday_week_review(
        start_date=days[0].strftime("%b %d"),
        end_date=days[-1].strftime("%b %d"),
        weekly_scanned=weekly_scanned,
        weekly_filtered=weekly_filtered,
        weekly_alerts=total_alerts,
        loudest_day=loudest[0],
        loudest_alerts=loudest[1],
        quietest_day=quietest[0],
        quietest_alerts=quietest[1],
        loudest_event_summary=summary,
    )


# ── Whop API call ─────────────────────────────────────────────────────────────

def _build_whop_client():
    api_key = _required_env("WHOP_API_KEY")
    if not api_key:
        raise RuntimeError("WHOP_API_KEY is not set")
    from whop_sdk import Whop
    return Whop(api_key=api_key)


def _post_to_whop(title: str, content: str) -> dict:
    """Synchronous Whop SDK call. Returns the API response or raises."""
    forum_exp_id = _required_env("WHOP_FORUM_EXPERIENCE_ID")
    company_id = _required_env("WHOP_COMPANY_ID")
    if not forum_exp_id:
        raise RuntimeError("WHOP_FORUM_EXPERIENCE_ID is not set")

    client = _build_whop_client()
    kwargs = dict(
        experience_id=forum_exp_id,
        title=title,
        content=content,
        is_mention=False,   # Daily update, not a mention/notify
    )
    if company_id:
        kwargs["company_id"] = company_id

    result = client.forum_posts.create(**kwargs)
    return {
        "id": getattr(result, "id", None),
        "experience_id": forum_exp_id,
    }


# ── Main entrypoint (called by APScheduler) ───────────────────────────────────

async def publish_daily_whop_post(force: bool = False) -> dict:
    """
    Build and publish today's Whop forum post.
    Returns a summary dict; never raises (errors logged for next-day retry).

    `force=True` skips the trading-day check (used for manual testing).
    """
    now_et = datetime.now(_ET)

    if not force and not is_trading_day(now_et.date()):
        logger.info("whop publisher skipped — not a trading day")
        return {"skipped": True, "reason": "not_trading_day"}

    try:
        post = await _build_post_for_weekday(now_et)
    except Exception as exc:
        logger.error("whop post build failed: %s", exc, exc_info=True)
        post = fallback_quiet_day(month_day=now_et.strftime("%b %d"))

    try:
        import asyncio
        result = await asyncio.to_thread(_post_to_whop, post["title"], post["content"])
        logger.info("whop post published: id=%s title=%r", result.get("id"), post["title"])
        return {"posted": True, "post_id": result.get("id"), "title": post["title"]}
    except Exception as exc:
        logger.error("whop post failed: %s", exc, exc_info=True)
        return {"posted": False, "error": str(exc), "title": post.get("title")}
