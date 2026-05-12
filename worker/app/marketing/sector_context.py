"""Sector context — replaces peer comparison with anomaly uniqueness.

Spec deliberately avoids naming individual peer tickers ('AMD vs NVDA
vs AVGO') in user-facing output. Instead, the question is:
'Is this ticker's anomaly unique to it, or shared across the sector?'

Three interpretation bands emitted verbatim to templates:
  - >=0.8 uniqueness  → "unique signal, likely company-specific catalyst"
  - 0.5-0.8           → "mixed — could be sector rotation or specific"
  - <0.5              → "sector-wide pattern, looks like rotation"
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .state import SentinelState


@dataclass(frozen=True)
class SectorContext:
    ticker: str
    peers_in_same_state: int
    peer_universe_size: int
    uniqueness_score: float  # 0.0 - 1.0
    interpretation: str

    @property
    def is_unique_signal(self) -> bool:
        return self.uniqueness_score >= 0.8

    @property
    def is_mixed(self) -> bool:
        return 0.5 <= self.uniqueness_score < 0.8

    @property
    def is_sector_wide(self) -> bool:
        return self.uniqueness_score < 0.5


UNIQUENESS_HIGH = 0.8
UNIQUENESS_MIXED = 0.5


def compute_sector_context(
    *,
    ticker: str,
    ticker_state: SentinelState,
    peer_states: Iterable[SentinelState],
) -> SectorContext:
    """Compute sector context from a precomputed list of peer states.

    Caller is responsible for the peer lookup (sector membership + each
    peer's current state). This keeps the function pure and testable.

    `peer_states` should NOT include the target ticker itself.
    """
    peers = list(peer_states)
    universe = len(peers)
    if universe == 0:
        # No peer data — degrade to 'mixed' interpretation with score=0.5
        return SectorContext(
            ticker=ticker.upper(),
            peers_in_same_state=0,
            peer_universe_size=0,
            uniqueness_score=0.5,
            interpretation=(
                f"${ticker.upper()} sector context unavailable — "
                "peer data missing. Treat as mixed signal."
            ),
        )

    same_state = sum(1 for s in peers if s == ticker_state)
    uniqueness = 1.0 - (same_state / universe)

    if uniqueness >= UNIQUENESS_HIGH:
        interp = (
            f"${ticker.upper()}'s signal is unique. "
            f"Only {same_state} of {universe} sector peers show the "
            f"same pattern. This suggests a company-specific catalyst, "
            f"not a sector rotation."
        )
    elif uniqueness >= UNIQUENESS_MIXED:
        interp = (
            f"${ticker.upper()} is moving with about half its sector. "
            f"Mixed signal — could be sector-driven or company-specific."
        )
    else:
        interp = (
            f"${ticker.upper()}'s pattern is shared across the sector. "
            f"This looks like sector rotation, not company-specific news."
        )

    return SectorContext(
        ticker=ticker.upper(),
        peers_in_same_state=same_state,
        peer_universe_size=universe,
        uniqueness_score=uniqueness,
        interpretation=interp,
    )
