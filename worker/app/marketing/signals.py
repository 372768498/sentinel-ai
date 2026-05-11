"""Score heuristic for marketing gate.

Until per-ticker AnalysisHistory.finalScore lookup is wired, derive a 0-100
score from absolute price move. The curve is intentionally conservative:
daily 1-2% moves stay below the daily-push gate, while 5%+ moves qualify
without making 99+ scores common enough to dilute the emergency tier.
"""
from __future__ import annotations

from typing import Protocol

_SCORE_POINTS: tuple[tuple[float, int], ...] = (
    (0.0, 0),
    (1.0, 50),
    (2.0, 62),
    (3.0, 72),
    (5.0, 82),
    (8.0, 92),
    (12.0, 98),
    (20.0, 100),
)


class _MoveLike(Protocol):
    change_pct: float
    ticker: str


def score_from_move(move: _MoveLike) -> int:
    abs_pct = abs(move.change_pct)
    if abs_pct <= 0:
        return 0

    previous_pct, previous_score = _SCORE_POINTS[0]
    for current_pct, current_score in _SCORE_POINTS[1:]:
        if abs_pct <= current_pct:
            span = current_pct - previous_pct
            ratio = (abs_pct - previous_pct) / span
            raw = previous_score + ratio * (current_score - previous_score)
            return max(0, min(100, round(raw)))
        previous_pct, previous_score = current_pct, current_score

    return 100


def passes_gate(score: int, *, threshold: int = 80) -> bool:
    return score >= threshold
