"""Tests for the X SERP adapter — query builder + intent classifier + creds gating."""

from __future__ import annotations

import asyncio

import pytest

from app.marketing.data_sources import x_serp


def _run(coro):
    return asyncio.run(coro)


def test_build_x_queries_includes_ticker_and_competitor_terms() -> None:
    queries = x_serp.build_x_queries(["NVDA", "TSLA"])
    flat = "\n".join(queries)
    assert '"$NVDA" stock' in flat
    assert '"$TSLA" earnings' in flat
    assert '"$NVDA" risk' in flat
    assert "TipRanks alternative" in flat
    assert "Simply Wall St alternative" in flat
    assert "AI stock analysis" in flat


def test_build_x_queries_per_ticker_count() -> None:
    queries = x_serp.build_x_queries(["NVDA"])
    # 4 per-ticker + 3 competitor globals
    assert len(queries) == 7


def test_classify_intent_competitor() -> None:
    assert (
        x_serp._classify_intent("Looking for a TipRanks alternative")
        == x_serp.INTENT_COMPETITOR_ALTERNATIVE
    )


def test_classify_intent_high_intent_question() -> None:
    assert (
        x_serp._classify_intent("Is $NVDA overvalued at this multiple?")
        == x_serp.INTENT_HIGH_INTENT_QUESTION
    )


def test_classify_intent_risk_discussion() -> None:
    assert (
        x_serp._classify_intent("There's a real concern that $TSLA will miss")
        == x_serp.INTENT_RISK_DISCUSSION
    )


def test_classify_intent_fallback_to_buzz() -> None:
    assert x_serp._classify_intent("$NVDA up nicely today") == x_serp.INTENT_TICKER_BUZZ


def test_scan_returns_empty_when_no_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("DATAFORSEO_LOGIN", "DATAFORSEO_PASSWORD", "TAVILY_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    assert _run(x_serp.scan_x_serp_signals(["NVDA"])) == []


def test_scan_empty_ticker_list_returns_empty() -> None:
    assert _run(x_serp.scan_x_serp_signals([])) == []


def test_scan_uses_dataforseo_when_credentials_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATAFORSEO_LOGIN", "user")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "pw")
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    async def fake_dataforseo(query: str):
        if '"$NVDA"' in query:
            return [
                {
                    "title": "$NVDA hits new high",
                    "url": "https://x.com/user/status/1",
                    "snippet": "buzz",
                },
            ]
        return []

    async def fake_tavily(query: str):
        raise AssertionError("Tavily should not be called when DataForSEO is configured")

    monkeypatch.setattr(x_serp, "_query_dataforseo", fake_dataforseo)
    monkeypatch.setattr(x_serp, "_query_tavily", fake_tavily)

    signals = _run(x_serp.scan_x_serp_signals(["NVDA"], queries_per_run=4))
    assert len(signals) >= 1
    assert all(s.source == "dataforseo" for s in signals)
    assert all(s.url.startswith("https://x.com") for s in signals)


def test_scan_falls_back_to_tavily(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATAFORSEO_LOGIN", raising=False)
    monkeypatch.delenv("DATAFORSEO_PASSWORD", raising=False)
    monkeypatch.setenv("TAVILY_API_KEY", "fake")

    async def fake_tavily(query: str):
        return [
            {
                "title": "$NVDA risk discussion",
                "url": "https://x.com/u/status/77",
                "snippet": "risk and overvalued",
            }
        ]

    async def fake_dataforseo(query: str):
        raise AssertionError("DataForSEO should not be called when creds missing")

    monkeypatch.setattr(x_serp, "_query_tavily", fake_tavily)
    monkeypatch.setattr(x_serp, "_query_dataforseo", fake_dataforseo)

    signals = _run(x_serp.scan_x_serp_signals(["NVDA"], queries_per_run=2))
    assert len(signals) >= 1
    assert all(s.source == "tavily" for s in signals)
    # Intent classification should label "risk" content correctly
    assert any(s.intent == x_serp.INTENT_RISK_DISCUSSION for s in signals)


def test_scan_dedupes_by_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATAFORSEO_LOGIN", "u")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "p")

    async def fake_dataforseo(query: str):
        return [
            {"title": "dup", "url": "https://x.com/dup/1", "snippet": ""},
        ]

    monkeypatch.setattr(x_serp, "_query_dataforseo", fake_dataforseo)

    signals = _run(x_serp.scan_x_serp_signals(["NVDA"], queries_per_run=4))
    urls = [s.url for s in signals]
    assert len(urls) == len(set(urls))
