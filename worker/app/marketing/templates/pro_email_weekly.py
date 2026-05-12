"""Pro Weekly 'What I told you' email.

Three-layer scoreboard per week:
  1. Anomaly detection: alerts we sent / alerts that played out in price
     or volume within 5 trading days (NEVER claim direction correctness)
  2. Direction reads: only when we noted a direction; confirmed rate
     reported with explicit hedging ("direction is hard")
  3. Misses: things that moved >=7% with catalyst that we didn't flag

The weekly digest is the trust-building artifact. It's why Pro Pro
subscribers pay $39 vs $19 — the system is honest about what it got
wrong, not just what it got right.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ..state import STATE_DISPLAY, SentinelState


TEMPLATE = """\
Subject: Your Sentinel week: {alert_count_week} alerts, {confirmed_count} confirmed
Preview: A look back at what we flagged and what happened next.

─────────────────────────
SENTINEL PRO · YOUR WEEK
{week_range_label}
─────────────────────────

ALERTS WE SENT YOU THIS WEEK: {alert_count_week}

What we flagged             What happened next:
─────────────────────────   ──────────────────────────
{weekly_alerts_table}


SIGNAL QUALITY THIS WEEK

✓ Anomaly detection
  {anomalies_caught} / {anomalies_total} caught ({anomaly_pct}%)

~ Direction reads (when we noted direction)
  {direction_confirmed} / {direction_called} confirmed ({direction_pct}%)
  We're cautious here. Direction is hard.

✗ Things we missed entirely
{misses_block}

──────────

YOUR WATCHLIST AT A GLANCE

Strongest signal right now: {strongest_ticker} ({strongest_state})
Weakest:                    {weakest_ticker} ({weakest_state})
Earnings next week:         {earnings_next_week_list}
Quiet for 14+ days:         {quiet_long_list}
                            {quiet_suggestion}

──────────

[ Download PDF of this week → {pdf_url} ]
[ Share this report → {share_url} ]


─────────────────────────
Manage watchlist → {manage_url}
Change notification mode → {mode_url}
─────────────────────────

Not financial advice.
"""


CONFIRMATION_CONFIRMED = "confirmed"
CONFIRMATION_NEUTRAL = "neutral"
CONFIRMATION_DIVERGED = "diverged"


@dataclass(frozen=True)
class WeeklyAlertRow:
    weekday_label: str  # 'Mon' / 'Tue' / ...
    ticker: str
    state_change: str   # 'Calm→Watch' / 'Heated' / etc — display string only
    move_label: str     # '+6.2% by Fri' / 'flat' etc.
    confirmation: str   # see CONFIRMATION_* above


def render_weekly_alerts_table(rows: Iterable[WeeklyAlertRow]) -> str:
    """Mono-spaced 5-column table per spec layout."""
    badge = {
        CONFIRMATION_CONFIRMED: "✓ confirmed",
        CONFIRMATION_NEUTRAL: "~ neutral",
        CONFIRMATION_DIVERGED: "✗ diverged",
    }
    lines: list[str] = []
    for r in rows:
        b = badge.get(r.confirmation, "~ neutral")
        lines.append(
            f"{r.weekday_label:<3}  ${r.ticker:<5}  →  {r.state_change:<14}  "
            f"{r.move_label:<16}  {b}"
        )
    return "\n".join(lines) if lines else "  (no alerts this week)"


def render_misses_block(miss_tickers: list[str]) -> str:
    """Bullet list of ticker symbols we missed entirely this week.

    Empty list → 'None this week — see methodology' wording so we never
    silently hide the absence of misses (which would be suspicious).
    """
    if not miss_tickers:
        return (
            "  None this week — but see methodology for how we count.\n"
            "  Zero misses is rare; if you see it >2 weeks in a row,\n"
            "  it likely means our universe is too narrow."
        )
    return "\n".join(f"  - ${t}" for t in miss_tickers)


@dataclass(frozen=True)
class ProEmailWeeklyPayload:
    alert_count_week: int
    confirmed_count: int
    week_range_label: str
    weekly_alerts_table: str
    anomalies_caught: int
    anomalies_total: int
    anomaly_pct: int
    direction_called: int
    direction_confirmed: int
    direction_pct: int
    misses_block: str
    strongest_ticker: str
    strongest_state: SentinelState
    weakest_ticker: str
    weakest_state: SentinelState
    earnings_next_week_list: str
    quiet_long_list: str
    quiet_suggestion: str
    pdf_url: str
    share_url: str
    manage_url: str
    mode_url: str


def render_weekly_email(p: ProEmailWeeklyPayload) -> str:
    strong = STATE_DISPLAY[p.strongest_state]
    weak = STATE_DISPLAY[p.weakest_state]
    return TEMPLATE.format(
        alert_count_week=p.alert_count_week,
        confirmed_count=p.confirmed_count,
        week_range_label=p.week_range_label,
        weekly_alerts_table=p.weekly_alerts_table,
        anomalies_caught=p.anomalies_caught,
        anomalies_total=p.anomalies_total,
        anomaly_pct=p.anomaly_pct,
        direction_called=p.direction_called,
        direction_confirmed=p.direction_confirmed,
        direction_pct=p.direction_pct,
        misses_block=p.misses_block,
        strongest_ticker=p.strongest_ticker,
        strongest_state=f"{strong['emoji']} {strong['label']}",
        weakest_ticker=p.weakest_ticker,
        weakest_state=f"{weak['emoji']} {weak['label']}",
        earnings_next_week_list=p.earnings_next_week_list,
        quiet_long_list=p.quiet_long_list,
        quiet_suggestion=p.quiet_suggestion,
        pdf_url=p.pdf_url,
        share_url=p.share_url,
        manage_url=p.manage_url,
        mode_url=p.mode_url,
    )
