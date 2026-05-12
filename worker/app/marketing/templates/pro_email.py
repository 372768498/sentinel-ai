"""Pro Email Daily — watchlist status, biggest change, week-ahead calendar.

Includes a render_watchlist_table() helper that emits the per-ticker
mono-spaced table plus a 'Calm for 14+ days, consider removing' nudge.
The nudge is a deliberate product position: we make it easier to NOT
watch noise.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from ..state import STATE_DISPLAY, SentinelState


TEMPLATE = """\
Subject: {subject_dynamic}
Preview: {preview_dynamic}

─────────────────────────
SENTINEL PRO · YOUR DAILY
{date_long} · sent {delivery_time_et} ET (your preference)
─────────────────────────

▎YOUR WATCHLIST STATUS

{watchlist_count} tickers tracked
{alert_count_today} alerts fired in last 24h
States: {state_distribution}


▎BIGGEST CHANGE

{biggest_change_block}


▎WEEK AHEAD ON YOUR WATCHLIST

{week_ahead_calendar}


▎ALL WATCHLIST ITEMS

{watchlist_table}


▎SECTOR CONTEXT

{sector_context_paragraph}


─────────────────────────
Manage:
  Watchlist → {manage_url}
  Notification mode → {mode_url}  (currently: {current_mode})
  Quiet hours → {quiet_hours_url}
─────────────────────────

Methodology: {methodology_url}
Not financial advice.
"""


@dataclass(frozen=True)
class TickerStatus:
    ticker: str
    state: SentinelState
    volume_relative: float
    days_in_calm: int
    short_note: str


def render_watchlist_table(items: Iterable[TickerStatus]) -> str:
    """Mono-spaced per-ticker line list plus an optional removal nudge.

    Spec layout intentionally omits any 'score' / 'rating' column.
    """
    rows = list(items)
    lines: list[str] = [
        "Ticker  State        Vol×    Note",
        "──────  ───────────  ─────   ────────────────────",
    ]
    for t in rows:
        d = STATE_DISPLAY[t.state]
        state_cell = f"{d['emoji']} {d['label']:<8}"
        vol_cell = f"{t.volume_relative:.1f}x"
        note = t.short_note or "—"
        lines.append(f"{t.ticker:<6}  {state_cell}  {vol_cell:>5}   {note}")

    quiet = [t for t in rows if t.days_in_calm >= 14]
    if quiet:
        lines.append("")
        lines.append(
            f"💡 {', '.join(t.ticker for t in quiet)} have been Calm for 14+ days."
        )
        lines.append(
            "   Consider removing if you don't have an active thesis."
        )

    return "\n".join(lines)


@dataclass(frozen=True)
class ProEmailDailyPayload:
    subject_dynamic: str
    preview_dynamic: str
    date_long: str
    delivery_time_et: str
    watchlist_count: int
    alert_count_today: int
    state_distribution: str
    biggest_change_block: str
    week_ahead_calendar: str
    watchlist_table: str
    sector_context_paragraph: str
    manage_url: str
    mode_url: str
    current_mode: str
    quiet_hours_url: str
    methodology_url: str


def render_email(p: ProEmailDailyPayload) -> str:
    return TEMPLATE.format(
        subject_dynamic=p.subject_dynamic,
        preview_dynamic=p.preview_dynamic,
        date_long=p.date_long,
        delivery_time_et=p.delivery_time_et,
        watchlist_count=p.watchlist_count,
        alert_count_today=p.alert_count_today,
        state_distribution=p.state_distribution,
        biggest_change_block=p.biggest_change_block,
        week_ahead_calendar=p.week_ahead_calendar,
        watchlist_table=p.watchlist_table,
        sector_context_paragraph=p.sector_context_paragraph,
        manage_url=p.manage_url,
        mode_url=p.mode_url,
        current_mode=p.current_mode,
        quiet_hours_url=p.quiet_hours_url,
        methodology_url=p.methodology_url,
    )
