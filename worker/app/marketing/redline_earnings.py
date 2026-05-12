"""Pre-earnings window redline — directional-language guard.

Within 7 calendar days BEFORE scheduled earnings and 2 days AFTER,
certain phrases are auto-rejected regardless of which model produced
them. Two reasons:

1. SEC may interpret pre-earnings directional language as an implied
   recommendation (vs Sentinel's "anomaly detection" positioning).
2. The post-earnings 2-day window catches retroactive "see, we told you"
   wording that would equally read as a recommendation.

Outside the window, this check is a no-op — generic redline still runs.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional


BLOCKED_PHRASES_PRE_EARNINGS: tuple[str, ...] = (
    # directional implications
    "consider buying",
    "consider selling",
    "good entry",
    "good exit",
    "good time to",
    "buying opportunity",
    "selling opportunity",
    "set up for a beat",
    "set up for a miss",
    "expecting a strong quarter",
    "expecting weak results",
    # implied recommendations dressed as analysis
    "score rising into earnings",
    "score falling into earnings",
    "bullish heading into earnings",
    "bearish heading into earnings",
    "sentinel favors",
    "sentinel prefers",
    # false-precision confidence words
    "high conviction",
    "low conviction",
    "should outperform",
    "should underperform",
)

WINDOW_DAYS_BEFORE = 7
WINDOW_DAYS_AFTER = 2


@dataclass(frozen=True)
class EarningsWindowResult:
    ok: bool
    in_window: bool
    days_to_earnings: Optional[int]
    blocked_phrase: Optional[str]

    def reason(self) -> str:
        if self.ok:
            return "ok"
        return (
            f"earnings_window:{self.blocked_phrase} "
            f"(d={self.days_to_earnings})"
        )


def check_earnings_window(
    *,
    text: str,
    earnings_date: Optional[date],
    today: Optional[date] = None,
) -> EarningsWindowResult:
    """Returns an EarningsWindowResult.

    `today` is injectable for deterministic tests.

    `earnings_date is None` → outside window, always ok (no calendar data).
    """
    if earnings_date is None:
        return EarningsWindowResult(
            ok=True,
            in_window=False,
            days_to_earnings=None,
            blocked_phrase=None,
        )

    ref = today or date.today()
    days_to = (earnings_date - ref).days
    in_window = -WINDOW_DAYS_AFTER <= days_to <= WINDOW_DAYS_BEFORE
    if not in_window:
        return EarningsWindowResult(
            ok=True,
            in_window=False,
            days_to_earnings=days_to,
            blocked_phrase=None,
        )

    text_lower = text.lower()
    for phrase in BLOCKED_PHRASES_PRE_EARNINGS:
        if phrase in text_lower:
            return EarningsWindowResult(
                ok=False,
                in_window=True,
                days_to_earnings=days_to,
                blocked_phrase=phrase,
            )

    return EarningsWindowResult(
        ok=True,
        in_window=True,
        days_to_earnings=days_to,
        blocked_phrase=None,
    )
