"""Tests for opportunities + signal_layer."""

from __future__ import annotations

import asyncio

import pytest

from app.marketing.intel import TickerBuzz
from app.marketing.data_sources.fmp import MarketMover
from app.marketing.data_sources.x_serp import SocialSignal
from app.marketing.opportunities import (
    ACTION_CREATE_CONTENT,
    ACTION_IGNORE,
    ACTION_WATCH,
    INTENT_HIGH_INTENT_QUESTION,
    INTENT_MARKET_MOVER,
    Opportunity,
    derive_action,
    rank_opportunities,
)
from app.marketing.signal_layer import compute_x_score, scan_growth_opportunities, scan_x_opportunities
from datetime import datetime, timezone


def _tweet(tid: str, likes: int, author: str = "u1") -> dict:
    return {
        "id": tid,
        "text": f"sample tweet {tid}",
        "author_id": author,
        "created_at": None,
        "metrics": {"like_count": likes, "retweet_count": 0, "reply_count": 0, "quote_count": 0},
    }


def _buzz(ticker: str, sample_count: int, top_likes: list[int]) -> TickerBuzz:
    return TickerBuzz(
        ticker=ticker,
        sample_count=sample_count,
        top_engagement=[_tweet(f"t{i}", lk) for i, lk in enumerate(top_likes)],
    )


def test_derive_action_thresholds() -> None:
    assert derive_action(90) == ACTION_CREATE_CONTENT
    assert derive_action(70) == ACTION_CREATE_CONTENT
    assert derive_action(50) == ACTION_WATCH
    assert derive_action(30) == ACTION_WATCH
    assert derive_action(10) == ACTION_IGNORE


def test_compute_x_score_combines_breadth_and_peak() -> None:
    # 30 samples → sample_signal capped at 60; top_like 200 → top_signal capped at 40
    score, top_like = compute_x_score(_buzz("NVDA", 30, [200, 80, 50]))
    assert score == 100
    assert top_like == 200

    # Low breadth, mid engagement: 5 samples → 10; top 50 → 10 → score 20
    score2, _ = compute_x_score(_buzz("AAPL", 5, [50, 20]))
    assert score2 == 20

    # No engagement at all
    score3, top3 = compute_x_score(_buzz("XYZ", 0, []))
    assert (score3, top3) == (0, 0)


def test_rank_opportunities_sorts_desc_with_ticker_tiebreak() -> None:
    a = Opportunity("OP-1", "x", "AAPL", "ticker_buzz", "", None, None, 80, 0, ACTION_CREATE_CONTENT)
    b = Opportunity("OP-2", "x", "TSLA", "ticker_buzz", "", None, None, 80, 0, ACTION_CREATE_CONTENT)
    c = Opportunity("OP-3", "x", "NVDA", "ticker_buzz", "", None, None, 95, 0, ACTION_CREATE_CONTENT)
    ranked = rank_opportunities([a, b, c])
    assert [o.ticker for o in ranked] == ["NVDA", "AAPL", "TSLA"]


class FakeXClient:
    def __init__(self, by_ticker: dict[str, TickerBuzz]) -> None:
        self.by_ticker = by_ticker
        self.dry_run = False
        self.bearer_token = "fake"

    async def search(self, query: str, *, max_results: int = 20) -> list[dict]:  # not used here
        return []


async def _fake_measure(ticker: str, *, client=None, max_results: int = 30) -> TickerBuzz:
    return client.by_ticker.get(ticker, TickerBuzz(ticker=ticker, sample_count=0, top_engagement=[]))


