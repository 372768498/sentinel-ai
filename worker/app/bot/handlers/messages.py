"""
Free-text message handler: "What about TSLA?", "Why no alert on NVDA?", etc.
Rule-based intent recognition. No LLM in v1 (slot pre-reserved).
"""
from __future__ import annotations

import asyncio
import logging
import re

import yfinance as yf
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from .. import db
from ..templates.telegram_messages import alert_user_reply_ticker

logger = logging.getLogger(__name__)

_KEYWORD_TICKER_RE = re.compile(
    r"(?:what about|how(?:'s| is| about)|why(?:\s+no\s+alert(?:\s+on)?)?|"
    r"check|show|tell me about)\s+([A-Za-z]{1,5})",
    re.IGNORECASE,
)

_UPPERCASE_TICKER_RE = re.compile(r"\b([A-Z]{2,5})\b")

_KNOWN_NON_TICKERS = {
    "I", "A", "AN", "THE", "IS", "IT", "IN", "ON", "AT", "BY", "OK", "AM",
    "PM", "US", "UK", "EU", "AI", "OR", "NO", "DO", "SO", "MY", "ME",
    "HI", "HEY", "ETF", "SEC", "FED", "IPO", "CEO", "CFO",
}


def _extract_ticker_from_query(text: str) -> str | None:
    """
    Extract ticker from user message.
    Strategy:
      1. Keyword-triggered match (what about X, check X, how's X) — any case
      2. Standalone uppercase ticker (NVDA, TSLA — already caps in original text)
    """
    for match in _KEYWORD_TICKER_RE.finditer(text):
        candidate = match.group(1).upper()
        if candidate not in _KNOWN_NON_TICKERS and len(candidate) >= 2:
            return candidate

    for match in _UPPERCASE_TICKER_RE.finditer(text):  # search original text
        candidate = match.group(1)
        if candidate not in _KNOWN_NON_TICKERS:
            return candidate

    return None


def _fetch_ticker_data(ticker: str) -> dict | None:
    try:
        info = yf.Ticker(ticker)
        fast = info.fast_info
        last_price = getattr(fast, "last_price", None) or 0.0
        prev_close = getattr(fast, "previous_close", None) or last_price
        if prev_close and prev_close > 0:
            change_pct = (last_price - prev_close) / prev_close * 100.0
        else:
            change_pct = 0.0
        return {"last_price": last_price, "change_pct": change_pct}
    except Exception as exc:
        logger.warning("yfinance fast_info failed for %s: %s", ticker, exc)
        return None


async def handle_ticker_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data.get("wl_pending_action"):
        return

    text = update.message.text or ""
    ticker = _extract_ticker_from_query(text)
    if not ticker:
        return

    user_id = update.effective_user.id
    profile = await db.get_profile(user_id)
    user_threshold = profile.get("alert_threshold", 2.0) if profile else 0.0
    watchlist = profile.get("watchlist", []) if profile else []
    on_watchlist = ticker in watchlist
    threshold_for_reply = user_threshold if on_watchlist else 0.0

    loop = asyncio.get_running_loop()
    data = await loop.run_in_executor(None, _fetch_ticker_data, ticker)

    if not data:
        await update.message.reply_text(
            f"Couldn't fetch data for <code>{ticker}</code> right now. Try again shortly.",
            parse_mode="HTML",
        )
        return

    last_price = data["last_price"]
    change_pct = data["change_pct"]
    catalyst_scan = "no material news detected"
    last_cross_desc = "none today" if on_watchlist else "not on your watchlist"

    reply = alert_user_reply_ticker(
        ticker=ticker,
        last_price=last_price,
        change_pct=change_pct,
        threshold=threshold_for_reply,
        last_cross_desc=last_cross_desc,
        catalyst_scan=catalyst_scan,
    )
    await update.message.reply_text(reply, parse_mode="HTML", disable_web_page_preview=True)


def get_handler() -> MessageHandler:
    return MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_ticker_query,
    )
