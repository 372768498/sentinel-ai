"""Notification mode presets — 5 predefined push-behavior profiles.

The mode is stored on User.notificationMode (Sprint 1 schema migration).
Default is 'morning'. The 'custom' mode is reserved for users who have
been active >=30 days; for Sprint 3 it behaves identically to 'morning'.

Each mode caps the minimum SentinelState that triggers a push, plus
session and quiet-hours behavior. The notification dispatcher consults
this table — there is no other source of truth.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .state import SentinelState


MODE_MORNING = "morning"
MODE_ACTIVE = "active"
MODE_SLEEP = "sleep"
MODE_VACATION = "vacation"
MODE_CUSTOM = "custom"

ALL_MODES = (MODE_MORNING, MODE_ACTIVE, MODE_SLEEP, MODE_VACATION, MODE_CUSTOM)


@dataclass(frozen=True)
class ModeConfig:
    label: str
    description: str
    best_for: str
    allows_intraday: bool
    allows_after_hours: bool
    # None == nothing pushes; queue for daily email instead.
    min_state_for_push: Optional[SentinelState]
    email_daily: bool
    email_time_hour_et: int
    respect_quiet_hours: bool


NOTIFICATION_MODES: dict[str, ModeConfig] = {
    MODE_MORNING: ModeConfig(
        label="Morning person",
        description="Pre-market digest only. No intraday alerts.",
        best_for="Long-term investors",
        allows_intraday=False,
        allows_after_hours=False,
        min_state_for_push=SentinelState.INFLECTION,
        email_daily=True,
        email_time_hour_et=7,
        respect_quiet_hours=False,
    ),
    MODE_ACTIVE: ModeConfig(
        label="Active trader",
        description="Pre-market + Heated state changes intraday.",
        best_for="1-3 trades per week",
        allows_intraday=True,
        allows_after_hours=True,
        min_state_for_push=SentinelState.HEATED,
        email_daily=True,
        email_time_hour_et=7,
        respect_quiet_hours=False,
    ),
    MODE_SLEEP: ModeConfig(
        label="Sleep mode",
        description="Only Inflection state. Queue everything else.",
        best_for="Phone-buzz averse",
        allows_intraday=True,
        allows_after_hours=False,
        min_state_for_push=SentinelState.INFLECTION,
        email_daily=True,
        email_time_hour_et=8,
        respect_quiet_hours=True,
    ),
    MODE_VACATION: ModeConfig(
        label="Vacation",
        description="Email-only digest. No Telegram pushes.",
        best_for="Travel, family time",
        allows_intraday=False,
        allows_after_hours=False,
        min_state_for_push=None,
        email_daily=True,
        email_time_hour_et=9,
        respect_quiet_hours=False,
    ),
    MODE_CUSTOM: ModeConfig(
        # Sprint 3 placeholder — same as 'morning' until per-user thresholds
        # land. Frontend exposes 'custom' only after 30 days of use.
        label="Custom",
        description="Set your own thresholds (requires 30-day history).",
        best_for="Power users",
        allows_intraday=False,
        allows_after_hours=False,
        min_state_for_push=SentinelState.INFLECTION,
        email_daily=True,
        email_time_hour_et=7,
        respect_quiet_hours=True,
    ),
}


def get_mode(mode_name: str) -> ModeConfig:
    """Return ModeConfig; falls back to MORNING on unknown name."""
    return NOTIFICATION_MODES.get(mode_name, NOTIFICATION_MODES[MODE_MORNING])
