"""Tests for the Pro weekly digest template."""
from __future__ import annotations

import re

import pytest

from app.marketing.state import SentinelState
from app.marketing.templates import pro_email_weekly as pew


FORBIDDEN_WORDS_RE = re.compile(
    r"\b(score|rating|\d{1,3}\s*/\s*100|out\s+of\s+(?:100|ten|10))\b",
    re.IGNORECASE,
)


def test_alerts_table_renders_three_outcome_badges() -> None:
    rows = [
        pew.WeeklyAlertRow(
            weekday_label="Mon", ticker="AMD",
            state_change="Heated", move_label="+6.2% by Fri",
            confirmation=pew.CONFIRMATION_CONFIRMED,
        ),
        pew.WeeklyAlertRow(
            weekday_label="Tue", ticker="TSLA",
            state_change="Watching", move_label="-1.8% (held)",
            confirmation=pew.CONFIRMATION_NEUTRAL,
        ),
        pew.WeeklyAlertRow(
            weekday_label="Wed", ticker="NVDA",
            state_change="Calm→Watch", move_label="flat",
            confirmation=pew.CONFIRMATION_DIVERGED,
        ),
    ]
    table = pew.render_weekly_alerts_table(rows)
    assert "✓ confirmed" in table
    assert "~ neutral" in table
    assert "✗ diverged" in table
    assert FORBIDDEN_WORDS_RE.search(table) is None


def test_alerts_table_empty_shows_placeholder() -> None:
    table = pew.render_weekly_alerts_table([])
    assert "no alerts" in table


def test_misses_block_lists_tickers() -> None:
    out = pew.render_misses_block(["AMD", "TSLA"])
    assert "$AMD" in out and "$TSLA" in out


def test_misses_block_empty_says_so_explicitly() -> None:
    """Zero misses must be flagged as suspicious — never silently hide."""
    out = pew.render_misses_block([])
    assert "None this week" in out
    assert "methodology" in out


def test_weekly_email_full_render_safe() -> None:
    rows = [
        pew.WeeklyAlertRow(
            weekday_label="Fri", ticker="MSFT", state_change="Inflection",
            move_label="+3.4%", confirmation=pew.CONFIRMATION_CONFIRMED,
        ),
    ]
    payload = pew.ProEmailWeeklyPayload(
        alert_count_week=5,
        confirmed_count=3,
        week_range_label="May 5-9, 2026",
        weekly_alerts_table=pew.render_weekly_alerts_table(rows),
        anomalies_caught=12,
        anomalies_total=14,
        anomaly_pct=86,
        direction_called=4,
        direction_confirmed=2,
        direction_pct=50,
        misses_block=pew.render_misses_block(["AMD"]),
        strongest_ticker="NVDA",
        strongest_state=SentinelState.HEATED,
        weakest_ticker="MSFT",
        weakest_state=SentinelState.CALM,
        earnings_next_week_list="AMD (Tue), TSLA (Wed)",
        quiet_long_list="MSFT, GOOGL",
        quiet_suggestion="Consider removing if no active thesis.",
        pdf_url="https://app.jilo.ai/pro/weekly.pdf",
        share_url="https://app.jilo.ai/pro/share/abc",
        manage_url="https://app.jilo.ai/manage",
        mode_url="https://app.jilo.ai/mode",
    )
    out = pew.render_weekly_email(payload)
    assert "SENTINEL PRO" in out
    assert "NVDA" in out  # bare ticker in strongest/weakest lines per spec
    assert "$MSFT" in out  # $-prefixed inside the alerts table
    assert "🟠 Heated" in out  # strongest state badge
    assert "🔵 Calm" in out    # weakest
    assert "Direction is hard" in out
    assert "not financial advice" in out.lower()
    assert FORBIDDEN_WORDS_RE.search(out) is None


def test_confirmation_constants_used_in_render() -> None:
    """The badge mapping must cover all three constants exposed."""
    rows = [
        pew.WeeklyAlertRow(
            weekday_label=day, ticker=f"T{i}", state_change="X",
            move_label="0%", confirmation=cstate,
        )
        for i, (day, cstate) in enumerate(
            (("Mon", pew.CONFIRMATION_CONFIRMED),
             ("Tue", pew.CONFIRMATION_NEUTRAL),
             ("Wed", pew.CONFIRMATION_DIVERGED))
        )
    ]
    table = pew.render_weekly_alerts_table(rows)
    # Sanity: 3 rows produce 3 distinct badges
    badges = ("✓ confirmed", "~ neutral", "✗ diverged")
    for b in badges:
        assert b in table
