"""Pure-function tests for opportunity_scoring."""

from __future__ import annotations

from app.marketing.opportunity_scoring import (
    ANGLE_AI_SCORE_REVEAL,
    ANGLE_COMPETITOR_COMPARISON,
    ANGLE_EARNINGS_REACTION,
    ANGLE_NEWS_CATALYST,
    ANGLE_RETAIL_MISREAD,
    ANGLE_RISK_FLAG,
    ANGLE_VALUATION_GAP,
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    derive_confidence,
    recommend_angles,
    score_competitor_heat,
    score_filing_recency,
    score_market_cap_relevance,
    score_market_heat,
    score_news_count,
    score_news_heat,
    score_overall_opportunity,
    score_price_move,
    score_relative_volume,
    score_search_heat,
    score_social_heat,
)


# ---- sub-scores -----------------------------------------------------------


def test_price_move_zero_returns_zero() -> None:
    assert score_price_move(0.0) == 0
    assert score_price_move(None) == 0


def test_price_move_monotonic() -> None:
    assert score_price_move(1.0) < score_price_move(3.0)
    assert score_price_move(3.0) < score_price_move(8.0)


def test_price_move_caps_at_100() -> None:
    assert score_price_move(25.0) == 100
    assert score_price_move(-25.0) == 100  # symmetric


def test_relative_volume_safe_with_none() -> None:
    assert score_relative_volume(None) == 0
    assert score_relative_volume(0.0) == 0


def test_relative_volume_grows() -> None:
    assert score_relative_volume(1.0) == 0  # exactly normal
    assert score_relative_volume(2.0) > 0
    assert score_relative_volume(5.0) >= score_relative_volume(2.0)


def test_filing_recency_today_full() -> None:
    assert score_filing_recency(0) == 100
    assert score_filing_recency(30) == 0
    assert score_filing_recency(15) == 50


def test_market_cap_micro_penalty() -> None:
    assert score_market_cap_relevance(100_000_000) < score_market_cap_relevance(5_000_000_000)
    assert score_market_cap_relevance(None) == 50  # neutral default


def test_market_heat_composes_subscores() -> None:
    # Strong movers with recent filing should clear 70
    heat = score_market_heat(
        change_pct=5.5,
        relative_volume=3.0,
        news_count=3,
        days_since_filing=1,
        market_cap=80_000_000_000,
    )
    assert heat >= 70


def test_market_heat_quiet_day_low() -> None:
    heat = score_market_heat(
        change_pct=0.1,
        relative_volume=1.0,
        news_count=0,
        days_since_filing=None,
        market_cap=10_000_000_000,
    )
    assert heat <= 40


# ---- overall -------------------------------------------------------------


def test_overall_weighted_sum() -> None:
    score = score_overall_opportunity(
        market_heat=80,
        social_heat=80,
        search_heat=80,
        news_heat=80,
        competitor_heat=80,
    )
    assert score == 80
    score_low = score_overall_opportunity(
        market_heat=0,
        social_heat=0,
        search_heat=0,
        news_heat=0,
        competitor_heat=0,
    )
    assert score_low == 0


def test_overall_higher_when_market_stronger() -> None:
    a = score_overall_opportunity(market_heat=90, social_heat=30, search_heat=30, news_heat=30, competitor_heat=30)
    b = score_overall_opportunity(market_heat=30, social_heat=30, search_heat=30, news_heat=30, competitor_heat=30)
    assert a > b


# ---- confidence ----------------------------------------------------------


def test_confidence_high_when_multi_source_and_filing() -> None:
    assert derive_confidence(sample_size=8, sources_used=3, has_filing_evidence=True) == CONFIDENCE_HIGH


def test_confidence_low_when_thin_evidence() -> None:
    assert derive_confidence(sample_size=1, sources_used=1, has_filing_evidence=False) == CONFIDENCE_LOW


def test_confidence_medium_in_between() -> None:
    assert derive_confidence(sample_size=4, sources_used=2, has_filing_evidence=False) == CONFIDENCE_MEDIUM


# ---- angle recommendation ------------------------------------------------


def test_recommend_angles_always_returns_at_least_one() -> None:
    angles = recommend_angles(
        market_heat=10, social_heat=10, news_heat=10, competitor_heat=10
    )
    assert len(angles) >= 1


def test_recommend_angles_picks_earnings_when_signal_present() -> None:
    angles = recommend_angles(
        market_heat=70,
        social_heat=40,
        news_heat=50,
        competitor_heat=0,
        has_earnings_signal=True,
    )
    assert ANGLE_EARNINGS_REACTION in angles


def test_recommend_angles_picks_competitor_when_heat_high() -> None:
    angles = recommend_angles(
        market_heat=40, social_heat=40, news_heat=20, competitor_heat=70
    )
    assert ANGLE_COMPETITOR_COMPARISON in angles


def test_recommend_angles_picks_retail_misread() -> None:
    angles = recommend_angles(
        market_heat=20, social_heat=80, news_heat=10, competitor_heat=0
    )
    assert ANGLE_RETAIL_MISREAD in angles


def test_recommend_angles_caps_at_three() -> None:
    angles = recommend_angles(
        market_heat=90,
        social_heat=90,
        news_heat=90,
        competitor_heat=90,
        has_recent_filing=True,
        has_earnings_signal=True,
        has_valuation_concern=True,
    )
    assert len(angles) <= 3


def test_recommend_angles_dedupes() -> None:
    angles = recommend_angles(market_heat=80, social_heat=10, news_heat=10, competitor_heat=10)
    assert len(angles) == len(set(angles))
