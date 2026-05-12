"""Tests for notification mode preset table."""
from __future__ import annotations

import pytest

from app.marketing.notification_modes import (
    ALL_MODES,
    MODE_ACTIVE,
    MODE_CUSTOM,
    MODE_MORNING,
    MODE_SLEEP,
    MODE_VACATION,
    NOTIFICATION_MODES,
    get_mode,
)
from app.marketing.state import SentinelState


def test_all_modes_present_in_table() -> None:
    for mode in ALL_MODES:
        assert mode in NOTIFICATION_MODES


def test_morning_inflection_only() -> None:
    cfg = NOTIFICATION_MODES[MODE_MORNING]
    assert cfg.min_state_for_push is SentinelState.INFLECTION
    assert cfg.allows_intraday is False
    assert cfg.allows_after_hours is False


def test_active_allows_intraday_heated() -> None:
    cfg = NOTIFICATION_MODES[MODE_ACTIVE]
    assert cfg.allows_intraday is True
    assert cfg.allows_after_hours is True
    assert cfg.min_state_for_push is SentinelState.HEATED


def test_sleep_respects_quiet_hours() -> None:
    cfg = NOTIFICATION_MODES[MODE_SLEEP]
    assert cfg.respect_quiet_hours is True
    assert cfg.min_state_for_push is SentinelState.INFLECTION
    assert cfg.allows_after_hours is False


def test_vacation_pushes_nothing() -> None:
    cfg = NOTIFICATION_MODES[MODE_VACATION]
    assert cfg.min_state_for_push is None
    assert cfg.allows_intraday is False
    assert cfg.allows_after_hours is False
    assert cfg.email_daily is True


def test_custom_placeholder_behaves_like_morning_for_now() -> None:
    cfg = NOTIFICATION_MODES[MODE_CUSTOM]
    assert cfg.min_state_for_push is SentinelState.INFLECTION
    assert cfg.allows_intraday is False


def test_email_times_are_in_morning_hours() -> None:
    for mode_name, cfg in NOTIFICATION_MODES.items():
        assert 6 <= cfg.email_time_hour_et <= 10, (
            f"{mode_name} email_time_hour_et={cfg.email_time_hour_et} outside 6-10 ET"
        )


def test_get_mode_falls_back_to_morning_for_unknown() -> None:
    cfg = get_mode("not_a_real_mode")
    assert cfg is NOTIFICATION_MODES[MODE_MORNING]


def test_get_mode_returns_exact_match_when_known() -> None:
    cfg = get_mode(MODE_ACTIVE)
    assert cfg is NOTIFICATION_MODES[MODE_ACTIVE]
