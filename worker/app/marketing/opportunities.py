"""Opportunity model — the standardized signal shape that flows from any
discovery adapter (X, Reddit, YouTube, OpenClaw…) into the Content Factory.

Adapters are responsible for shaping their raw output into `Opportunity`.
The Content Factory consumes ONLY this shape — keeps the core decoupled
from any one platform's data model.

Score range conventions:
  - opportunity_score  : 0-100, higher = more worth creating content for
  - compliance_risk    : 0-100, higher = more likely to need extra scrutiny
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

INTENT_TICKER_BUZZ = "ticker_buzz"
INTENT_HIGH_INTENT_QUESTION = "high_intent_question"
INTENT_COMPETITOR_ALTERNATIVE = "competitor_alternative"
INTENT_MARKET_MOVER = "market_mover"

ACTION_CREATE_CONTENT = "create_content"
ACTION_WATCH = "watch"
ACTION_IGNORE = "ignore"

SUGGESTED_ACTIONS = (ACTION_CREATE_CONTENT, ACTION_WATCH, ACTION_IGNORE)


@dataclass(frozen=True)
class Opportunity:
    opportunity_id: str
    source: str  # x / fmp / reddit / youtube / manual
    ticker: str
    intent: str
    raw_text: str
    url: str | None
    author_id: str | None
    opportunity_score: int
    compliance_risk: int
    suggested_action: str
    evidence: dict[str, Any] = field(default_factory=dict)


def derive_action(score: int) -> str:
    if score >= 70:
        return ACTION_CREATE_CONTENT
    if score >= 30:
        return ACTION_WATCH
    return ACTION_IGNORE


def rank_opportunities(items: list[Opportunity]) -> list[Opportunity]:
    """Sort descending by opportunity_score, tiebreak by ticker for determinism."""
    return sorted(items, key=lambda o: (-o.opportunity_score, o.ticker))
