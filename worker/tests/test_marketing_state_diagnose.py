"""Tests for state_resolver.diagnose() — the --debug-state public API."""
from __future__ import annotations

import pytest

from app.marketing.intelligence import TickerIntelligenceProfile
from app.marketing.state import SentinelState
from app.marketing.state_resolver import diagnose, resolve_state


def _profile(
    *,
    market: int = 0,
    social: int = 0,
    search: int = 0,
    news: int = 0,
    competitor: int = 0,
    catalysts: tuple[str, ...] = (),
    catalyst_count: int = 0,
    relative_volume: float | None = None,
) -> TickerIntelligenceProfile:
    evidence: dict = {"catalyst_count": catalyst_count}
    if relative_volume is not None:
        evidence["mover"] = {"relative_volume": relative_volume}
    return TickerIntelligenceProfile(
        ticker="TEST",
        company_name="Test Co",
        market_heat=market,
        social_heat=social,
        search_heat=search,
        news_heat=news,
        competitor_heat=competitor,
        overall_opportunity=50,
        why_now="x",
        market_signals=(),
        social_signals=(),
        catalysts=catalysts,
        recommended_angles=(),
        evidence=evidence,
        confidence="low",
    )


def test_diagnose_calm_no_signals() -> None:
    d = diagnose(_profile())
    assert d.state is SentinelState.CALM
    assert d.confirming_signal_count == 0
    assert d.disagreeing_signal_count == 5  # all heats == 0, all <=20
    assert d.has_filing_catalyst is False
    assert d.rule_fired.startswith("CALM")


def test_diagnose_watching_single_heat() -> None:
    d = diagnose(_profile(social=80))
    assert d.state is SentinelState.WATCHING
    assert d.confirming_signal_count == 1
    assert "social (heat=80)" in d.confirming_signals[0]
    assert d.rule_fired.startswith("WATCHING")


def test_diagnose_heated_three_signals_no_filing() -> None:
    d = diagnose(_profile(market=70, social=70, search=70))
    assert d.state is SentinelState.HEATED
    assert d.confirming_signal_count == 3
    assert "HEATED" in d.rule_fired


def test_diagnose_inflection_three_signals_plus_catalyst() -> None:
    d = diagnose(_profile(market=70, social=70, news=70, catalyst_count=1))
    assert d.state is SentinelState.INFLECTION
    assert d.has_filing_catalyst is True
    assert "INFLECTION" in d.rule_fired


def test_diagnose_volume_relative_from_evidence() -> None:
    d = diagnose(_profile(relative_volume=2.5))
    assert d.volume_relative == 2.5


def test_diagnose_volume_relative_none_when_missing() -> None:
    d = diagnose(_profile())
    assert d.volume_relative is None


def test_diagnose_disagreeing_signals_include_label_and_heat() -> None:
    d = diagnose(_profile(market=80, competitor=10))
    # competitor (10) is below HEAT_LOW so it appears in disagreeing
    assert any("competitor" in s and "heat=10" in s for s in d.disagreeing_signals)
    # market (80) is in confirming
    assert any("market" in s for s in d.confirming_signals)


def test_diagnose_rule_text_includes_narrative_gap_when_relevant() -> None:
    # high social + search, low news → narrative gap > 0.3, no confirming high
    d = diagnose(_profile(social=64, search=64, news=10))
    # social=64 just below HEAT_HIGH=65 → 0 confirming, so narrative gap fires
    assert d.state is SentinelState.WATCHING
    assert d.confirming_signal_count == 0
    assert "narrative gap" in d.rule_fired


def test_resolve_state_matches_diagnose_state() -> None:
    """resolve_state must always agree with diagnose(p).state."""
    cases = [
        _profile(),
        _profile(social=80),
        _profile(market=70, social=70, search=70),
        _profile(market=70, social=70, news=70, catalyst_count=1),
    ]
    for p in cases:
        assert resolve_state(p) is diagnose(p).state
