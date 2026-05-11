"""Tests for the FMP adapter."""

from __future__ import annotations

import asyncio

import pytest

from app.marketing.data_sources import fmp


def _run(coro):
    return asyncio.run(coro)


def test_no_key_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    assert _run(fmp.fetch_market_movers()) == []


def test_row_to_mover_parses_typical_payload() -> None:
    row = {
        "symbol": "nvda",
        "name": "NVIDIA Corporation",
        "price": "475.32",
        "changesPercentage": "+3.45%",
        "volume": "53212100",
        "marketCap": 1_200_000_000_000,
    }
    mover = fmp._row_to_mover(row, "https://example/fmp")
    assert mover is not None
    assert mover.ticker == "NVDA"
    assert mover.price == 475.32
    assert mover.change_pct == 3.45
    assert mover.volume == 53212100
    assert mover.market_cap == 1_200_000_000_000
    assert mover.company_name == "NVIDIA Corporation"


def test_row_to_mover_returns_none_without_ticker() -> None:
    assert fmp._row_to_mover({"name": "no symbol here"}, "url") is None


def test_fetch_market_movers_dedupes_across_endpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FMP_API_KEY", "fakekey")

    async def fake_get(path: str, params: dict):
        if path.endswith("/gainers"):
            return [
                {"symbol": "NVDA", "name": "NVIDIA", "price": 1.0, "changesPercentage": "1%", "volume": 1, "marketCap": 1},
                {"symbol": "TSLA", "name": "Tesla", "price": 1.0, "changesPercentage": "1%", "volume": 1, "marketCap": 1},
            ]
        if path.endswith("/losers"):
            return [
                {"symbol": "AAPL", "name": "Apple", "price": 1.0, "changesPercentage": "-1%", "volume": 1, "marketCap": 1},
            ]
        if path.endswith("/actives"):
            return [
                {"symbol": "NVDA", "name": "NVIDIA Dup", "price": 1.0, "changesPercentage": "1%", "volume": 1, "marketCap": 1},
            ]
        return []

    monkeypatch.setattr(fmp, "_get", fake_get)

    movers = _run(fmp.fetch_market_movers(limit=10))
    tickers = [m.ticker for m in movers]
    # NVDA appears in both gainers and actives but should appear only once
    assert tickers.count("NVDA") == 1
    assert "TSLA" in tickers
    assert "AAPL" in tickers


def test_fetch_market_movers_respects_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FMP_API_KEY", "fakekey")

    async def fake_get(path, params):
        # Return 5 rows per endpoint
        return [
            {"symbol": f"T{i}{path[-1]}", "name": "x", "price": 1.0, "changesPercentage": "1%", "volume": 1, "marketCap": 1}
            for i in range(5)
        ]

    monkeypatch.setattr(fmp, "_get", fake_get)
    movers = _run(fmp.fetch_market_movers(limit=3))
    assert len(movers) == 3


def test_as_float_handles_percent_and_plus() -> None:
    assert fmp._as_float("+3.45%") == 3.45
    assert fmp._as_float("-1.2") == -1.2
    assert fmp._as_float(None) is None
    assert fmp._as_float("") is None
    assert fmp._as_float("abc") is None
