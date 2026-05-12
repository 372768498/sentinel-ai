"""Derive SentinelState from a TickerIntelligenceProfile.

Sprint 1 implementation: heuristic mapping from the existing five heat
scores + catalyst presence. The IntelligenceProfile does not yet expose
explicit confirming / disagreeing signal counts (Sprint 2 will add those
fields); for now we infer them from heat-score band membership.

Critically: the internal 0-100 composite score (overall_opportunity) is
NEVER consulted here. State is derived from the underlying signal mix so
that "anomaly state" is independent of the score we may use for internal
ranking.
"""
from __future__ import annotations

from .intelligence import TickerIntelligenceProfile
from .state import SentinelState

# Heat threshold for "confirming" — chosen to match the existing
# opportunity_scoring band (>=65 has been "high heat" in production).
HEAT_HIGH = 65
NARRATIVE_GAP_THRESHOLD = 0.3


def resolve_state(profile: TickerIntelligenceProfile) -> SentinelState:
    """Map a profile to one of four public states.

    INFLECTION: filing catalyst + >=3 high-heat signals
    HEATED:    >=3 high-heat signals (without filing)
    WATCHING:  >=1 high-heat signal OR social/search outpacing news
    CALM:      otherwise
    """
    confirming = _count_confirming(profile)
    has_filing = _has_filing_catalyst(profile)
    narrative_gap = _narrative_filing_gap(profile)

    if has_filing and confirming >= 3:
        return SentinelState.INFLECTION

    if confirming >= 3:
        return SentinelState.HEATED

    if confirming >= 1 or narrative_gap >= NARRATIVE_GAP_THRESHOLD:
        return SentinelState.WATCHING

    return SentinelState.CALM


def _count_confirming(profile: TickerIntelligenceProfile) -> int:
    return sum(
        1
        for heat in (
            profile.market_heat,
            profile.social_heat,
            profile.search_heat,
            profile.news_heat,
            profile.competitor_heat,
        )
        if heat >= HEAT_HIGH
    )


def _has_filing_catalyst(profile: TickerIntelligenceProfile) -> bool:
    return bool(profile.catalysts) or bool(
        profile.evidence.get("catalyst_count", 0)
    )


def _narrative_filing_gap(profile: TickerIntelligenceProfile) -> float:
    """Positive when social/search heat exceeds news heat — narrative
    running ahead of filings. Normalized to [0, 1]."""
    narrative = (profile.social_heat + profile.search_heat) / 2.0
    gap = (narrative - profile.news_heat) / 100.0
    return max(0.0, gap)
