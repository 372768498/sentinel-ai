"""
Unit tests for component → English highlight rendering.
"""
from __future__ import annotations

import pytest

from app.scoring.highlights import (
    component_highlight,
    component_label,
    extract_peer_tickers,
    rank_components,
)


# ── component_label ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("key,expected", [
    ("earnings_surprise", "Earnings surprise"),
    ("fundamentals", "Fundamentals"),
    ("analyst_sentiment", "Analyst consensus"),
    ("historical_patterns", "Earnings track"),
    ("market_context", "Market regime"),
    ("sector_performance", "Sector strength"),
    ("technical", "Technicals"),
    ("sentiment_analysis", "Sentiment"),
    ("peer_comparison", "Peer comp"),
    ("unknown_key", "Unknown Key"),  # fallback titleization
])
def test_component_label_known_and_unknown(key: str, expected: str) -> None:
    assert component_label(key) == expected


# ── component_highlight: per-dimension renderers ──────────────────────────────


def test_highlight_earnings_surprise() -> None:
    assert component_highlight(
        "earnings_surprise", {"surprise_pct": 5.2},
    ) == "EPS surprise +5.2%"


def test_highlight_earnings_surprise_negative() -> None:
    assert component_highlight(
        "earnings_surprise", {"surprise_pct": -3.4},
    ) == "EPS surprise -3.4%"


def test_highlight_earnings_surprise_missing() -> None:
    assert component_highlight("earnings_surprise", {}) is None


def test_highlight_fundamentals_roe_fraction() -> None:
    # 0.27 is the fraction-form ROE that xiangyu sometimes emits
    out = component_highlight("fundamentals", {"roe": 0.27, "free_cashflow": 19e9})
    assert out is not None
    assert "ROE 27%" in out
    assert "FCF $19.0B" in out


def test_highlight_fundamentals_roe_already_percent() -> None:
    out = component_highlight("fundamentals", {"roe": 27})
    assert out == "ROE 27%"


def test_highlight_analyst_sentiment_full() -> None:
    out = component_highlight(
        "analyst_sentiment",
        {"consensus_rating": "Strong Buy", "upside_pct": 14.2},
    )
    assert out == "Strong Buy · +14% upside"


def test_highlight_analyst_sentiment_partial() -> None:
    out = component_highlight(
        "analyst_sentiment", {"consensus_rating": "Hold"},
    )
    assert out == "Hold"


def test_highlight_historical_patterns_beats() -> None:
    out = component_highlight(
        "historical_patterns", {"beats_last_4q": 3, "total_quarters": 4},
    )
    assert out == "3/4 earnings beats"


def test_highlight_market_context_vix() -> None:
    out = component_highlight(
        "market_context", {"vix_level": 18.3, "vix_status": "Normal"},
    )
    assert out == "VIX 18.3 (Normal)"


def test_highlight_sector_performance_relative() -> None:
    # stock_return_1m=0.08, sector_return_1m=0.05 → relative +3.0%
    out = component_highlight(
        "sector_performance",
        {"stock_return_1m": 0.08, "sector_return_1m": 0.05},
    )
    assert out == "+3.0% vs sector (1m)"


def test_highlight_technical_trend_rsi() -> None:
    out = component_highlight(
        "technical", {"trend": "Bullish", "rsi_14d": 62.4},
    )
    assert out == "Bullish · RSI 62"


def test_highlight_sentiment_fear_greed() -> None:
    out = component_highlight(
        "sentiment_analysis",
        {"fear_greed_value": 52, "fear_greed_status": "Neutral"},
    )
    assert out == "Fear&amp;Greed 52 (Neutral)"


def test_highlight_peer_comparison_premium() -> None:
    out = component_highlight(
        "peer_comparison",
        {
            "peer_tickers": ["AMD", "INTC"],
            "comparisons": {"pe": {"premium_pct": 44.0}},
        },
    )
    assert out == "P/E 44% premium vs peers"


def test_highlight_peer_comparison_discount() -> None:
    out = component_highlight(
        "peer_comparison",
        {
            "peer_tickers": ["AMD", "INTC"],
            "comparisons": {"pe": {"premium_pct": -43.8}},
        },
    )
    assert out == "P/E 44% discount vs peers"


def test_highlight_returns_none_for_non_dict() -> None:
    assert component_highlight("technical", "not a dict") is None
    assert component_highlight("technical", None) is None


def test_highlight_returns_none_for_unknown_dimension() -> None:
    assert component_highlight("unknown_dim", {"score": 0.5}) is None


# ── rank_components ───────────────────────────────────────────────────────────


def test_rank_components_strongest_and_weakest_disjoint() -> None:
    components = {
        "a": {"score": 1.0},
        "b": {"score": 0.8},
        "c": {"score": 0.6},
        "d": {"score": 0.4},
        "e": {"score": 0.2},
        "f": {"score": -0.1},
    }
    strongest, weakest = rank_components(components, top_n=3)
    assert [k for k, _ in strongest] == ["a", "b", "c"]
    assert [k for k, _ in weakest] == ["f", "e", "d"]
    # Disjoint
    assert {k for k, _ in strongest}.isdisjoint({k for k, _ in weakest})


def test_rank_components_skips_missing_score() -> None:
    components = {
        "a": {"score": 0.8},
        "b": {"no_score_key": "x"},
        "c": "not even a dict",
        "d": {"score": 0.2},
    }
    strongest, _ = rank_components(components, top_n=3)
    keys = [k for k, _ in strongest]
    assert "b" not in keys
    assert "c" not in keys


# ── extract_peer_tickers ──────────────────────────────────────────────────────


def test_extract_peer_tickers_present() -> None:
    components = {
        "peer_comparison": {"peer_tickers": ["AMD", "INTC", "AVGO"]},
    }
    assert extract_peer_tickers(components) == ["AMD", "INTC", "AVGO"]


def test_extract_peer_tickers_absent() -> None:
    assert extract_peer_tickers({}) == []
    assert extract_peer_tickers({"peer_comparison": None}) == []
    assert extract_peer_tickers({"peer_comparison": {}}) == []
