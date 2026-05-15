from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Awaitable, Callable, Iterable, Sequence

import httpx

from ..marketing.data_sources.earnings_calendar import fetch_earnings_dates
from ..scanner import TickerMove, fetch_watchlist_moves
from ..watchlist import DEFAULT_WATCHLIST

logger = logging.getLogger(__name__)

MARKET_INDEX_TICKERS = ("SPY", "QQQ")
SECTOR_ETFS: dict[str, str] = {
    "XLK": "Tech",
    "XLF": "Financials",
    "XLE": "Energy",
    "XLV": "Health Care",
    "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples",
    "XLI": "Industrials",
    "XLU": "Utilities",
    "XLB": "Materials",
    "XLRE": "Real Estate",
}
FEAR_GREED_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"

MoveFetcher = Callable[[Iterable[str]], Awaitable[list[TickerMove]]]
EarningsFetcher = Callable[..., Awaitable[dict[str, date | None]]]
FearGreedFetcher = Callable[[], Awaitable["FearGreedSnapshot | None"]]


@dataclass(frozen=True)
class FearGreedSnapshot:
    value: int
    rating: str
    previous_value: int | None = None


def _signed_pct(value: float) -> str:
    return f"{value:+.1f}%"


def _move_by_ticker(moves: Sequence[TickerMove]) -> dict[str, TickerMove]:
    return {m.ticker.upper(): m for m in moves}


def _format_index_moves(moves: Sequence[TickerMove], *, label: str) -> str | None:
    by_ticker = _move_by_ticker(moves)
    parts: list[str] = []
    for ticker in MARKET_INDEX_TICKERS:
        move = by_ticker.get(ticker)
        if move is not None:
            parts.append(f"{ticker} {_signed_pct(move.change_pct)}")
    if not parts:
        return None
    return f"{label}: " + " · ".join(parts)


def _format_fear_greed(snapshot: FearGreedSnapshot | None, *, include_change: bool) -> str | None:
    if snapshot is None:
        return None
    line = f"Fear & Greed: {snapshot.value} ({snapshot.rating})"
    if include_change and snapshot.previous_value is not None:
        delta = snapshot.value - snapshot.previous_value
        line += f" · {delta:+d} vs prior"
    return line


def _format_earnings(
    earnings: dict[str, date | None],
    target_date: date,
    *,
    label: str,
) -> str | None:
    tickers = sorted(
        ticker for ticker, report_date in earnings.items() if report_date == target_date
    )
    if not tickers:
        return None
    shown = tickers[:3]
    suffix = f" · {len(tickers) - len(shown)} more" if len(tickers) > len(shown) else ""
    return f"{label}: " + " · ".join(shown) + suffix


def _format_activity(moves: Sequence[TickerMove]) -> str | None:
    ranked = sorted(
        moves,
        key=lambda m: (
            m.relative_volume if m.relative_volume is not None else 0.0,
            abs(m.change_pct),
        ),
        reverse=True,
    )
    if not ranked:
        return None
    parts = []
    for move in ranked[:3]:
        if move.relative_volume is not None:
            parts.append(f"{move.ticker} {move.relative_volume:.1f}x vol")
        else:
            parts.append(f"{move.ticker} {_signed_pct(move.change_pct)}")
    return "Morning activity: " + " · ".join(parts)


def _format_sector_rotation(moves: Sequence[TickerMove]) -> str | None:
    ranked = sorted(moves, key=lambda m: m.change_pct, reverse=True)
    if len(ranked) < 2:
        return None
    leader = ranked[0]
    laggard = ranked[-1]
    leader_name = SECTOR_ETFS.get(leader.ticker.upper(), leader.ticker.upper())
    laggard_name = SECTOR_ETFS.get(laggard.ticker.upper(), laggard.ticker.upper())
    return (
        "Sector rotation: "
        f"{leader_name} {_signed_pct(leader.change_pct)} vs "
        f"{laggard_name} {_signed_pct(laggard.change_pct)}"
    )


async def _try(label: str, action: Callable[[], Awaitable[str | None]]) -> str | None:
    try:
        return await action()
    except Exception as exc:
        logger.warning("quiet context skipped %s: %s", label, exc)
        return None


