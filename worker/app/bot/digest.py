"""
Scheduled digest functions called by APScheduler.
- public_premarket_brief(): 8:30 AM ET → @SentinelAI_signals
- personal_eod_digest():    4:30 PM ET → each VIP user's DM
- public_postclose_digest(): 4:30 PM ET → @SentinelAI_signals
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date

from ..scanner import TickerMove, fetch_watchlist_moves
from ..telegram import send_channel_message
from ..watchlist import DEFAULT_WATCHLIST, MOVE_THRESHOLD_PCT
from . import db
from .market_calendar import is_trading_day, today_et
from .templates.telegram_messages import (
    alert_eod_digest,
    alert_silence_day,
    public_postclose_digest,
    public_premarket_brief_active,
    public_premarket_brief_quiet,
)

logger = logging.getLogger(__name__)


async def public_premarket_brief() -> None:
    if not is_trading_day(today_et()):
        logger.info("pre-market brief skipped — not a trading day")
        return

    date_str = today_et().strftime("%a %b %d")
    moves = await fetch_watchlist_moves(DEFAULT_WATCHLIST)
    notable = [m for m in moves if abs(m.change_pct) >= MOVE_THRESHOLD_PCT]

    if notable:
        items = [
            f"<b>{m.ticker}</b> pre-market {m.signed_pct} · "
            f"${m.prev_close:.2f} → ${m.last_price:.2f}"
            for m in sorted(notable, key=lambda x: abs(x.change_pct), reverse=True)[:3]
        ]
        text = public_premarket_brief_active(date_str, items)
    else:
        text = public_premarket_brief_quiet(date_str)

    await send_channel_message(text)
    logger.info("public pre-market brief sent (%d notable)", len(notable))


async def public_eod_digest() -> None:
    if not is_trading_day(today_et()):
        logger.info("public EOD digest skipped — not a trading day")
        return

    date_str = today_et().strftime("%a %b %d")
    moves = await fetch_watchlist_moves(DEFAULT_WATCHLIST)
    significant = [m for m in moves if abs(m.change_pct) >= MOVE_THRESHOLD_PCT]

    movers = [
        {"ticker": m.ticker, "change_pct": m.change_pct, "price": m.last_price}
        for m in sorted(significant, key=lambda x: abs(x.change_pct), reverse=True)
    ]
    text = public_postclose_digest(date_str, movers, notes=[])
    await send_channel_message(text)
    logger.info("public EOD digest sent (%d movers)", len(movers))


async def _send_personal_digest(user_id: int, profile: dict) -> None:
    from ..telegram import send_channel_message as _send

    tickers = profile.get("watchlist", [])
    threshold = profile.get("alert_threshold", MOVE_THRESHOLD_PCT)
    date_str = today_et().strftime("%a %b %d")

    if not tickers:
        return

    moves = await fetch_watchlist_moves(tickers)
    crossings_raw = [m for m in moves if abs(m.change_pct) >= threshold]
    quiet_raw = [m for m in moves if abs(m.change_pct) < threshold]

    crossings = [
        {"ticker": m.ticker, "change_pct": m.change_pct, "price": m.last_price}
        for m in sorted(crossings_raw, key=lambda x: abs(x.change_pct), reverse=True)
    ]
    quiet_tickers = [m.ticker for m in quiet_raw]

    text = alert_eod_digest(crossings, quiet_tickers, date_str)

    try:
        import os
        import httpx
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": user_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload)
        data = resp.json()
        if not data.get("ok"):
            logger.warning(
                "failed to send digest to %s: %s %s",
                user_id, data.get("error_code"), data.get("description"),
            )
    except Exception as exc:
        logger.error("error sending personal digest to %s: %s", user_id, exc)


async def personal_eod_digests() -> None:
    if not is_trading_day(today_et()):
        logger.info("personal EOD digests skipped — not a trading day")
        return

    profiles = await db.get_all_active_profiles()
    if not profiles:
        logger.info("no active profiles for personal EOD digest")
        return

    await asyncio.gather(*[
        _send_personal_digest(p["telegram_user_id"], p)
        for p in profiles
    ], return_exceptions=True)
    logger.info("personal EOD digests sent to %d users", len(profiles))
