from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.bot.quiet_context import (
    FearGreedSnapshot,
    build_eod_quiet_bullets,
    build_midday_quiet_bullets,
    build_premarket_quiet_bullets,
)
from app.bot.templates.telegram_messages import (
    public_midday_brief_quiet,
    public_postclose_digest,
    public_premarket_brief_quiet,
)
from app.scanner import TickerMove


def _move(
    ticker: str,
    change_pct: float,
    *,
    relative_volume: float | None = None,
) -> TickerMove:
    return TickerMove(
        ticker=ticker,
        prev_close=100.0,
        last_price=100.0 + change_pct,
        change_pct=change_pct,
        volume=1_000_000,
        relative_volume=relative_volume,
    )


def test_quiet_templates_render_fallback_bullets() -> None:
    bullets = [
        "SPY/QQQ overnight: SPY +0.3% · QQQ +0.1%",
        "Fear & Greed: 62 (Greed)",
    ]

    premarket = public_premarket_brief_quiet("Thu May 14", bullets)
    midday = public_midday_brief_quiet("Thu May 14", bullets)
    eod = public_postclose_digest("Thu May 14", [], quiet_bullets=bullets)

    for rendered in (premarket, midday, eod):
        assert rendered.count("• ") >= 2
        assert "Context, not financial advice." in rendered


@pytest.mark.asyncio
async def test_premarket_quiet_bullets_skip_failed_sources() -> None:
    async def move_fetcher(tickers):
        return [_move("SPY", 0.3), _move("QQQ", 0.1)]

    async def earnings_fetcher(*args, **kwargs):
        raise RuntimeError("FMP unavailable")

    async def fear_greed_fetcher():
        return FearGreedSnapshot(value=62, rating="Greed")

    bullets = await build_premarket_quiet_bullets(
        today=date(2026, 5, 14),
        move_fetcher=move_fetcher,
        earnings_fetcher=earnings_fetcher,
        fear_greed_fetcher=fear_greed_fetcher,
    )

    assert len(bullets) == 2
    assert bullets[0].startswith("SPY/QQQ overnight")
    assert bullets[1] == "Fear & Greed: 62 (Greed)"


@pytest.mark.asyncio
async def test_midday_quiet_bullets_include_activity_and_sector_rotation() -> None:
    watchlist_moves = [
        _move("NVDA", 0.4, relative_volume=1.8),
        _move("AMD", -0.2, relative_volume=1.4),
        _move("AAPL", 0.1, relative_volume=1.1),
    ]

    async def sector_fetcher(tickers):
        return [_move("XLK", 0.8), _move("XLE", -0.5)]

    bullets = await build_midday_quiet_bullets(
        watchlist_moves=watchlist_moves,
        move_fetcher=sector_fetcher,
    )

    assert len(bullets) >= 2
    assert bullets[0].startswith("Morning activity:")
    assert any("Sector rotation:" in bullet for bullet in bullets)


@pytest.mark.asyncio
async def test_eod_quiet_bullets_include_close_fear_greed_and_tomorrow_earnings() -> None:
    today = date(2026, 5, 14)

    async def move_fetcher(tickers):
        return [_move("SPY", -0.2), _move("QQQ", 0.1)]

    async def earnings_fetcher(*args, **kwargs):
        return {"NVDA": today + timedelta(days=1), "AMD": today + timedelta(days=1)}

    async def fear_greed_fetcher():
        return FearGreedSnapshot(value=58, rating="Greed", previous_value=62)

    bullets = await build_eod_quiet_bullets(
        today=today,
        move_fetcher=move_fetcher,
        earnings_fetcher=earnings_fetcher,
        fear_greed_fetcher=fear_greed_fetcher,
    )

    assert len(bullets) == 3
    assert bullets[0].startswith("Market close:")
    assert "vs prior" in bullets[1]
    assert bullets[2] == "Earnings tomorrow: AMD · NVDA"
