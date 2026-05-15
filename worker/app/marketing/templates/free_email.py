"""Free Email Daily Radar: anomaly digest or quiet-market context."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ..state import STATE_DISPLAY, SentinelState


TEMPLATE_ANOMALY = """\
Subject: {subject_line}
Preview: {preview_line}

-------------------------
SENTINEL - DAILY RADAR
{date_long} - {timestamp_et} ET
-------------------------

TODAY'S WATCHLIST PRIORITY

{state_emoji} ${ticker} - ${price} - {price_change_pct:+.1f}% {session_label}

Bottom line:
Something changed enough for Sentinel to move this ticker to the top of today's watchlist.
This is not a trade call. It is a reason to slow down, check the evidence, and decide whether
the move changes your thesis.

WHY SENTINEL FLAGGED IT

{setup_bullets}

What it means:
{matters_paragraph}

Evidence balance:
- Confirming signals: {confirming_count}
- Signals pushing back: {disagreeing_count}
- Source set: {source_links_list}

WHAT TO IGNORE FOR NOW

Do not react to the headline alone. The useful question is whether price, volume,
filings/news, and attention are moving together or disagreeing.

YOU'LL HEAR FROM SENTINEL IF

- The move widens materially during the session.
- A filing, earnings item, or news catalyst changes the evidence.
- Watchlist context flips from noisy to actionable.

[ Open stock context preview -> {cta_url} ]


{seed_section}


ONE QUESTION TO ASK YOURSELF

{reflection_question}


-------------------------
Want this for YOUR tickers?
Pro watches your actual list, not just the public radar.

[ Try Pro Watch - 7-day trial, no card -> {pro_url} ]
-------------------------

Context, not financial advice.
Reply to this email - a real person reads them.

Methodology + sources: {methodology_url}
Unsubscribe: {unsubscribe_url}
"""

TEMPLATE_NOTHING = """\
Subject: Today: nothing unusual, but not empty
Preview: No confirmed anomaly yet. Here is what Sentinel watched and what would change the state.

-------------------------
SENTINEL - DAILY RADAR
{date_long} - {timestamp_et} ET
-------------------------

TODAY'S WATCHLIST PRIORITY

Quiet. No confirmed public anomaly yet.
In plain English: nothing unusual reached the public radar.

We scanned ~{scan_universe_size} U.S.-listed equities
across price, volume, SEC filings, news, and social chatter.
Everything stayed inside Sentinel's public alert threshold.

WHY NO ALERT YET

- No single ticker had enough cross-signal confirmation.
- Price action without a catalyst stayed classified as noise.
- Chatter without matching volume or filing/news evidence did not qualify.

WHAT TO WATCH NEXT

- A sharp volume break with a matching catalyst.
- SEC filing, earnings revision, analyst action, or policy headline.
- A watchlist ticker moving differently from its peers.

{seed_section}

Sentinel is quiet because the evidence is quiet. You will hear when that changes.

-------------------------
Want alerts only when YOUR tickers move?
[ Try Pro Watch -> {pro_url} ]
-------------------------

Context, not financial advice.
Reply to this email anytime.
"""


REFLECTION_QUESTIONS: tuple[str, ...] = (
    "If you own this ticker: would your position size still feel right "
    "if the narrative reverses by Friday?",
    "If you don't own it: are you watching it because of fundamentals, "
    "or because everyone else is talking about it?",
    "When was the last time you checked the actual 10-Q, "
    "not just the price chart?",
    "What would have to be true for you to be wrong about this name? "
    "Can you write it in one sentence?",
    "Is this in your watchlist because it's on your watchlist, "
    "or because you have a thesis?",
)


@dataclass(frozen=True)
class SeedTicker:
    ticker: str
    state: SentinelState
    one_liner: str


def render_seed_section(seeds: Iterable[SeedTicker]) -> str:
    """Render the user-specific watchlist floor."""
    items = list(seeds)
    if not items:
        return ""
    lines = []
    for s in items:
        display = STATE_DISPLAY[s.state]
        lines.append(f"  {s.ticker}: {display['emoji']} {display['label']} - {s.one_liner}")
    return (
        "-------------------------\n"
        "YOUR WATCHLIST PRIORITY\n\n"
        + "\n".join(lines)
        + "\n\nThis is your user-specific floor: even calm tickers were checked.\n"
        + "Want real-time alerts on these, plus 12 more tickers?\n"
        + "[ Try Pro Watch - 7-day trial -> ]\n"
        + "-------------------------"
    )


def pick_reflection_question(*, day_offset: int) -> str:
    """Deterministic rotation so daily emails feel less repetitive."""
    return REFLECTION_QUESTIONS[day_offset % len(REFLECTION_QUESTIONS)]


@dataclass(frozen=True)
class AnomalyEmailPayload:
    subject_line: str
    preview_line: str
    date_long: str
    timestamp_et: str
    state: SentinelState
    ticker: str
    price: float
    price_change_pct: float
    session_label: str
    setup_bullets: str
    matters_paragraph: str
    confirming_count: int
    disagreeing_count: int
    source_links_list: str
    cta_url: str
    seed_section: str
    reflection_question: str
    pro_url: str
    methodology_url: str
    unsubscribe_url: str


@dataclass(frozen=True)
class NothingEmailPayload:
    date_long: str
    timestamp_et: str
    scan_universe_size: int
    seed_section: str
    pro_url: str


def render_anomaly_email(p: AnomalyEmailPayload) -> str:
    display = STATE_DISPLAY[p.state]
    return TEMPLATE_ANOMALY.format(
        subject_line=p.subject_line,
        preview_line=p.preview_line,
        date_long=p.date_long,
        timestamp_et=p.timestamp_et,
        state_emoji=display["emoji"],
        ticker=p.ticker.upper(),
        price=p.price,
        price_change_pct=p.price_change_pct,
        session_label=p.session_label,
        setup_bullets=p.setup_bullets,
        matters_paragraph=p.matters_paragraph,
        confirming_count=p.confirming_count,
        disagreeing_count=p.disagreeing_count,
        source_links_list=p.source_links_list,
        cta_url=p.cta_url,
        seed_section=p.seed_section,
        reflection_question=p.reflection_question,
        pro_url=p.pro_url,
        methodology_url=p.methodology_url,
        unsubscribe_url=p.unsubscribe_url,
    )


def render_nothing_email(p: NothingEmailPayload) -> str:
    return TEMPLATE_NOTHING.format(
        date_long=p.date_long,
        timestamp_et=p.timestamp_et,
        scan_universe_size=p.scan_universe_size,
        seed_section=p.seed_section,
        pro_url=p.pro_url,
    )
