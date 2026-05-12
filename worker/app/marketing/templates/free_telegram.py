"""Free Telegram channel template — at most ONE post per day.

Two branches:
  - ANOMALY: a single ticker qualified (state HEATED or INFLECTION +
    uniqueness >= 0.6). The most anomalous one wins.
  - NOTHING: no qualified anomaly. We publish the "nothing unusual"
    post anyway — silence is not free, but manufactured signals are
    worse. This is a product position, not a fallback.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..state import STATE_DISPLAY, SentinelState

TEMPLATE_ANOMALY = """\
🛰 Sentinel · Anomaly Watch
{session_label} · {timestamp_et} ET

{state_emoji} ${ticker} · ${price}
{session_change_label}: {price_change_pct:+.1f}%
Volume: {volume_relative:.1f}x avg

Why it's anomalous:
{anomaly_one_liner}

{uniqueness_line}

Signals confirming: {confirming_list}
Signals disagreeing: {disagreeing_list}

Sentinel's read:
{narrative_one_paragraph}

⚠ {risk_one_liner}

Sources: {source_categories}

Full breakdown → {cta_url}
Watch your own tickers → {pro_url}

Not financial advice.
"""

TEMPLATE_NOTHING = """\
🛰 Sentinel · Anomaly Watch
{session_label} · {timestamp_et} ET

Today: nothing unusual on radar.

We scanned ~{scan_universe_size} U.S.-listed equities
across price, volume, filings, news, and social.
All within normal range.

We don't manufacture signals.
See you tomorrow.

Not financial advice.
"""


@dataclass(frozen=True)
class AnomalyPayload:
    session_label: str
    timestamp_et: str
    state: SentinelState
    ticker: str
    price: float
    session_change_label: str
    price_change_pct: float
    volume_relative: float
    anomaly_one_liner: str
    uniqueness_line: str
    confirming_list: str
    disagreeing_list: str
    narrative_one_paragraph: str
    risk_one_liner: str
    source_categories: str
    cta_url: str
    pro_url: str


@dataclass(frozen=True)
class NothingPayload:
    session_label: str
    timestamp_et: str
    scan_universe_size: int


def render_anomaly(p: AnomalyPayload) -> str:
    display = STATE_DISPLAY[p.state]
    return TEMPLATE_ANOMALY.format(
        session_label=p.session_label,
        timestamp_et=p.timestamp_et,
        state_emoji=display["emoji"],
        ticker=p.ticker.upper(),
        price=p.price,
        session_change_label=p.session_change_label,
        price_change_pct=p.price_change_pct,
        volume_relative=p.volume_relative,
        anomaly_one_liner=p.anomaly_one_liner,
        uniqueness_line=p.uniqueness_line,
        confirming_list=p.confirming_list,
        disagreeing_list=p.disagreeing_list,
        narrative_one_paragraph=p.narrative_one_paragraph,
        risk_one_liner=p.risk_one_liner,
        source_categories=p.source_categories,
        cta_url=p.cta_url,
        pro_url=p.pro_url,
    )


def render_nothing(p: NothingPayload) -> str:
    return TEMPLATE_NOTHING.format(
        session_label=p.session_label,
        timestamp_et=p.timestamp_et,
        scan_universe_size=p.scan_universe_size,
    )
