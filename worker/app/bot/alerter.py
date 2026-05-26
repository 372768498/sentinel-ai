"""
Personal real-time alert dispatcher.
Called by APScheduler after each scanner run.

Flow:
  1. Load all active user profiles
  2. Batch-fetch prices for all unique tickers
  3. For each user: find crossings vs their threshold
  4. Check dedup (cooldown) and quiet hours
  5. Send immediately or queue for later delivery

Batch aggregation: if a user has >= BATCH_THRESHOLD crossings at once,
send one combined message instead of N individual ones (prevents alert storms).
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Callable, Awaitable

import httpx

from ..scanner import TickerMove, fetch_watchlist_moves
from ..scoring import ScoreRow, get_latest_scores, get_score_delta
from . import db
from .market_calendar import is_trading_day, today_et
from .templates.telegram_messages import (
    AlertPriority,
    alert_threshold_crossed,
    alert_threshold_crossed_batch,
    build_alert_keyboard,
    compute_priority,
    should_call_for,
)
from .tz_check import is_quiet_time

logger = logging.getLogger(__name__)

BATCH_THRESHOLD = 3   # crossings ≥ this → send one batch message

# Sender takes (user_id, text, priority) — priority is forwarded for logging/escalation
SenderFn = Callable[..., Awaitable[dict | None]]


async def _score_overlay_for_tickers(tickers: list[str]) -> dict[str, dict]:
    """
    Pull {score_100, rating, score_change, why_moving, risk_flag} per ticker.
    Empty dict on DB unavailable / table empty / any error — caller treats
    the overlay as decorative and renders without it.
    """
    if not tickers:
        return {}
    try:
        pool = await db.get_pool()
    except Exception as exc:
        logger.debug("alert score overlay: DB unavailable: %s", exc)
        return {}

    try:
        latest = await get_latest_scores(pool, tickers)
    except Exception as exc:
        logger.warning("alert score overlay: get_latest_scores failed: %s", exc)
        return {}

    overlay: dict[str, dict] = {}
    for ticker in tickers:
        row = latest.get(ticker.upper())
        if row is None:
            continue
        delta: int | None = None
        try:
            _, prior = await get_score_delta(pool, ticker)
            if prior is not None:
                delta = row.score_100 - prior.score_100
        except Exception as exc:
            logger.debug("alert score delta failed for %s: %s", ticker, exc)
        overlay[ticker.upper()] = {
            "score_100": row.score_100,
            "rating": row.rating,
            "score_change": delta,
            "why_moving": row.why_moving,
            "risk_flag": row.risk_flag,
        }
    return overlay


async def _default_sender(
    user_id: int,
    text: str,
    priority: AlertPriority = AlertPriority.NORMAL,
    reply_markup: dict | None = None,
) -> dict | None:
    """Send a DM to a Telegram user via Bot API (httpx)."""
    import json as _json

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not set — cannot send DM")
        return None
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    # Always notify (False); priority kept as metadata for future critical-alert escalation
    payload: dict = {
        "chat_id": user_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "disable_notification": False,
    }
    if reply_markup is not None:
        payload["reply_markup"] = _json.dumps(reply_markup, ensure_ascii=False)
    if should_call_for(priority):
        # Future: trigger Twilio call workflow here (P3 item from backlog)
        logger.warning(
            "CRITICAL alert for user %s — should_call=True (Twilio not yet wired)", user_id,
        )
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload)
        data = resp.json()
        if not data.get("ok"):
            logger.warning(
                "DM send failed to %s: %s %s",
                user_id, data.get("error_code"), data.get("description"),
            )
            return None
        logger.info("alert DM sent to user %s (msg_id=%s)", user_id,
                    data["result"]["message_id"])
        return data["result"]
    except Exception as exc:
        logger.error("DM send error to %s: %s", user_id, exc)
        return None


async def _send_or_queue(
    profile: dict,
    crossings: list[TickerMove],
    sender: SenderFn,
    score_overlay: dict[str, dict] | None = None,
) -> dict:
    """
    For each crossing: check cooldown → check quiet hours → send or queue.
    If >= BATCH_THRESHOLD crossings pass cooldown check, aggregate into one message.
    Returns stats dict.
    """
    user_id: int = profile["telegram_user_id"]
    snooze_until = profile.get("snooze_until")
    if snooze_until:
        if snooze_until.tzinfo is None:
            snooze_until = snooze_until.replace(tzinfo=timezone.utc)
        if snooze_until > datetime.now(timezone.utc):
            logger.info("user %s snoozed until %s — suppressing alerts", user_id, snooze_until)
            return {"sent": 0, "queued": 0, "deduped": len(crossings)}

    quiet_enabled: bool = profile.get("quiet_hours_enabled", True)
    quiet_start: int = profile.get("quiet_hours_start", 22)
    quiet_end: int = profile.get("quiet_hours_end", 7)
    in_quiet = is_quiet_time(quiet_enabled, quiet_start, quiet_end)

    stats = {"sent": 0, "queued": 0, "deduped": 0}

    # Filter out crossings still on cooldown
    eligible: list[TickerMove] = []
    for move in crossings:
        direction = "+" if move.change_pct > 0 else "-"
        if await db.is_on_cooldown(user_id, move.ticker, direction):
            logger.debug("cooldown active: user=%s ticker=%s dir=%s", user_id, move.ticker, direction)
            stats["deduped"] += 1
            continue
        eligible.append(move)

    if not eligible:
        return stats

    # Set cooldowns for all eligible (do this before send, so concurrent runs don't double-send)
    for move in eligible:
        direction = "+" if move.change_pct > 0 else "-"
        await db.set_cooldown(user_id, move.ticker, direction)

    if in_quiet:
        # Queue all eligible alerts for later delivery
        for move in eligible:
            payload = {
                "ticker": move.ticker,
                "change_pct": move.change_pct,
                "prev_price": move.prev_close,
                "price": move.last_price,
                "priority": compute_priority(move.change_pct).value,
            }
            await db.queue_alert(user_id, move.ticker, payload)
            stats["queued"] += 1
        logger.info("user %s in quiet hours — queued %d alerts", user_id, len(eligible))
        return stats

    # Not in quiet hours — send now
    if len(eligible) >= BATCH_THRESHOLD:
        crossings_dicts = [
            {
                "ticker": m.ticker,
                "change_pct": m.change_pct,
                "prev_price": m.prev_close,
                "price": m.last_price,
            }
            for m in eligible
        ]
        text = alert_threshold_crossed_batch(crossings_dicts)
        # Batch priority = max across all crossings
        max_pct = max(abs(m.change_pct) for m in eligible)
        priority = compute_priority(max_pct)
        top_ticker = max(eligible, key=lambda m: abs(m.change_pct)).ticker
        keyboard = build_alert_keyboard(top_ticker, is_pro=True)
        result = await sender(user_id, text, priority, reply_markup=keyboard)
        if result:
            stats["sent"] += len(eligible)
            for m in eligible:
                try:
                    await db.log_alert_sent(user_id, m.ticker, m.change_pct, priority.value)
                except Exception as exc:
                    logger.warning("alert_log write failed: %s", exc)
    else:
        for move in eligible:
            score_kwargs = (score_overlay or {}).get(move.ticker.upper(), {})
            text = alert_threshold_crossed(
                ticker=move.ticker,
                change_pct=move.change_pct,
                prev_price=move.prev_close,
                last_price=move.last_price,
                session="session",
                score_100=score_kwargs.get("score_100"),
                rating=score_kwargs.get("rating"),
                score_change=score_kwargs.get("score_change"),
                why_moving=score_kwargs.get("why_moving"),
                risk_flag=score_kwargs.get("risk_flag"),
            )
            priority = compute_priority(move.change_pct)
            keyboard = build_alert_keyboard(move.ticker, is_pro=True)
            result = await sender(user_id, text, priority, reply_markup=keyboard)
            if result:
                stats["sent"] += 1
                try:
                    await db.log_alert_sent(user_id, move.ticker, move.change_pct, priority.value)
                except Exception as exc:
                    logger.warning("alert_log write failed: %s", exc)

    return stats


async def dispatch_personal_alerts(
    session_label: str,
    sender: SenderFn | None = None,
) -> dict:
    """
    Main function called by APScheduler after each scan session.
    Also callable directly with a mock sender for testing.
    """
    if not is_trading_day(today_et()):
        logger.info("personal alerts skipped — not a trading day")
        return {"skipped": True}

    _sender = sender or _default_sender

    try:
        profiles = await db.get_all_active_profiles()
    except Exception as exc:
        logger.error("DB unavailable for personal alerts: %s", exc)
        return {"error": str(exc)}

    if not profiles:
        logger.info("no active profiles for personal alerts")
        return {"users": 0}

    # Collect all unique tickers across all users
    all_tickers: set[str] = set()
    for p in profiles:
        all_tickers.update(p.get("watchlist", []))

    if not all_tickers:
        return {"users": len(profiles), "tickers": 0}

    # Batch fetch prices for all tickers at once
    all_moves = await fetch_watchlist_moves(list(all_tickers))
    moves_by_ticker = {m.ticker: m for m in all_moves}

    # One DB pass: load latest Sentinel score + narrative per ticker. Empty
    # overlay on cold start / DB outage — alerts still send, just without
    # the score / why_moving / risk_flag enrichment lines.
    score_overlay = await _score_overlay_for_tickers(list(all_tickers))

    total_sent = total_queued = total_deduped = 0

    for profile in profiles:
        tickers = profile.get("watchlist", [])
        threshold = profile.get("alert_threshold", 2.0)

        crossings = [
            moves_by_ticker[t]
            for t in tickers
            if t in moves_by_ticker and abs(moves_by_ticker[t].change_pct) >= threshold
        ]

        if not crossings:
            continue

        stats = await _send_or_queue(profile, crossings, _sender, score_overlay)
        total_sent += stats["sent"]
        total_queued += stats["queued"]
        total_deduped += stats["deduped"]

    summary = {
        "session": session_label,
        "users_checked": len(profiles),
        "tickers_fetched": len(all_tickers),
        "alerts_sent": total_sent,
        "alerts_queued": total_queued,
        "alerts_deduped": total_deduped,
    }
    logger.info("personal alerts: %s", summary)
    return summary


async def process_queued_alerts(sender: SenderFn | None = None) -> int:
    """
    Process queued alerts for users who are now out of quiet hours.
    Called every 2 minutes by APScheduler.
    Returns number of alerts sent.
    """
    _sender = sender or _default_sender
    sent = 0

    try:
        pending = await db.get_pending_queued_alerts()
    except Exception as exc:
        logger.error("DB unavailable for queued alerts: %s", exc)
        return 0

    # Group by user to check quiet hours once per user
    by_user: dict[int, list[dict]] = {}
    for alert in pending:
        uid = alert["telegram_user_id"]
        by_user.setdefault(uid, []).append(alert)

    # Collect every distinct ticker in the pending queue so we can pull
    # the daily_scores overlay in one shot. By the time these queued
    # alerts thaw out of quiet hours, the post-close run has almost
    # certainly populated daily_scores — so the morning delivery carries
    # full score + narrative even though the original cross fired at night.
    import json as _json
    queued_tickers: set[str] = set()
    for alert in pending:
        payload = alert.get("payload_json")
        if isinstance(payload, str):
            try:
                payload = _json.loads(payload)
            except Exception:
                continue
        if isinstance(payload, dict) and payload.get("ticker"):
            queued_tickers.add(str(payload["ticker"]).upper())
    score_overlay = await _score_overlay_for_tickers(list(queued_tickers))

    for user_id, alerts in by_user.items():
        try:
            profile = await db.get_profile(user_id)
        except Exception:
            continue
        if not profile:
            continue

        snooze_until = profile.get("snooze_until")
        if snooze_until:
            if snooze_until.tzinfo is None:
                snooze_until = snooze_until.replace(tzinfo=timezone.utc)
            if snooze_until > datetime.now(timezone.utc):
                continue

        if is_quiet_time(
            profile.get("quiet_hours_enabled", True),
            profile.get("quiet_hours_start", 22),
            profile.get("quiet_hours_end", 7),
        ):
            continue  # still in quiet hours, skip

        for alert in alerts:
            payload = alert["payload_json"]
            if isinstance(payload, str):
                payload = _json.loads(payload)

            ticker = str(payload.get("ticker", "")).upper()
            score_kwargs = score_overlay.get(ticker, {})
            text = alert_threshold_crossed(
                ticker=payload.get("ticker", ""),
                change_pct=payload.get("change_pct", 0),
                prev_price=payload.get("prev_price", 0),
                last_price=payload.get("price", 0),
                session="earlier session",
                score_100=score_kwargs.get("score_100"),
                rating=score_kwargs.get("rating"),
                score_change=score_kwargs.get("score_change"),
                why_moving=score_kwargs.get("why_moving"),
                risk_flag=score_kwargs.get("risk_flag"),
            )
            priority_val = payload.get("priority", AlertPriority.NORMAL.value)
            try:
                priority = AlertPriority(priority_val)
            except ValueError:
                priority = AlertPriority.NORMAL
            result = await _sender(user_id, text, priority)
            if result:
                await db.mark_queued_sent(alert["id"])
                sent += 1
                try:
                    await db.log_alert_sent(
                        user_id,
                        payload.get("ticker", ""),
                        payload.get("change_pct", 0),
                        priority.value,
                    )
                except Exception as exc:
                    logger.warning("alert_log write failed: %s", exc)

    if sent:
        logger.info("processed %d queued alerts", sent)
    return sent