def test_scan_x_returns_empty_when_no_bearer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("X_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("X_DRY_RUN", raising=False)
    result = asyncio.run(scan_x_opportunities(["NVDA", "AAPL"]))
    assert result == []


def test_scan_x_returns_empty_when_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("X_BEARER_TOKEN", "fake")
    monkeypatch.setenv("X_DRY_RUN", "true")
    result = asyncio.run(scan_x_opportunities(["NVDA"]))
    assert result == []


def test_scan_x_filters_by_min_score_and_ranks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("X_BEARER_TOKEN", "fake")
    monkeypatch.setenv("X_DRY_RUN", "false")
    fake_client = FakeXClient({
        "NVDA": _buzz("NVDA", 30, [200, 100, 50]),  # score 100
        "AAPL": _buzz("AAPL", 15, [60, 20]),         # 30 + 12 = 42
        "TSLA": _buzz("TSLA", 25, [120, 80, 30]),    # 50 + 24 = 74
        "WEAK": _buzz("WEAK", 5, [10]),              # 10 + 2 = 12
    })
    monkeypatch.setattr("app.marketing.signal_layer.measure_ticker_buzz", _fake_measure)

    result = asyncio.run(
        scan_x_opportunities(
            ["NVDA", "AAPL", "TSLA", "WEAK"],
            min_score=70,
            client=fake_client,
        )
    )
    assert [o.ticker for o in result] == ["NVDA", "TSLA"]
    assert result[0].opportunity_score == 100
    assert result[0].suggested_action == ACTION_CREATE_CONTENT
    assert result[0].evidence["sample_count"] == 30
    assert result[0].evidence["top_like_count"] == 200


def test_scan_x_continues_when_one_ticker_throws(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("X_BEARER_TOKEN", "fake")
    monkeypatch.setenv("X_DRY_RUN", "false")
    fake_client = FakeXClient({"NVDA": _buzz("NVDA", 30, [200])})

    async def measure(ticker: str, *, client=None, max_results: int = 30) -> TickerBuzz:
        if ticker == "BROKEN":
            raise RuntimeError("api blew up")
        return client.by_ticker[ticker]

    monkeypatch.setattr("app.marketing.signal_layer.measure_ticker_buzz", measure)
    result = asyncio.run(
        scan_x_opportunities(["BROKEN", "NVDA"], min_score=50, client=fake_client)
    )
    assert [o.ticker for o in result] == ["NVDA"]


def test_scan_growth_uses_serp_fallback_without_x_bearer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("X_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("X_DRY_RUN", raising=False)

    async def fake_serp(tickers):
        return [
            SocialSignal(
                source="tavily",
                query='site:x.com "$NVDA" risk',
                ticker="NVDA",
                title="Is $NVDA risk getting crowded?",
                url="https://x.com/u/status/1",
                snippet="Investors are asking whether NVDA risk is now one-sided.",
                observed_at=datetime.now(timezone.utc),
                estimated_engagement=45,
                intent="high_intent_question",
            )
        ]

    async def fake_quotes(tickers):
        return []

    monkeypatch.setattr("app.marketing.signal_layer.scan_x_serp_signals", fake_serp)
    monkeypatch.setattr("app.marketing.signal_layer.fetch_quotes_for_tickers", fake_quotes)

    result = asyncio.run(scan_growth_opportunities(["NVDA"], min_score=70))

    assert len(result) == 1
    assert result[0].ticker == "NVDA"
    assert result[0].source == "tavily"
    assert result[0].intent == INTENT_HIGH_INTENT_QUESTION
    assert result[0].suggested_action == ACTION_CREATE_CONTENT


def test_scan_growth_uses_fmp_quote_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("X_BEARER_TOKEN", raising=False)

    async def fake_serp(tickers):
        return []

    async def fake_quotes(tickers):
        return [
            MarketMover(
                ticker="TSLA",
                price=180.0,
                change_pct=-4.2,
                volume=50_000_000,
                market_cap=600_000_000_000,
                company_name="Tesla, Inc.",
                source_url="https://financialmodelingprep.com/stable/quote?symbol=TSLA",
            )
        ]

    monkeypatch.setattr("app.marketing.signal_layer.scan_x_serp_signals", fake_serp)
    monkeypatch.setattr("app.marketing.signal_layer.fetch_quotes_for_tickers", fake_quotes)

    result = asyncio.run(scan_growth_opportunities(["TSLA"], min_score=70))

    assert len(result) == 1
    assert result[0].ticker == "TSLA"
    assert result[0].source == "fmp"
    assert result[0].intent == INTENT_MARKET_MOVER
    assert result[0].evidence["change_pct"] == -4.2


def test_scan_growth_dedupes_by_ticker_highest_score_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("X_BEARER_TOKEN", raising=False)

    async def fake_serp(tickers):
        return [
            SocialSignal(
                source="tavily",
                query='site:x.com "$NVDA" stock',
                ticker="NVDA",
                title="$NVDA social buzz",
                url="https://x.com/u/status/2",
                snippet="discussion",
                observed_at=datetime.now(timezone.utc),
                estimated_engagement=0,
                intent="ticker_buzz",
            )
        ]

    async def fake_quotes(tickers):
        return [
            MarketMover(
                ticker="NVDA",
                price=120.0,
                change_pct=8.0,
                volume=70_000_000,
                market_cap=2_000_000_000_000,
                company_name="NVIDIA Corporation",
                source_url="https://financialmodelingprep.com/stable/quote?symbol=NVDA",
            )
        ]

    monkeypatch.setattr("app.marketing.signal_layer.scan_x_serp_signals", fake_serp)
    monkeypatch.setattr("app.marketing.signal_layer.fetch_quotes_for_tickers", fake_quotes)

    result = asyncio.run(scan_growth_opportunities(["NVDA"], min_score=70))

    assert len(result) == 1
    assert result[0].ticker == "NVDA"
    assert result[0].source == "fmp"
