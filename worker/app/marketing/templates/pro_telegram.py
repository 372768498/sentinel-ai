"""Pro Telegram alert: state change plus evidence context."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ..state import STATE_DISPLAY, SentinelState


TEMPLATE = """\
Sentinel Pro Alert
{timestamp_et} ET - for {user_first_name}

${ticker} state changed:
{prev_state_emoji} {prev_state_label} -> {new_state_emoji} {new_state_label}
({minutes_since_change} min ago)

Current: ${price} - {price_change_pct:+.1f}% {session_label}
Volume: {volume_relative:.1f}x avg

WHAT CHANGED IN THE LAST 24H

{change_bullets}

EVIDENCE BALANCE

Confirming:
{compass_top}

Pushing back:
{compass_bottom}

SENTINEL READ

{synthesis_paragraph}

{divergence_warning}

WHAT TO DO WITH THIS

- Check the evidence chain before reacting to price.
- Compare the move against peers and your original thesis.
- Adjust threshold only if this alert was too noisy or too late.

Quick actions:
  /why {ticker}      see full evidence chain
  /snooze {ticker} 2h
  /threshold {ticker}
  /share             generate share card

Full report -> {pro_report_url}

Not financial advice.
"""


@dataclass(frozen=True)
class CompassSignal:
    name: str
    strength: float


def render_compass(
    confirming: Iterable[CompassSignal],
    disagreeing: Iterable[CompassSignal],
    *,
    max_per_side: int = 3,
) -> tuple[str, str]:
    top = sorted(confirming, key=lambda s: -s.strength)[:max_per_side]
    bot = sorted(disagreeing, key=lambda s: -s.strength)[:max_per_side]
    top_lines = [
        f"  - {s.name}: {'● strong' if s.strength > 0.7 else '○ moderate'}"
        for s in top
    ]
    bot_lines = [
        f"  - {s.name}: {'● strong' if s.strength > 0.7 else '○ moderate'}"
        for s in bot
    ]
    return ("\n".join(top_lines), "\n".join(bot_lines))


def render_divergence_warning(divergence_score: float) -> str:
    if divergence_score < 0.5:
        return ""
    return (
        "Divergence detected.\n"
        "Multiple signals point one way while others push back.\n\n"
        "This is not a high-conviction setup. Position sizing matters more than direction here."
    )


@dataclass(frozen=True)
class ProAlertPayload:
    timestamp_et: str
    user_first_name: str
    ticker: str
    prev_state: SentinelState
    new_state: SentinelState
    minutes_since_change: int
    price: float
    price_change_pct: float
    session_label: str
    volume_relative: float
    change_bullets: str
    compass_top: str
    compass_bottom: str
    synthesis_paragraph: str
    divergence_warning: str
    pro_report_url: str


def render_alert(p: ProAlertPayload) -> str:
    prev_d = STATE_DISPLAY[p.prev_state]
    new_d = STATE_DISPLAY[p.new_state]
    return TEMPLATE.format(
        timestamp_et=p.timestamp_et,
        user_first_name=p.user_first_name,
        ticker=p.ticker.upper(),
        prev_state_emoji=prev_d["emoji"],
        prev_state_label=prev_d["label"],
        new_state_emoji=new_d["emoji"],
        new_state_label=new_d["label"],
        minutes_since_change=p.minutes_since_change,
        price=p.price,
        price_change_pct=p.price_change_pct,
        session_label=p.session_label,
        volume_relative=p.volume_relative,
        change_bullets=p.change_bullets,
        compass_top=p.compass_top,
        compass_bottom=p.compass_bottom,
        synthesis_paragraph=p.synthesis_paragraph,
        divergence_warning=p.divergence_warning,
        pro_report_url=p.pro_report_url,
    )
