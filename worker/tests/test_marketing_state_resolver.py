"""Tests for resolve_state() heuristic mapping."""
from __future__ import annotations

from app.marketing.intelligence import TickerIntelligenceProfile
from app.marketing.state import SentinelState
from app.marketing.state_resolver import resolve_state


def _profile(
    *,
    market_heat: int = 0,
    social_heat: int = 0,
    search_heat: int = 0,
    news_heat: int = 0,
    competitor_heat: int = 0,
    catalysts: tuple[str, ...] = (),
    catalyst_count: int = 0,
) -> TickerIntelligenceProfile:
    """Build a minimal profile for state-resolution tests."""
    return TickerIntelligenceProfile(
        ticker="TEST",
        company_name="Test Co",
        market_heat=market_heat,
        social_heat=social_heat,
        search_heat=search_heat,
        news_heat=news_heat,
        competitor_heat=competitor_heat,
        overall_opportunity=50,  # intentionally NOT consulted by resolver
        why_now="test",
        market_signals=(),
        social_signals=(),
        catalysts=catalysts,
        recommended_angles=(),
        evidence={"catalyst_count": catalyst_count},
        confidence="low",
    )


# ---- CALM ---------------------------------------------------------------


def test_calm_when_all_heats_low_and_no_catalyst() -> None:
    p = _profile(market_heat=20, social_heat=30, search_heat=10)
    assert resolve_state(p) is SentinelState.CALM


def test_calm_even_when_overall_score_high_but_no_underlying_heat() -> None:
    p = _profile(market_heat=10, social_heat=10)
    p_override = TickerIntelligenceProfile(
        ticker=p.ticker,
        company_name=p.company_name,
        market_heat=p.market_heat,
        social_heat=p.social_heat,
        search_heat=p.search_heat,
        news_heat=p.news_heat,
        competitor_heat=p.competitor_heat,
        overall_opportunity=95,  # high composite, low signals
        why_now=p.why_now,
        market_signals=p.market_signals,
        social_signals=p.social_signals,
        catalysts=p.catalysts,
        recommended_angles=p.recommended_angles,
        evidence=p.evidence,
        confidence=p.confidence,
    )
    assert resolve_state(p_override) is SentinelState.CALM


# ---- WATCHING -----------------------------------------------------------


def test_watching_when_single_high_heat() -> None:
    p = _profile(social_heat=80)
    assert resolve_state(p) is SentinelState.WATCHING


def test_watching_when_narrative_outpaces_filings() -> None:
    # social + search high, news low: narrative gap > 0.3
    p = _profile(social_heat=80, search_heat=70, news_heat=10)
    assert resolve_state(p) in {SentinelState.WATCHING, SentinelState.HEATED}


# ---- HEATED -------------------------------------------------------------


def test_heated_when_three_high_heats_no_filing() -> None:
    p = _profile(market_heat=70, social_heat=70, search_heat=70)
    assert resolve_state(p) is SentinelState.HEATED


def test_heated_with_four_heats() -> None:
    p = _profile(market_heat=70, social_heat=70, search_heat=70, news_heat=70)
    # No filing catalyst → stays HEATED, not INFLECTION
    assert resolve_state(p) is SentinelState.HEATED


# ---- INFLECTION ---------------------------------------------------------


def test_inflection_three_heats_plus_filing_via_catalysts() -> None:
    p = _profile(
        market_heat=70,
        social_heat=70,
        news_heat=70,
        catalysts=("8-K · big news (2026-05-10)",),
    )
    assert resolve_state(p) is SentinelState.INFLECTION


def test_inflection_three_heats_plus_filing_via_evidence_count() -> None:
    p = _profile(
        market_heat=70, social_heat=70, news_heat=70, catalyst_count=2
    )
    assert resolve_state(p) is SentinelState.INFLECTION


def test_filing_alone_does_not_trigger_inflection() -> None:
    p = _profile(market_heat=20, catalysts=("8-K · stale",))
    assert resolve_state(p) is SentinelState.CALM


# ---- composite score isolation -----------------------------------------


def test_overall_opportunity_score_is_not_consulted() -> None:
    """resolve_state MUST derive from underlying signals, not the composite."""
    # Make composite low but signals high — should still resolve high
    p = _profile(
        market_heat=80,
        social_heat=80,
        search_heat=80,
        catalysts=("8-K", "10-Q"),
    )
    high_signal_profile = TickerIntelligenceProfile(
        ticker=p.ticker,
        company_name=p.company_name,
        market_heat=p.market_heat,
        social_heat=p.social_heat,
        search_heat=p.search_heat,
        news_heat=p.news_heat,
        competitor_heat=p.competitor_heat,
        overall_opportunity=5,  # absurdly low composite
        why_now=p.why_now,
        market_signals=p.market_signals,
        social_signals=p.social_signals,
        catalysts=p.catalysts,
        recommended_angles=p.recommended_angles,
        evidence=p.evidence,
        confidence=p.confidence,
    )
    assert resolve_state(high_signal_profile) is SentinelState.INFLECTION
