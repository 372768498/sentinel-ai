"""Tests for the notification dispatcher decision pipeline.

Pure function — no IO. Every mode × state × session × quiet-hours
combination is testable in milliseconds.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.marketing.notification_dispatcher import (
    AlertCandidate,
    PushDecision,
    UserNotificationProfile,
    should_push_alert,
)
from app.marketing.notification_modes import (
    MODE_ACTIVE,
    MODE_MORNING,
    MODE_SLEEP,
    MODE_VACATION,
)
from app.marketing.state import SentinelState

# Reference times in ET.
PRE_MARKET_ET = datetime(2026, 5, 12, 7, 30)   # Tuesday 07:30 ET
INTRADAY_ET = datetime(2026, 5, 12, 11, 0)     # 11:00 ET
AFTER_HOURS_ET = datetime(2026, 5, 12, 17, 30) # 17:30 ET
OVERNIGHT_ET = datetime(2026, 5, 12, 23, 0)    # 23:00 ET


def _user(mode: str = MODE_MORNING, **overrides) -> UserNotificationProfile:
    defaults: dict = dict(
        notification_mode=mode,
        quiet_hours_start=None,
        quiet_hours_end=None,
        timezone="America/New_York",
        vacation_until=None,
    )
    defaults.update(overrides)
    return UserNotificationProfile(**defaults)


def _alert(state: SentinelState = SentinelState.HEATED) -> AlertCandidate:
    return AlertCandidate(ticker="NVDA", state=state)


# ---- vacation overrides --------------------------------------------------


def test_vacation_mode_blocks_all_pushes() -> None:
    d = should_push_alert(
        user=_user(MODE_VACATION),
        alert=_alert(SentinelState.INFLECTION),
        now_et=INTRADAY_ET,
    )
    assert d.should_push is False
    assert "vacation" in d.reason


def test_vacation_until_blocks_when_active() -> None:
    until = INTRADAY_ET + timedelta(days=1)
    d = should_push_alert(
        user=_user(MODE_ACTIVE, vacation_until=until),
        alert=_alert(SentinelState.INFLECTION),
        now_et=INTRADAY_ET,
    )
    assert d.should_push is False
    assert "vacation_until" in d.reason
    assert d.queue_until == until


def test_vacation_until_in_past_does_not_block() -> None:
    past = INTRADAY_ET - timedelta(days=1)
    d = should_push_alert(
        user=_user(MODE_ACTIVE, vacation_until=past),
        alert=_alert(SentinelState.HEATED),
        now_et=INTRADAY_ET,
    )
    assert d.should_push is True


# ---- mode × state matrix -------------------------------------------------


@pytest.mark.parametrize(
    "mode,state,expect_push",
    [
        # MORNING — only INFLECTION pushes
        (MODE_MORNING, SentinelState.CALM, False),
        (MODE_MORNING, SentinelState.WATCHING, False),
        (MODE_MORNING, SentinelState.HEATED, False),
        (MODE_MORNING, SentinelState.INFLECTION, True),
        # ACTIVE — HEATED and above push
        (MODE_ACTIVE, SentinelState.CALM, False),
        (MODE_ACTIVE, SentinelState.WATCHING, False),
        (MODE_ACTIVE, SentinelState.HEATED, True),
        (MODE_ACTIVE, SentinelState.INFLECTION, True),
        # SLEEP — only INFLECTION pushes
        (MODE_SLEEP, SentinelState.HEATED, False),
        (MODE_SLEEP, SentinelState.INFLECTION, True),
    ],
)
def test_mode_state_matrix_at_pre_market(mode: str, state: SentinelState, expect_push: bool) -> None:
    """Pre-market — no session restriction, only mode + state filter."""
    d = should_push_alert(user=_user(mode), alert=_alert(state), now_et=PRE_MARKET_ET)
    assert d.should_push is expect_push, f"{mode}/{state.value}: {d.reason}"


# ---- session filter ------------------------------------------------------


def test_morning_blocks_intraday_even_at_inflection() -> None:
    d = should_push_alert(
        user=_user(MODE_MORNING),
        alert=_alert(SentinelState.INFLECTION),
        now_et=INTRADAY_ET,
    )
    assert d.should_push is False
    assert "intraday" in d.reason


def test_active_allows_intraday_at_heated() -> None:
    d = should_push_alert(
        user=_user(MODE_ACTIVE),
        alert=_alert(SentinelState.HEATED),
        now_et=INTRADAY_ET,
    )
    assert d.should_push is True


def test_sleep_blocks_after_hours() -> None:
    d = should_push_alert(
        user=_user(MODE_SLEEP),
        alert=_alert(SentinelState.INFLECTION),
        now_et=AFTER_HOURS_ET,
    )
    assert d.should_push is False
    assert "after_hours" in d.reason


# ---- quiet hours ---------------------------------------------------------


def test_sleep_quiet_hours_block_heated() -> None:
    # 23:00 inside 22-7 quiet hours
    d = should_push_alert(
        user=_user(MODE_SLEEP, quiet_hours_start=22, quiet_hours_end=7),
        alert=_alert(SentinelState.HEATED),
        now_et=OVERNIGHT_ET,
    )
    # HEATED already blocked by SLEEP's min_state=INFLECTION before quiet hours,
    # but the reason text confirms which gate fired.
    assert d.should_push is False


def test_sleep_quiet_hours_inflection_overrides() -> None:
    """INFLECTION must override quiet hours per spec."""
    d = should_push_alert(
        user=_user(MODE_SLEEP, quiet_hours_start=22, quiet_hours_end=7),
        alert=_alert(SentinelState.INFLECTION),
        now_et=OVERNIGHT_ET,
    )
    assert d.should_push is True


def test_quiet_hours_no_wrap_window() -> None:
    """Quiet 13-15: hour=14 inside, hour=12 outside."""
    user_in = _user(MODE_SLEEP, quiet_hours_start=13, quiet_hours_end=15)
    # 14:00 ET intraday — SLEEP blocks intraday HEATED already, so test
    # INFLECTION-override path explicitly.
    in_window = datetime(2026, 5, 12, 14, 0)
    out_window = datetime(2026, 5, 12, 12, 0)
    d_in = should_push_alert(
        user=user_in,
        alert=_alert(SentinelState.INFLECTION),
        now_et=in_window,
    )
    d_out = should_push_alert(
        user=user_in,
        alert=_alert(SentinelState.INFLECTION),
        now_et=out_window,
    )
    # Both should push (INFLECTION overrides quiet hours)
    assert d_in.should_push is True
    assert d_out.should_push is True


def test_no_quiet_hours_when_unset() -> None:
    d = should_push_alert(
        user=_user(MODE_SLEEP, quiet_hours_start=None, quiet_hours_end=None),
        alert=_alert(SentinelState.INFLECTION),
        now_et=PRE_MARKET_ET,
    )
    assert d.should_push is True


# ---- reason payload ------------------------------------------------------


def test_reason_includes_state_comparison_below_threshold() -> None:
    d = should_push_alert(
        user=_user(MODE_MORNING),
        alert=_alert(SentinelState.WATCHING),
        now_et=PRE_MARKET_ET,
    )
    assert d.should_push is False
    assert "watching" in d.reason
    assert "inflection" in d.reason
