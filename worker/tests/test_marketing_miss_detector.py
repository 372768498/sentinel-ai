"""Tests for miss_detector.detect_misses()."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.marketing.miss_detector import (
    BIG_MOVE_THRESHOLD_PCT,
    DailyMoveRecord,
    FlagHistoryRow,
    detect_misses,
)


TODAY = date(2026, 5, 12)


def _move(
    ticker: str = "NVDA",
    pct: float = 8.0,
    had_catalyst: bool = True,
    volume_relative: float = 2.0,
    days_ago: int = 0,
) -> DailyMoveRecord:
    return DailyMoveRecord(
        ticker=ticker,
        date=TODAY - timedelta(days=days_ago),
        price_change_pct=pct,
        had_catalyst=had_catalyst,
        volume_relative=volume_relative,
    )


def _flag(ticker: str, days_ago: int) -> FlagHistoryRow:
    return FlagHistoryRow(
        ticker=ticker,
        flagged_at=TODAY - timedelta(days=days_ago),
        state_at_flag="watching",
    )


def test_small_move_is_not_a_miss() -> None:
    moves = [_move(pct=3.0)]
    misses = detect_misses(moves=moves, flag_history=[])
    assert misses == []


def test_big_move_with_catalyst_and_no_flag_is_miss() -> None:
    moves = [_move(pct=10.0, had_catalyst=True, volume_relative=2.5)]
    misses = detect_misses(moves=moves, flag_history=[])
    assert len(misses) == 1
    m = misses[0]
    assert m.ticker == "NVDA"
    assert m.catalyst_type == "mixed"
    assert m.move_pct == 10.0


def test_big_move_without_catalyst_or_volume_is_not_a_miss() -> None:
    """Pure price move without supporting evidence is noise, not a miss."""
    moves = [_move(pct=10.0, had_catalyst=False, volume_relative=1.0)]
    misses = detect_misses(moves=moves, flag_history=[])
    assert misses == []


def test_big_move_with_catalyst_only_classified_as_filing() -> None:
    moves = [_move(pct=8.0, had_catalyst=True, volume_relative=1.0)]
    misses = detect_misses(moves=moves, flag_history=[])
    assert len(misses) == 1
    assert misses[0].catalyst_type == "filing"


def test_big_move_with_volume_only_classified_as_volume_spike() -> None:
    moves = [_move(pct=8.0, had_catalyst=False, volume_relative=2.5)]
    misses = detect_misses(moves=moves, flag_history=[])
    assert len(misses) == 1
    assert misses[0].catalyst_type == "volume_spike"


def test_flag_within_window_disqualifies_miss() -> None:
    moves = [_move(pct=10.0, days_ago=0)]
    flags = [_flag("NVDA", days_ago=1)]  # flagged 1 day before move
    misses = detect_misses(moves=moves, flag_history=flags, window_days=1)
    assert misses == []


def test_flag_outside_window_still_a_miss() -> None:
    moves = [_move(pct=10.0, days_ago=0)]
    flags = [_flag("NVDA", days_ago=5)]  # flag too old
    misses = detect_misses(moves=moves, flag_history=flags, window_days=1)
    assert len(misses) == 1


def test_flag_for_other_ticker_doesnt_disqualify() -> None:
    moves = [_move(ticker="NVDA", pct=10.0)]
    flags = [_flag("AMD", days_ago=1)]
    misses = detect_misses(moves=moves, flag_history=flags)
    assert len(misses) == 1
    assert misses[0].ticker == "NVDA"


def test_threshold_override() -> None:
    moves = [_move(pct=5.0, had_catalyst=True, volume_relative=2.0)]
    # Default threshold 7 → no miss
    assert detect_misses(moves=moves, flag_history=[]) == []
    # Custom threshold 4 → it's a miss
    misses = detect_misses(moves=moves, flag_history=[], threshold_pct=4.0)
    assert len(misses) == 1


def test_negative_move_also_qualifies() -> None:
    """A -8% drop with a catalyst is just as much of a miss as +8%."""
    moves = [_move(pct=-9.0, had_catalyst=True, volume_relative=2.0)]
    misses = detect_misses(moves=moves, flag_history=[])
    assert len(misses) == 1
    assert misses[0].move_pct == -9.0


def test_diagnose_text_per_catalyst_type() -> None:
    cases = [
        (DailyMoveRecord("X", TODAY, 8.0, True, 1.0), "filing"),
        (DailyMoveRecord("X", TODAY, 8.0, False, 3.0), "volume"),
        (DailyMoveRecord("X", TODAY, 8.0, True, 3.0), "Filing"),
    ]
    for move, expected in cases:
        misses = detect_misses(moves=[move], flag_history=[])
        assert len(misses) == 1
        assert expected.lower() in misses[0].why_we_missed.lower()
