"""Tests for FMP earnings-calendar adapter."""
from __future__ import annotations

from datetime import date

import pytest

from app.marketing.data_sources import earnings_calendar


@pytest.fixture(autouse=True)
def _key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FMP_API_KEY", "fake-key")


async def _fake_fetch(rows):
    async def _inner(ticker: str):
        return rows
    return _inner


@pytest.mark.asyncio
async def test_returns_next_future_date() -> None:
    rows = [
        {"symbol": "NVDA", "date": "2026-04-01"},  # past
        {"symbol": "NVDA", "date": "2026-08-21"},  # future
        {"symbol": "NVDA", "date": "2026-05-21"},  # nearer future
    ]
    fetcher = await _fake_fetch(rows)
    out = await earnings_calendar.fetch_next_earnings_date(
        "NVDA", today=date(2026, 5, 12), fetcher=fetcher
    )
    assert out == date(2026, 5, 21)


@pytest.mark.asyncio
async def test_today_counts_as_future() -> None:
    rows = [{"symbol": "X", "date": "2026-05-12"}]
    fetcher = await _fake_fetch(rows)
    out = await earnings_calendar.fetch_next_earnings_date(
        "X", today=date(2026, 5, 12), fetcher=fetcher
    )
    assert out == date(2026, 5, 12)


@pytest.mark.asyncio
async def test_all_past_returns_none() -> None:
    rows = [{"symbol": "X", "date": "2026-04-01"}, {"symbol": "X", "date": "2026-03-15"}]
    fetcher = await _fake_fetch(rows)
    out = await earnings_calendar.fetch_next_earnings_date(
        "X", today=date(2026, 5, 12), fetcher=fetcher
    )
    assert out is None


@pytest.mark.asyncio
async def test_empty_response_returns_none() -> None:
    fetcher = await _fake_fetch([])
    out = await earnings_calendar.fetch_next_earnings_date(
        "X", today=date(2026, 5, 12), fetcher=fetcher
    )
    assert out is None


@pytest.mark.asyncio
async def test_none_fetcher_returns_none() -> None:
    async def fetcher(_ticker):
        return None
    out = await earnings_calendar.fetch_next_earnings_date(
        "X", today=date(2026, 5, 12), fetcher=fetcher
    )
    assert out is None


@pytest.mark.asyncio
async def test_malformed_rows_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        "not a dict",
        {"symbol": "X"},  # missing date
        {"symbol": "X", "date": None},
        {"symbol": "X", "date": "garbage"},
        {"symbol": "X", "date": "2026-09-30"},
    ]
    async def fetcher(_ticker):
        return rows
    out = await earnings_calendar.fetch_next_earnings_date(
        "X", today=date(2026, 5, 12), fetcher=fetcher
    )
    assert out == date(2026, 9, 30)


@pytest.mark.asyncio
async def test_date_with_time_suffix_parses() -> None:
    rows = [{"symbol": "X", "date": "2026-06-15T20:30:00"}]
    async def fetcher(_ticker):
        return rows
    out = await earnings_calendar.fetch_next_earnings_date(
        "X", today=date(2026, 5, 12), fetcher=fetcher
    )
    assert out == date(2026, 6, 15)


@pytest.mark.asyncio
async def test_missing_key_short_circuits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    out = await earnings_calendar.fetch_next_earnings_date(
        "NVDA", today=date(2026, 5, 12)
    )
    assert out is None


@pytest.mark.asyncio
async def test_batch_helper_per_ticker() -> None:
    calls: list[str] = []

    async def fetcher(ticker):
        calls.append(ticker)
        if ticker == "NVDA":
            return [{"symbol": "NVDA", "date": "2026-05-20"}]
        return []

    out = await earnings_calendar.fetch_earnings_dates(
        ["NVDA", "AMD"], today=date(2026, 5, 12), fetcher=fetcher
    )
    assert out == {"NVDA": date(2026, 5, 20), "AMD": None}
    assert calls == ["NVDA", "AMD"]
