"""Tests for SentinelState enum + display + rank helpers."""
from __future__ import annotations

import pytest

from app.marketing.state import (
    STATE_DISPLAY,
    STATE_RANK,
    SentinelState,
    is_at_least,
)


def test_enum_has_exactly_four_states() -> None:
    assert len(SentinelState) == 4
    assert {s for s in SentinelState} == {
        SentinelState.CALM,
        SentinelState.WATCHING,
        SentinelState.HEATED,
        SentinelState.INFLECTION,
    }


def test_enum_values_are_lowercase_strings() -> None:
    for state in SentinelState:
        assert isinstance(state.value, str)
        assert state.value == state.value.lower()


def test_display_table_complete_and_has_required_keys() -> None:
    required = {"emoji", "label", "one_liner", "color_hex"}
    for state in SentinelState:
        assert state in STATE_DISPLAY
        assert required.issubset(STATE_DISPLAY[state].keys())
        # color hex sanity
        assert STATE_DISPLAY[state]["color_hex"].startswith("#")
        assert len(STATE_DISPLAY[state]["color_hex"]) == 7


def test_display_labels_are_distinct_and_titlecase() -> None:
    labels = {STATE_DISPLAY[s]["label"] for s in SentinelState}
    assert len(labels) == 4
    for label in labels:
        assert label[0].isupper()


def test_rank_monotonic_calm_to_inflection() -> None:
    assert STATE_RANK[SentinelState.CALM] == 0
    assert STATE_RANK[SentinelState.WATCHING] == 1
    assert STATE_RANK[SentinelState.HEATED] == 2
    assert STATE_RANK[SentinelState.INFLECTION] == 3


def test_is_at_least_self() -> None:
    for state in SentinelState:
        assert is_at_least(state, state) is True


def test_is_at_least_strictly_above() -> None:
    assert is_at_least(SentinelState.HEATED, SentinelState.WATCHING) is True
    assert is_at_least(SentinelState.INFLECTION, SentinelState.CALM) is True


def test_is_at_least_below_is_false() -> None:
    assert is_at_least(SentinelState.CALM, SentinelState.WATCHING) is False
    assert is_at_least(SentinelState.WATCHING, SentinelState.HEATED) is False
    assert is_at_least(SentinelState.HEATED, SentinelState.INFLECTION) is False
