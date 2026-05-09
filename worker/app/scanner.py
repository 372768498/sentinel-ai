from __future__ import annotations

import asyncio
import logging
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

    @property
    def arrow(self) -> str:
        return "📈" if self.change_pct > 0 else "📉"

    @property
    def signed_pct(self) -> str:
        sign = "+" if self.change_pct > 0 else ""
        return f"{sign}{self.change_pct:.2f}%"


def _fetch_one(ticker: str) -> TickerMove | None:
    try:
        data = yf.Ticker(ticker).history(period="2d", interval="1d", auto_adjust=False)
    except Exception as exc:
        logger.warning("yfinance fetch failed for %s: %s", ticker, exc)
        return None

    if data is None or len(data) < 2:
        logger.warning("yfinance returned insufficient rows for %s", ticker)
        return None

    prev_close = float(data["Close"].iloc[-2])
    last_price = float(data["Close"].iloc[-1])
    if prev_close <= 0:
        return None

    change_pct = (last_price - prev_close) / prev_close * 100.0
    return TickerMove(
        ticker=ticker,
        prev_close=prev_close,
        last_price=last_price,
        change_pct=change_pct,
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
    header = f"<b>📊 Sentinel AI · {session_label}</b>"
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    if not moves:
        return (
            f"{header}\n<i>{timestamp}</i>\n\n"
            f"Watchlist quiet — no tickers moved beyond ±{MOVE_THRESHOLD_PCT:.0f}% today."
        )

    lines = [header, f"<i>{timestamp}</i>", ""]
    for m in sorted(moves, key=lambda x: abs(x.change_pct), reverse=True):
        lines.append(
            f"{m.arrow} <b>{m.ticker}</b> · {m.signed_pct} · "
            f"${m.prev_close:.2f} → ${m.last_price:.2f}"
        )
    lines.append("")
    lines.append("<i>Not financial advice. For information only.</i>")
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
