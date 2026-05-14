from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

import yfinance as yf

from .telegram import send_channel_message
from .watchlist import DEFAULT_WATCHLIST, MOVE_THRESHOLD_PCT

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TickerMove:
    ticker: str
    prev_close: float
    last_price: float
    change_pct: float
    volume: int | None = None
    relative_volume: float | None = None

    @property
    def arrow(self) -> str:
        return "📈" if self.change_pct > 0 else "📉"

    @property
    def signed_pct(self) -> str:
        sign = "+" if self.change_pct > 0 else ""
        return f"{sign}{self.change_pct:.2f}%"


def _safe_float(value) -> float | None:
    """yfinance fast_info attrs occasionally return nan / None / numpy types."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _fetch_one(ticker: str) -> TickerMove | None:
    """
    Pull a live-as-of-fire-time quote.

    Uses yfinance.fast_info (Yahoo's real-time endpoint) so the pre-market slot
    actually sees pre-market quotes instead of replaying yesterday's close.
    `period="2d", interval="1d"` previously returned the prior session's two
    daily bars during pre-market hours — that was the 5/12-5/14 stale-data bug.
    """
    try:
        t = yf.Ticker(ticker)
        info = t.fast_info  # type: ignore[attr-defined]
        prev_close = _safe_float(getattr(info, "previous_close", None))
        last_price = _safe_float(getattr(info, "last_price", None))
        last_volume = getattr(info, "last_volume", None)
    except Exception as exc:
        logger.warning("yfinance fast_info failed for %s: %s", ticker, exc)
        return None

    if not prev_close or prev_close <= 0 or last_price is None:
        logger.warning("yfinance returned unusable quote for %s", ticker)
        return None

    change_pct = (last_price - prev_close) / prev_close * 100.0

    avg_volume: float | None = None
    try:
        hist = t.history(period="1mo", interval="1d", auto_adjust=False)
        if hist is not None and "Volume" in hist and len(hist) > 0:
            avg = float(hist["Volume"].mean())
            if avg > 0:
                avg_volume = avg
    except Exception as exc:
        logger.debug("avg-volume fetch failed for %s: %s", ticker, exc)

    volume_int: int | None = None
    volume_float = _safe_float(last_volume)
    if volume_float is not None and volume_float >= 0:
        volume_int = int(volume_float)

    rel_vol: float | None = None
    if volume_int is not None and avg_volume:
        rel_vol = volume_int / avg_volume

    return TickerMove(
        ticker=ticker,
        prev_close=prev_close,
        last_price=last_price,
        change_pct=change_pct,
        volume=volume_int,
        relative_volume=rel_vol,
    )


async def fetch_watchlist_moves(
    tickers: Iterable[str] = DEFAULT_WATCHLIST,
) -> list[TickerMove]:
    loop = asyncio.get_running_loop()
    results = await asyncio.gather(
        *[loop.run_in_executor(None, _fetch_one, t) for t in tickers]
    )
    return [r for r in results if r is not None]


def format_alert(moves: list[TickerMove], session_label: str) -> str:
    """v1 Radar shape used by /api/scan/run ops endpoint."""
    header = f"<b>📊 Sentinel AI · {session_label}</b>"
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    if not moves:
        return (
            f"{header}\n<i>{timestamp}</i>\n\n"
            f"Watchlist quiet — no tickers moved beyond ±{MOVE_THRESHOLD_PCT:.0f}% today.\n\n"
            "<i>Context, not financial advice.</i>"
        )

    lines = [header, f"<i>{timestamp}</i>", ""]
    for m in sorted(moves, key=lambda x: abs(x.change_pct), reverse=True):
        head = (
            f"{m.arrow} <b>{m.ticker}</b> · ${m.last_price:.2f} · {m.signed_pct}"
        )
        detail_parts: list[str] = []
        if m.relative_volume is not None:
            detail_parts.append(f"Vol {m.relative_volume:.1f}x avg")
        detail_parts.append(f"prev ${m.prev_close:.2f}")
        lines.append(head)
        lines.append("   " + " · ".join(detail_parts))
    lines.append("")
    lines.append("Sources: Yahoo Finance · SEC EDGAR")
    lines.append("Full breakdown → <a href=\"https://sentinelai.com\">sentinelai.com</a>")
    lines.append("")
    lines.append("<i>Context, not financial advice.</i>")
    return "\n".join(lines)


async def run_scan_and_push(session_label: str) -> dict:
    logger.info("starting scan: %s", session_label)
    moves = await fetch_watchlist_moves()
    significant = [m for m in moves if abs(m.change_pct) >= MOVE_THRESHOLD_PCT]

    text = format_alert(significant, session_label)
    result = await send_channel_message(text)
    return {
        "session": session_label,
        "scanned": len(moves),
        "significant": len(significant),
        "message_id": result.get("message_id"),
    }
