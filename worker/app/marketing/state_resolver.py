"""Derive SentinelState from a TickerIntelligenceProfile.

Sprint 1 implementation: heuristic mapping from the existing five heat
scores + catalyst presence. The IntelligenceProfile does not yet expose
explicit confirming / disagreeing signal counts (Sprint 2 will add those
fields); for now we infer them from heat-score band membership.

Critically: the internal 0-100 composite score (overall_opportunity) is
NEVER consulted here. State is derived from the underlying signal mix so
that "anomaly state" is independent of the score we may use for internal
ranking.

Public surface:
  - resolve_state(profile) → SentinelState
  - diagnose(profile)      → StateDiagnosis (rule + signal counts + volume)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .intelligence import TickerIntelligenceProfile
from .state import SentinelState

# Heat threshold for "confirming" — chosen to match the existing
# opportunity_scoring band (>=65 has been "high heat" in production).
HEAT_HIGH = 65
HEAT_LOW = 20
NARRATIVE_GAP_THRESHOLD = 0.3

# All five heat dimensions, in display order
_HEAT_DIMENSIONS = (
    ("market", "market_heat"),
    ("social", "social_heat"),
    ("search", "search_heat"),
    ("news", "news_heat"),
    ("competitor", "competitor_heat"),
)


@dataclass(frozen=True)
class StateDiagnosis:
    """All inputs and the rule that fired, for `--debug-state` UX."""
    state: SentinelState
    confirming_signal_count: int
    confirming_signals: tuple[str, ...]
    disagreeing_signal_count: int
    disagreeing_signals: tuple[str, ...]
    has_filing_catalyst: bool
    narrative_gap: float
    volume_relative: Optional[float]
    rule_fired: str


def resolve_state(profile: TickerIntelligenceProfile) -> SentinelState:
    """Map a profile to one of four public states.

    INFLECTION: filing catalyst + >=3 high-heat signals
    HEATED:    >=3 high-heat signals (without filing)
    WATCHING:  >=1 high-heat signal OR social/search outpacing news
    CALM:      otherwise
    """
    return diagnose(profile).state


def diagnose(profile: TickerIntelligenceProfile) -> StateDiagnosis:
    """Same logic as resolve_state, but returns every input that informed
    the decision. Used by `manual_brief --debug-state`."""
    confirming: list[str] = []
    disagreeing: list[str] = []
    for label, attr in _HEAT_DIMENSIONS:
        heat = getattr(profile, attr)
        if heat >= HEAT_HIGH:
            confirming.append(f"{label} (heat={heat})")
        elif heat <= HEAT_LOW:
            disagreeing.append(f"{label} (heat={heat})")

    has_filing = _has_filing_catalyst(profile)
    narrative_gap = _narrative_filing_gap(profile)
    confirming_count = len(confirming)
    mover = profile.evidence.get("mover", {}) or {}
    volume_relative = mover.get("relative_volume")

    if has_filing and confirming_count >= 3:
        state = SentinelState.INFLECTION
        rule = "INFLECTION: filing catalyst + >=3 confirming signals"
    elif confirming_count >= 3:
        state = SentinelState.HEATED
        rule = "HEATED: >=3 confirming signals (no filing)"
    elif confirming_count >= 1:
        state = SentinelState.WATCHING
        rule = f"WATCHING: {confirming_count} confirming signal(s)"
    elif narrative_gap >= NARRATIVE_GAP_THRESHOLD:
        state = SentinelState.WATCHING
        rule = (
            f"WATCHING: narrative gap {narrative_gap:.2f} "
            f">= threshold {NARRATIVE_GAP_THRESHOLD}"
        )
    else:
        state = SentinelState.CALM
        rule = "CALM: no high-heat signal, no narrative-filing gap"

    return StateDiagnosis(
        state=state,
        confirming_signal_count=confirming_count,
        confirming_signals=tuple(confirming),
        disagreeing_signal_count=len(disagreeing),
        disagreeing_signals=tuple(disagreeing),
        has_filing_catalyst=has_filing,
        narrative_gap=narrative_gap,
        volume_relative=volume_relative,
        rule_fired=rule,
    )


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
