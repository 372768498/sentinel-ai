"""Notification dispatcher — single source of truth for whether a Pro
alert push fires for a given user at a given time.

Decision pipeline (in order):
  1. Vacation override (User.vacationUntil > now or mode == vacation)
  2. Mode filter (mode.min_state_for_push)
  3. Session filter (intraday / after-hours flags per mode)
  4. Quiet hours (mode.respect_quiet_hours, with INFLECTION override)

Returns a PushDecision with `should_push: bool`, `reason: str`, and
`queue_until: Optional[datetime]` (for digest deferral).

DOES NOT actually send the push — that's the publisher's job. This is a
pure decision function so the caller can log/audit reasons consistently.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import Optional

from .notification_modes import (
    MODE_VACATION,
    NOTIFICATION_MODES,
    ModeConfig,
    get_mode,
)
from .state import STATE_RANK, SentinelState


# Session boundaries — ET hours. Pre-market < 09:30, regular 09:30-16:00,
# after-hours 16:00-20:00, overnight 20:00-04:00. We treat anything
# inside regular trading hours as "intraday" for the mode filter.
INTRADAY_START_HOUR_ET = 9   # 09:30 rounded down to 09:00
INTRADAY_END_HOUR_ET = 16
AFTER_HOURS_END_HOUR_ET = 20


@dataclass(frozen=True)
class UserNotificationProfile:
    """Subset of User columns the dispatcher reads.

    Built by the caller from the Prisma User row. The dispatcher does NOT
    open a DB connection — keeping it pure makes it cheap to unit-test
    every mode × state × time combination.
    """
    notification_mode: str
    quiet_hours_start: Optional[int]
    quiet_hours_end: Optional[int]
    timezone: str
    vacation_until: Optional[datetime]


@dataclass(frozen=True)
class AlertCandidate:
    ticker: str
    state: SentinelState


@dataclass(frozen=True)
class PushDecision:
    should_push: bool
    reason: str
    queue_until: Optional[datetime] = None

    @classmethod
    def push(cls, reason: str = "ok") -> "PushDecision":
        return cls(should_push=True, reason=reason)

    @classmethod
    def hold(cls, reason: str, queue_until: Optional[datetime] = None) -> "PushDecision":
        return cls(should_push=False, reason=reason, queue_until=queue_until)


def _current_session_et(now_et: datetime) -> str:
    """Returns 'pre_market' / 'intraday' / 'after_hours' / 'overnight'."""
    h = now_et.hour
    if INTRADAY_START_HOUR_ET <= h < INTRADAY_END_HOUR_ET:
        return "intraday"
    if INTRADAY_END_HOUR_ET <= h < AFTER_HOURS_END_HOUR_ET:
        return "after_hours"
    if h < INTRADAY_START_HOUR_ET:
        return "pre_market"
    return "overnight"


def _in_quiet_hours(profile: UserNotificationProfile, now_et: datetime) -> bool:
    """True when current hour is inside the user's quiet-hours window.

    Window is inclusive of start, exclusive of end, wraps across midnight
    when end < start (e.g., start=22, end=7 → 22, 23, 0, ..., 6 are quiet).
    """
    start = profile.quiet_hours_start
    end = profile.quiet_hours_end
    if start is None or end is None:
        return False
    h = now_et.hour
    if start <= end:
        return start <= h < end
    # wrap-around (e.g., 22 → 7)
    return h >= start or h < end


def should_push_alert(
    *,
    user: UserNotificationProfile,
    alert: AlertCandidate,
    now_et: datetime,
) -> PushDecision:
    """The single decision function. Pure — no IO, no state."""
    # 1. Vacation override (date or mode)
    if user.notification_mode == MODE_VACATION:
        return PushDecision.hold("vacation_mode_no_push")
    if user.vacation_until is not None and now_et < user.vacation_until:
        return PushDecision.hold(
            "vacation_until_active", queue_until=user.vacation_until
        )

    mode: ModeConfig = get_mode(user.notification_mode)

    # 2. Mode-level state filter
    min_state = mode.min_state_for_push
    if min_state is None:
        return PushDecision.hold("mode_blocks_push")
    if STATE_RANK[alert.state] < STATE_RANK[min_state]:
        return PushDecision.hold(
            f"below_threshold (state={alert.state.value} < min={min_state.value})"
        )

    # 3. Session filter
    session = _current_session_et(now_et)
    if session == "intraday" and not mode.allows_intraday:
        return PushDecision.hold("intraday_disabled")
    if session == "after_hours" and not mode.allows_after_hours:
        return PushDecision.hold("after_hours_disabled")

    # 4. Quiet hours — INFLECTION always overrides
    if mode.respect_quiet_hours and _in_quiet_hours(user, now_et):
        if alert.state is not SentinelState.INFLECTION:
            return PushDecision.hold("quiet_hours")

    return PushDecision.push()
