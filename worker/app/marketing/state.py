"""SentinelState — public-facing 4-state classification.

Replaces the internal 0-100 `overall_opportunity` score in all user-visible
outputs. The score stays in TickerIntelligenceProfile for internal ranking
and backtesting; it MUST NOT leak to any user-facing template.

Ordering matters: STATE_RANK is consulted by the notification dispatcher
to decide whether an alert clears the per-user push threshold.
"""
from __future__ import annotations

from enum import Enum


class SentinelState(str, Enum):
    CALM = "calm"
    WATCHING = "watching"
    HEATED = "heated"
    INFLECTION = "inflection"


STATE_DISPLAY: dict[SentinelState, dict[str, str]] = {
    SentinelState.CALM: {
        "emoji": "🔵",
        "label": "Calm",
        "one_liner": "no anomaly detected",
        "color_hex": "#4A90E2",
    },
    SentinelState.WATCHING: {
        "emoji": "🟡",
        "label": "Watching",
        "one_liner": "narrative running ahead of filings",
        "color_hex": "#F5A623",
    },
    SentinelState.HEATED: {
        "emoji": "🟠",
        "label": "Heated",
        "one_liner": "multi-dimension signals firing",
        "color_hex": "#FF6B35",
    },
    SentinelState.INFLECTION: {
        "emoji": "🔴",
        "label": "Inflection",
        "one_liner": "confirmed catalyst + volume + filing",
        "color_hex": "#D0021B",
    },
}


STATE_RANK: dict[SentinelState, int] = {
    SentinelState.CALM: 0,
    SentinelState.WATCHING: 1,
    SentinelState.HEATED: 2,
    SentinelState.INFLECTION: 3,
}


def is_at_least(state: SentinelState, min_state: SentinelState) -> bool:
    """True when `state` is at or above `min_state` in severity."""
    return STATE_RANK[state] >= STATE_RANK[min_state]
