"""Heat-scoring primitives for Sentinel AI Market Intelligence Layer.

All score functions return integers in 0-100. Pure: no I/O, no network.
Designed so the Content Factory always has explainable inputs:

  market_heat     = price move + relative volume + news count + filing recency
  social_heat     = X SERP signal volume + intent weighting
  search_heat     = SERP slot count + organic ranking spread (placeholder weights)
  news_heat       = curated news article density
  competitor_heat = mentions of competitor terms (TipRanks / Simply Wall St / etc.)

  overall_opportunity = weighted sum of the five sub-heats

Angle taxonomy (Week 6 baseline):
  risk_flag · earnings_reaction · valuation_gap · competitor_comparison
  retail_misread · ai_score_reveal · news_catalyst
"""

from __future__ import annotations

import math
from typing import Iterable

ANGLE_RISK_FLAG = "risk_flag"
ANGLE_EARNINGS_REACTION = "earnings_reaction"
ANGLE_VALUATION_GAP = "valuation_gap"
ANGLE_COMPETITOR_COMPARISON = "competitor_comparison"
ANGLE_RETAIL_MISREAD = "retail_misread"
ANGLE_AI_SCORE_REVEAL = "ai_score_reveal"
ANGLE_NEWS_CATALYST = "news_catalyst"

ANGLE_TAXONOMY: tuple[str, ...] = (
    ANGLE_RISK_FLAG,
    ANGLE_EARNINGS_REACTION,
    ANGLE_VALUATION_GAP,
    ANGLE_COMPETITOR_COMPARISON,
    ANGLE_RETAIL_MISREAD,
    ANGLE_AI_SCORE_REVEAL,
    ANGLE_NEWS_CATALYST,
)

CONFIDENCE_LOW = "low"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_HIGH = "high"


def _clip(score: float) -> int:
    return max(0, min(100, round(score)))


# ---------------------------------------------------------------------------
# Sub-scores (each piece returns 0-100)
# ---------------------------------------------------------------------------


def score_price_move(change_pct: float | None) -> int:
    """abs(change_pct) → 0-100. Piecewise-linear matching signals.score_from_move()."""
    if change_pct is None:
        return 0
    p = abs(change_pct)
    if p <= 0:
        return 0
    if p <= 1.0:
        return _clip(p * 50)
    if p <= 2.0:
        return _clip(50 + (p - 1.0) * 12)
    if p <= 3.0:
        return _clip(62 + (p - 2.0) * 10)
    if p <= 5.0:
        return _clip(72 + (p - 3.0) * 5)
    if p <= 8.0:
        return _clip(82 + (p - 5.0) * 3.3)
    if p <= 12.0:
        return _clip(92 + (p - 8.0) * 1.5)
    return 100


def score_relative_volume(rel_volume: float | None) -> int:
    """rel_volume = today_vol / avg_30d_vol. 1.0 = normal. 2.0 = double. Logarithmic."""
    if rel_volume is None or rel_volume <= 0:
        return 0
    # Caps at 5x volume → 100
    return _clip(math.log1p(max(0.0, rel_volume - 1.0)) / math.log(5.0) * 100)


def score_news_count(count: int) -> int:
    """0 articles → 0, 5+ articles → 100. Linear."""
    return _clip(min(count, 5) * 20)


def score_filing_recency(days_since_filing: int | None) -> int:
    """Same-day filing → 100, 30+ days → 0. Linear."""
    if days_since_filing is None or days_since_filing < 0:
        return 0
    if days_since_filing >= 30:
        return 0
    return _clip(100 - (days_since_filing / 30.0) * 100)


def score_market_cap_relevance(market_cap: int | None) -> int:
    """Mid+ cap retail-relevant. Penalize sub-$500M micro-caps (often pump targets)."""
    if market_cap is None:
        return 50
    if market_cap < 500_000_000:
        return 30
    if market_cap < 2_000_000_000:
        return 60
    if market_cap < 10_000_000_000:
        return 80
    return 100


