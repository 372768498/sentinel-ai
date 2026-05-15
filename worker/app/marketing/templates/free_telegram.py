"""Free Telegram channel templates."""
from __future__ import annotations

from dataclasses import dataclass

from ..state import STATE_DISPLAY, SentinelState

TEMPLATE_ANOMALY = """\
🛰 Sentinel · Anomaly Watch
{session_label} - {timestamp_et} ET

TODAY'S PRIORITY

{state_emoji} ${ticker} - ${price}
{session_change_label}: {price_change_pct:+.1f}%
Volume: {volume_relative:.1f}x avg

Why it matters:
{anomaly_one_liner}

Evidence balance:
- Uniqueness: {uniqueness_line}
- Confirming: {confirming_list}
- Pushing back: {disagreeing_list}

Sentinel read:
{narrative_one_paragraph}

Risk flag:
{risk_one_liner}

Watch next:
- Follow-through with volume.
- A filing, earnings item, or news catalyst.
- Whether peers confirm or reject the move.

Sources: {source_categories}

Stock context preview -> {cta_url}
Watch your own tickers -> {pro_url}

Not financial advice.
"""

TEMPLATE_NOTHING = """\
🛰 Sentinel · Anomaly Watch
{session_label} - {timestamp_et} ET

Today: nothing unusual on radar.

We scanned ~{scan_universe_size} U.S.-listed equities
across price, volume, filings, news, and social.
Nothing reached Sentinel's public anomaly threshold.

Why no alert yet:
- No ticker had enough cross-signal confirmation.
- Price-only moves stayed classified as noise.
- Chatter without matching volume or catalyst did not qualify.

Watch next:
- A volume break with a catalyst.
- SEC filing, earnings, analyst, or macro headline.
- A watchlist ticker moving differently from its peers.

Sentinel is quiet because the evidence is quiet.
See you tomorrow when the evidence changes.

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
