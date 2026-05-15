"""Pro Email Daily Intelligence Report."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


TEMPLATE = """\
Subject: {subject_line}
Preview: {preview_line}

-------------------------
SENTINEL PRO - DAILY INTELLIGENCE
{date_long} - {delivery_time_et} ET
-------------------------

EXECUTIVE READ

Your watchlist today: {watchlist_tickers_line}

Highest attention: ${top_ticker}
${top_ticker} - ${top_price} - {top_change_pct:+.1f}% {top_session}
Volume: {top_relative_volume:.1f}x avg - prev close ${top_prev_close}
Sentinel score: {top_score_line}

The useful read:
This is the ticker most worth checking first today. Sentinel is not saying buy or sell.
It is telling you where the evidence changed enough to deserve attention.

WHY IT'S MOVING

{narrative_block}

10-DIMENSION SNAPSHOT

{dim_snapshot_block}

PEER AND SECTOR CHECK

{peer_check_block}

WATCHLIST AT A GLANCE

{watchlist_summary_table}

WHAT TO IGNORE FOR NOW

- A price move without volume or catalyst confirmation.
- A social headline that does not match filings, earnings, or peer behavior.
- One-day noise that does not change your original thesis.

YOU'LL HEAR FROM SENTINEL IF

- A watchlist ticker crosses your threshold.
- The evidence balance flips materially.
- A filing, earnings item, or macro headline affects your names.

-------------------------
Open stock context for ${top_ticker}: {top_report_url}
Manage watchlist: {manage_url}
Methodology: {methodology_url}

Context, not financial advice.
"""


@dataclass(frozen=True)
class DimensionRow:
    label: str
    score_10: float
    highlight: str


@dataclass(frozen=True)
class WatchlistMover:
    ticker: str
    state_emoji: str
    change_pct: float
    score_100: Optional[int]
    rating: Optional[str]
    score_change: Optional[int]


@dataclass(frozen=True)
class ProEmailDailyPayload:
    subject_line: str
    preview_line: str
    date_long: str
    delivery_time_et: str
    watchlist_tickers_line: str

    top_ticker: str
    top_price: float
    top_change_pct: float
    top_session: str
    top_relative_volume: float
    top_prev_close: float

    top_score: Optional[int]
    top_rating: Optional[str]
    top_score_change: Optional[int]

    why_moving: Optional[str]
    risk_flag: Optional[str]

    dimensions: list[DimensionRow] = field(default_factory=list)
    peer_tickers: list[str] = field(default_factory=list)
    peer_check_lines: list[str] = field(default_factory=list)
    watchlist_movers: list[WatchlistMover] = field(default_factory=list)

    top_report_url: str = ""
    manage_url: str = ""
    methodology_url: str = ""


def _render_score_line(score: Optional[int], rating: Optional[str],
                       delta: Optional[int]) -> str:
    if score is None:
        return "not yet computed (post-close run pending)"
    line = f"{score}/100"
    if rating:
        line += f" - {rating}"
    if isinstance(delta, int):
        if delta > 0:
            line += f" (+{delta} vs prev)"
        elif delta < 0:
            line += f" ({delta} vs prev)"
        else:
            line += " (flat vs prev)"
    return line


def _render_narrative(why: Optional[str], risk: Optional[str]) -> str:
    bits: list[str] = []
    if why and why.strip():
        bits.append("Why it's moving:")
        bits.append(why.strip())
    if risk and risk.strip():
        if bits:
            bits.append("")
        bits.append("Risk flag:")
        bits.append(risk.strip())
    if not bits:
        return "(narrative not yet generated - back-fill on next post-close)"
    return "\n".join(bits)


def _render_dim_snapshot(dims: list[DimensionRow]) -> str:
    if not dims:
        return "(components not yet computed)"

    lines: list[str] = []
    width = 10
    for d in dims:
        filled = max(0, min(width, round(d.score_10)))
        bar = "#" * filled + "." * (width - filled)
        label = f"{d.label:<19}"
        score = f"{d.score_10:>4.1f}"
        highlight = d.highlight or "-"
        lines.append(f"{label} [{bar}]  {score}  {highlight}")
    return "\n".join(lines)


def _render_peer_check(tickers: list[str], lines: list[str]) -> str:
    if not tickers and not lines:
        return "(peer data not available)"
    out: list[str] = []
    if tickers:
        out.append(f"Compared to: {' - '.join(tickers[:5])}")
    if lines:
        out.append("")
        for line in lines[:3]:
            out.append(f"- {line}")
    return "\n".join(out)


def _render_watchlist_summary(movers: list[WatchlistMover]) -> str:
    if not movers:
        return "(empty watchlist)"
    rows = [
        "Ticker  Move    Score  Rating       Score Change",
        "------  ------  -----  -----------  ------------",
    ]
    for m in movers:
        delta_str = f"{m.change_pct:+.2f}%"
        score_str = f"{m.score_100}" if m.score_100 is not None else "-"
        rating_str = (m.rating or "-")[:11]
        if isinstance(m.score_change, int):
            if m.score_change > 0:
                ch = f"+{m.score_change}"
            elif m.score_change < 0:
                ch = f"{m.score_change}"
            else:
                ch = "flat"
        else:
            ch = "-"
        rows.append(
            f"{m.ticker:<6}  {delta_str:>6}  {score_str:>5}  {rating_str:<11}  {ch}"
        )
    return "\n".join(rows)


def render_email(p: ProEmailDailyPayload) -> str:
    score_line = _render_score_line(p.top_score, p.top_rating, p.top_score_change)
    narrative_block = _render_narrative(p.why_moving, p.risk_flag)
    dim_snapshot_block = _render_dim_snapshot(p.dimensions)
    peer_check_block = _render_peer_check(p.peer_tickers, p.peer_check_lines)
    watchlist_summary_table = _render_watchlist_summary(p.watchlist_movers)

    return TEMPLATE.format(
        subject_line=p.subject_line,
        preview_line=p.preview_line,
        date_long=p.date_long,
        delivery_time_et=p.delivery_time_et,
        watchlist_tickers_line=p.watchlist_tickers_line,
        top_ticker=p.top_ticker,
        top_price=f"{p.top_price:.2f}",
        top_change_pct=p.top_change_pct,
        top_session=p.top_session,
        top_relative_volume=p.top_relative_volume,
        top_prev_close=f"{p.top_prev_close:.2f}",
        top_score_line=score_line,
        narrative_block=narrative_block,
        dim_snapshot_block=dim_snapshot_block,
        peer_check_block=peer_check_block,
        watchlist_summary_table=watchlist_summary_table,
        top_report_url=p.top_report_url or "https://sentinelai.com",
        manage_url=p.manage_url or "https://sentinelai.com/account",
        methodology_url=p.methodology_url or "https://sentinelai.com/methodology",
    )