async def fetch_fear_greed_snapshot() -> FearGreedSnapshot | None:
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(FEAR_GREED_URL)
        if resp.status_code != 200:
            logger.warning("fear_greed returned HTTP %s", resp.status_code)
            return None
        data = resp.json()
        fg = data.get("fear_and_greed") if isinstance(data, dict) else None
        if not isinstance(fg, dict):
            return None
        value_raw = fg.get("score") or fg.get("value")
        rating_raw = fg.get("rating") or fg.get("status")
        previous_raw = fg.get("previous_close") or fg.get("previousClose")
        if value_raw is None or rating_raw is None:
            return None
        previous = int(round(float(previous_raw))) if previous_raw is not None else None
        return FearGreedSnapshot(
            value=int(round(float(value_raw))),
            rating=str(rating_raw).title(),
            previous_value=previous,
        )
    except Exception as exc:
        logger.warning("fear_greed raised %s", exc)
        return None


async def build_premarket_quiet_bullets(
    *,
    today: date,
    move_fetcher: MoveFetcher = fetch_watchlist_moves,
    earnings_fetcher: EarningsFetcher = fetch_earnings_dates,
    fear_greed_fetcher: FearGreedFetcher = fetch_fear_greed_snapshot,
) -> list[str]:
    bullets: list[str] = []

    async def index_line() -> str | None:
        return _format_index_moves(await move_fetcher(MARKET_INDEX_TICKERS), label="SPY/QQQ overnight")

    async def fear_line() -> str | None:
        return _format_fear_greed(await fear_greed_fetcher(), include_change=False)

    async def earnings_line() -> str | None:
        earnings = await earnings_fetcher(DEFAULT_WATCHLIST, today=today)
        return _format_earnings(earnings, today, label="Earnings today")

    for line in await _collect(index_line, fear_line, earnings_line):
        bullets.append(line)
    return bullets


async def build_midday_quiet_bullets(
    *,
    watchlist_moves: Sequence[TickerMove],
    move_fetcher: MoveFetcher = fetch_watchlist_moves,
) -> list[str]:
    bullets: list[str] = []

    async def activity_line() -> str | None:
        return _format_activity(watchlist_moves)

    async def sector_line() -> str | None:
        return _format_sector_rotation(await move_fetcher(SECTOR_ETFS.keys()))

    async def breadth_line() -> str | None:
        if not watchlist_moves:
            return None
        up = sum(1 for move in watchlist_moves if move.change_pct > 0)
        down = sum(1 for move in watchlist_moves if move.change_pct < 0)
        return f"Watchlist breadth: {up} up · {down} down · {len(watchlist_moves)} tracked"

    for line in await _collect(activity_line, sector_line, breadth_line):
        bullets.append(line)
    return bullets


async def build_eod_quiet_bullets(
    *,
    today: date,
    move_fetcher: MoveFetcher = fetch_watchlist_moves,
    earnings_fetcher: EarningsFetcher = fetch_earnings_dates,
    fear_greed_fetcher: FearGreedFetcher = fetch_fear_greed_snapshot,
) -> list[str]:
    bullets: list[str] = []
    tomorrow = today + timedelta(days=1)

    async def close_line() -> str | None:
        return _format_index_moves(await move_fetcher(MARKET_INDEX_TICKERS), label="Market close")

    async def fear_line() -> str | None:
        return _format_fear_greed(await fear_greed_fetcher(), include_change=True)

    async def earnings_line() -> str | None:
        earnings = await earnings_fetcher(DEFAULT_WATCHLIST, today=today)
        return _format_earnings(earnings, tomorrow, label="Earnings tomorrow")

    for line in await _collect(close_line, fear_line, earnings_line):
        bullets.append(line)
    return bullets


async def _collect(*builders: Callable[[], Awaitable[str | None]]) -> list[str]:
    out: list[str] = []
    for builder in builders:
        line = await _try(getattr(builder, "__name__", "bullet"), builder)
        if line:
            out.append(line)
    return out
