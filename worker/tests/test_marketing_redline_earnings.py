"""Tests for pre-earnings window redline."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.marketing.redline_earnings import (
    BLOCKED_PHRASES_PRE_EARNINGS,
    WINDOW_DAYS_AFTER,
    WINDOW_DAYS_BEFORE,
    check_earnings_window,
)

TODAY = date(2026, 5, 12)


def test_no_earnings_date_always_ok() -> None:
    res = check_earnings_window(
        text="set up for a beat with high conviction",
        earnings_date=None,
        today=TODAY,
    )
    assert res.ok is True
    assert res.in_window is False
    assert res.days_to_earnings is None


def test_far_future_earnings_outside_window() -> None:
    earnings = TODAY + timedelta(days=30)
    res = check_earnings_window(
        text="bullish heading into earnings",
        earnings_date=earnings,
        today=TODAY,
    )
    assert res.ok is True
    assert res.in_window is False
    assert res.days_to_earnings == 30


def test_far_past_earnings_outside_window() -> None:
    earnings = TODAY - timedelta(days=10)
    res = check_earnings_window(
        text="should outperform",
        earnings_date=earnings,
        today=TODAY,
    )
    assert res.ok is True
    assert res.in_window is False


def test_exactly_at_window_boundary_before() -> None:
    earnings = TODAY + timedelta(days=WINDOW_DAYS_BEFORE)
    res = check_earnings_window(
        text="we are watching",
        earnings_date=earnings,
        today=TODAY,
    )
    assert res.in_window is True
    assert res.ok is True  # no blocked phrase


def test_exactly_at_window_boundary_after() -> None:
    earnings = TODAY - timedelta(days=WINDOW_DAYS_AFTER)
    res = check_earnings_window(
        text="anomaly detected",
        earnings_date=earnings,
        today=TODAY,
    )
    assert res.in_window is True
    assert res.ok is True


def test_one_day_outside_window_after() -> None:
    earnings = TODAY - timedelta(days=WINDOW_DAYS_AFTER + 1)
    res = check_earnings_window(
        text="high conviction setup",
        earnings_date=earnings,
        today=TODAY,
    )
    assert res.in_window is False
    assert res.ok is True


@pytest.mark.parametrize("phrase", BLOCKED_PHRASES_PRE_EARNINGS)
def test_every_blocked_phrase_triggers_inside_window(phrase: str) -> None:
    earnings = TODAY + timedelta(days=3)  # well inside window
    text = f"Some prose. {phrase}. More prose. https://example.com"
    res = check_earnings_window(
        text=text, earnings_date=earnings, today=TODAY
    )
    assert res.ok is False
    assert res.in_window is True
    assert res.blocked_phrase == phrase


def test_case_insensitive_blocked_phrase() -> None:
    earnings = TODAY + timedelta(days=3)
    res = check_earnings_window(
        text="Consider BUYING right before the report",
        earnings_date=earnings,
        today=TODAY,
    )
    assert res.ok is False
    assert res.blocked_phrase == "consider buying"


def test_clean_text_inside_window_is_ok() -> None:
    earnings = TODAY + timedelta(days=3)
    text = (
        "$NVDA scheduled to report. Elevated activity ahead of earnings. "
        "We are watching. https://sec.gov/x  Not financial advice."
    )
    res = check_earnings_window(
        text=text, earnings_date=earnings, today=TODAY
    )
    assert res.ok is True
    assert res.in_window is True


def test_reason_string_format() -> None:
    earnings = TODAY + timedelta(days=2)
    res = check_earnings_window(
        text="this is a buying opportunity",
        earnings_date=earnings,
        today=TODAY,
    )
    assert res.ok is False
    reason = res.reason()
    assert "earnings_window:" in reason
    assert "buying opportunity" in reason
    assert "d=2" in reason
