"""X single-post templates — 3 variants for the once-or-twice-daily slot.

Strict rule: NEVER generate a thread. Every X post is a single tweet,
complete in isolation. The HONEST_LOG and TODAY_NOTHING templates are
deliberately blunt — they sell trust, not signal.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..state import STATE_DISPLAY, SentinelState


TEMPLATE_ANOMALY_HOOK = """\
${ticker} {action_verb} {price_change_pct:+.1f}% {session_label}.

The number worth noticing isn't price — it's {anomaly_dimension}.
{anomaly_value}.

{narrative_tension_line}

That gap is where retail usually misses risk.

Full breakdown ↓
{cta_url}

Not financial advice.
"""

TEMPLATE_HONEST_LOG = """\
{days_ago} days ago we flagged ${ticker} as {state_label}.

State then: {prev_state_label}
State now:  {curr_state_label}
Stock move: {price_move_pct:+.1f}%

We don't predict direction.
We flag when {flag_dimension}.
{outcome_one_liner}

Position sizing > direction.
"""

TEMPLATE_TODAY_NOTHING = """\
Sentinel scanned ~{universe_size} stocks today.

Nothing unusual.

Most "must-read alerts" you see today
are noise dressed as signal.

We'll be back tomorrow if there's something real.

Not financial advice.
"""


@dataclass(frozen=True)
class AnomalyHookPayload:
    ticker: str
    action_verb: str
    price_change_pct: float
    session_label: str
    anomaly_dimension: str
    anomaly_value: str
    narrative_tension_line: str
    cta_url: str


@dataclass(frozen=True)
class HonestLogPayload:
    days_ago: int
    ticker: str
    state_label: str
    prev_state: SentinelState
    curr_state: SentinelState
    price_move_pct: float
    flag_dimension: str
    outcome_one_liner: str


@dataclass(frozen=True)
class TodayNothingPayload:
    universe_size: int


def render_anomaly_hook(p: AnomalyHookPayload) -> str:
    return TEMPLATE_ANOMALY_HOOK.format(
        ticker=p.ticker.upper(),
        action_verb=p.action_verb,
        price_change_pct=p.price_change_pct,
        session_label=p.session_label,
        anomaly_dimension=p.anomaly_dimension,
        anomaly_value=p.anomaly_value,
        narrative_tension_line=p.narrative_tension_line,
        cta_url=p.cta_url,
    )


def render_honest_log(p: HonestLogPayload) -> str:
    prev_d = STATE_DISPLAY[p.prev_state]
    curr_d = STATE_DISPLAY[p.curr_state]
    return TEMPLATE_HONEST_LOG.format(
        days_ago=p.days_ago,
        ticker=p.ticker.upper(),
        state_label=p.state_label,
        prev_state_label=prev_d["label"],
        curr_state_label=curr_d["label"],
        price_move_pct=p.price_move_pct,
        flag_dimension=p.flag_dimension,
        outcome_one_liner=p.outcome_one_liner,
    )


def render_today_nothing(p: TodayNothingPayload) -> str:
    return TEMPLATE_TODAY_NOTHING.format(universe_size=p.universe_size)