def score_market_heat(
    *,
    change_pct: float | None,
    relative_volume: float | None,
    news_count: int = 0,
    days_since_filing: int | None = None,
    market_cap: int | None = None,
) -> int:
    return _clip(
        score_price_move(change_pct) * 0.30
        + score_relative_volume(relative_volume) * 0.25
        + score_news_count(news_count) * 0.20
        + score_filing_recency(days_since_filing) * 0.15
        + score_market_cap_relevance(market_cap) * 0.10
    )


def score_social_heat(
    signal_count: int, *, high_intent_count: int = 0, competitor_mentions: int = 0
) -> int:
    """Each SERP-derived X mention worth ~5 pts up to 50, high-intent doubled."""
    base = min(signal_count * 5, 50)
    intent_bonus = min(high_intent_count * 10, 30)
    competitor_bonus = min(competitor_mentions * 5, 20)
    return _clip(base + intent_bonus + competitor_bonus)


def score_search_heat(serp_results_count: int, *, ranking_spread: int = 1) -> int:
    """More SERP hits + diverse ranking domains → more search heat."""
    base = min(serp_results_count * 4, 70)
    spread = min(ranking_spread * 5, 30)
    return _clip(base + spread)


def score_news_heat(news_count: int, *, high_priority_count: int = 0) -> int:
    """News count weighted by curation priority (e.g. SEC 8-K = high priority)."""
    return _clip(min(news_count * 8, 60) + min(high_priority_count * 20, 40))


def score_competitor_heat(competitor_mentions: int) -> int:
    """Detected mentions of TipRanks / Simply Wall St / Seeking Alpha / etc."""
    return _clip(min(competitor_mentions * 15, 100))


def score_overall_opportunity(
    *,
    market_heat: int,
    social_heat: int,
    search_heat: int,
    news_heat: int,
    competitor_heat: int,
) -> int:
    return _clip(
        market_heat * 0.35
        + social_heat * 0.25
        + search_heat * 0.15
        + news_heat * 0.15
        + competitor_heat * 0.10
    )


def derive_confidence(
    *,
    sample_size: int,
    sources_used: int,
    has_filing_evidence: bool,
) -> str:
    """Translate evidence strength into a low/medium/high label."""
    if sources_used >= 3 and sample_size >= 5 and has_filing_evidence:
        return CONFIDENCE_HIGH
    if sources_used >= 2 and sample_size >= 3:
        return CONFIDENCE_MEDIUM
    return CONFIDENCE_LOW


# ---------------------------------------------------------------------------
# Angle recommendation
# ---------------------------------------------------------------------------


def recommend_angles(
    *,
    market_heat: int,
    social_heat: int,
    news_heat: int,
    competitor_heat: int,
    has_recent_filing: bool = False,
    has_earnings_signal: bool = False,
    has_valuation_concern: bool = False,
) -> tuple[str, ...]:
    """Pick 1-3 angles based on which signals dominate.

    Caller decides which angle to pursue. Returned in priority order, deduped.
    """
    angles: list[str] = []

    if has_earnings_signal and market_heat >= 60:
        angles.append(ANGLE_EARNINGS_REACTION)
    if has_recent_filing and news_heat >= 40:
        angles.append(ANGLE_NEWS_CATALYST)
    if competitor_heat >= 50:
        angles.append(ANGLE_COMPETITOR_COMPARISON)
    if has_valuation_concern:
        angles.append(ANGLE_VALUATION_GAP)
    if social_heat >= 70 and market_heat < 50:
        angles.append(ANGLE_RETAIL_MISREAD)
    if market_heat >= 50:
        angles.append(ANGLE_RISK_FLAG)

    # AI score reveal is the always-on fallback — Sentinel's signature angle
    if not angles or len(angles) < 2:
        angles.append(ANGLE_AI_SCORE_REVEAL)

    # Dedupe preserving order, cap at 3
    seen: set[str] = set()
    result: list[str] = []
    for angle in angles:
        if angle in seen:
            continue
        seen.add(angle)
        result.append(angle)
        if len(result) >= 3:
            break
    return tuple(result)
