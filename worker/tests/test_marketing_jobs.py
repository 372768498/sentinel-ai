"""Test publish_marketing_alerts with monkey-patched scanner."""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.marketing import jobs as jobs_module
from app.marketing.composer import Composer
from app.marketing.publisher import Publisher
from app.marketing.x_client import XClient


@dataclass
class _Move:
    ticker: str
    prev_close: float
    last_price: float
    change_pct: float


@pytest.fixture
def fake_moves(monkeypatch):
    moves = [
        _Move("AAPL", 100.0, 102.0, 2.0),   # ~62 score, below 80
        _Move("NVDA", 100.0, 106.0, 6.0),   # >80
        _Move("TSLA", 100.0, 92.0, -8.0),   # >80 (negative)
        _Move("MSFT", 100.0, 100.5, 0.5),   # tiny
    ]

    async def _fake_fetch(*args, **kwargs):
        return moves

    async def _fake_catalyst(*args, **kwargs):
        return None  # always exercise fallback_source path in tests

    monkeypatch.setattr("app.marketing.jobs.fetch_watchlist_moves", _fake_fetch)
    monkeypatch.setattr("app.marketing.jobs.latest_catalyst", _fake_catalyst)
    # Reset publisher singleton so monkeypatched env propagates
    monkeypatch.setattr(jobs_module, "_publisher_singleton", None)
    return moves


@pytest.mark.asyncio
async def test_publish_marketing_alerts_filters_by_threshold(fake_moves, monkeypatch):
    monkeypatch.setenv("MARKETING_SCORE_THRESHOLD", "80")
    monkeypatch.setenv("X_DRY_RUN", "true")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    result = await jobs_module.publish_marketing_alerts("test-session")
    assert result["scanned"] == 4
    # NVDA and TSLA pass; AAPL and MSFT don't
    qualified_tickers = {o["ticker"] for o in result["outcomes"]}
    assert "NVDA" in qualified_tickers
    assert "TSLA" in qualified_tickers
    assert "AAPL" not in qualified_tickers
    assert "MSFT" not in qualified_tickers


@pytest.mark.asyncio
async def test_publish_marketing_alerts_all_dry_run(fake_moves, monkeypatch):
    monkeypatch.setenv("MARKETING_SCORE_THRESHOLD", "80")
    monkeypatch.setenv("X_DRY_RUN", "true")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    result = await jobs_module.publish_marketing_alerts("test")
    for outcome in result["outcomes"]:
        assert outcome.get("dry_run") is True
        assert outcome.get("posted") is False
        assert outcome.get("redline_ok") is True


@pytest.mark.asyncio
async def test_publish_marketing_alerts_high_threshold_skips_all(fake_moves, monkeypatch):
    monkeypatch.setenv("MARKETING_SCORE_THRESHOLD", "99")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    result = await jobs_module.publish_marketing_alerts("test")
    assert result["qualified"] == 0
    assert result["outcomes"] == []
