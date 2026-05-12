"""Honest miss detector — what Sentinel SHOULD have flagged but didn't.

A 'miss' is a ticker that:
  - Moved >=7% in a single day within the lookback window
  - Had supporting catalyst (SEC filing, news, or volume spike)
  - Was NOT flagged by Sentinel in the 24h before the move

Output feeds:
  - Monthly Telegram 'Honest log' post
  - Pro weekly digest 'misses' section
  - Model improvement loop (manual review)

Sprint 4 status: the detection LOGIC lives here as a pure function.
The DB integration (alert-history lookup, price-history lookup) is left
as caller responsibility — the function takes pre-fetched data so it
can be unit-tested without touching FMP / Postgres.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional


BIG_MOVE_THRESHOLD_PCT = 7.0
LOOKBACK_DAYS_DEFAULT = 7
FLAG_WINDOW_HOURS = 24


@dataclass(frozen=True)
class DailyMoveRecord:
    """One ticker's single-day price snapshot (for miss-detection)."""
    ticker: str
    date: date
    price_change_pct: float
    had_catalyst: bool         # any 8-K/10-Q/10-K filing OR major news
    volume_relative: float     # 1.0 = avg


@dataclass(frozen=True)
class FlagHistoryRow:
    ticker: str
    flagged_at: date           # date we sent any alert for this ticker
    state_at_flag: str         # state name, lower-case


@dataclass(frozen=True)
class Miss:
    ticker: str
    move_date: date
    move_pct: float
    catalyst_type: str         # 'filing' | 'volume_spike' | 'mixed'
    why_we_missed: str


def _classify_catalyst(move: DailyMoveRecord) -> Optional[str]:
    """Returns the dominant catalyst label, or None if not enough signal."""
    if move.had_catalyst and move.volume_relative >= 1.5:
        return "mixed"
    if move.had_catalyst:
        return "filing"
    if move.volume_relative >= 2.0:
        return "volume_spike"
    return None


def _was_flagged_within_window(
    move: DailyMoveRecord,
    flag_history: Iterable[FlagHistoryRow],
    *,
    window_days: int = 1,
) -> bool:
    """True if any flag for this ticker fired within `window_days` BEFORE
    the move date (inclusive). Implementation accepts a generic iterable
    so the caller can pre-filter to one ticker if desired."""
    for row in flag_history:
        if row.ticker.upper() != move.ticker.upper():
            continue
        days_before = (move.date - row.flagged_at).days
        if 0 <= days_before <= window_days:
            return True
    return False


def detect_misses(
    *,
    moves: Iterable[DailyMoveRecord],
    flag_history: Iterable[FlagHistoryRow],
    threshold_pct: float = BIG_MOVE_THRESHOLD_PCT,
    window_days: int = 1,
) -> list[Miss]:
    """Pure miss-detection over pre-fetched data.

    Caller responsibilities:
      - Provide `moves` covering the lookback period (one row per
        ticker-day big enough to potentially qualify).
      - Provide `flag_history` for the same period plus the day before
        (so we can detect 24h pre-move flags).
    """
    flags = list(flag_history)
    out: list[Miss] = []
    for move in moves:
        if abs(move.price_change_pct) < threshold_pct:
            continue
        catalyst = _classify_catalyst(move)
        if catalyst is None:
            continue
        if _was_flagged_within_window(move, flags, window_days=window_days):
            continue
        out.append(
            Miss(
                ticker=move.ticker.upper(),
                move_date=move.date,
                move_pct=move.price_change_pct,
                catalyst_type=catalyst,
                why_we_missed=_diagnose(move, catalyst),
            )
        )
    return out


def _diagnose(move: DailyMoveRecord, catalyst: str) -> str:
    """One-line human-readable explanation for the miss."""
    if catalyst == "filing":
        return (
            f"SEC filing landed but Sentinel didn't escalate state. "
            f"Filing signal weight may be too low."
        )
    if catalyst == "volume_spike":
        return (
            f"Volume spiked to {move.volume_relative:.1f}x avg but no "
            f"narrative signal accompanied — pure-volume threshold may "
            f"need tightening."
        )
    return (
        f"Filing + {move.volume_relative:.1f}x volume both fired but "
        f"didn't combine to trigger state transition. Confirming-signal "
        f"count rule may be too strict."
    )
