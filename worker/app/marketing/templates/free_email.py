"""Free Email Daily Radar: anomaly digest or quiet-market context."""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
import re
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


def render_email_html(*, subject: str, preview: str, body_text: str) -> str:
    """Render a mobile-friendly HTML email while keeping text fallback separate."""
    blocks = _html_blocks(body_text)
    return f"""\
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{escape(subject)}</title>
  </head>
  <body style="margin:0;background:#eef2f7;color:#172033;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;">
    <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">
      {escape(preview)}
    </div>
    <main style="max-width:720px;margin:0 auto;padding:30px 14px;">
      <section style="background:#ffffff;border:1px solid #dfe5ee;border-radius:12px;overflow:hidden;box-shadow:0 18px 44px rgba(23,32,51,.09);">
        <div style="padding:26px 26px 22px;background:#0b1220;color:#ffffff;">
          <div style="font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:#9fb1cc;font-weight:700;">Sentinel AI · Daily Radar</div>
          <h1 style="margin:12px 0 10px;font-size:28px;line-height:1.18;font-weight:800;letter-spacing:0;">{escape(subject)}</h1>
          <p style="margin:0;color:#d9e2ef;font-size:16px;line-height:1.55;">{escape(preview)}</p>
          <div style="margin-top:18px;height:4px;width:86px;background:#38bdf8;border-radius:999px;"></div>
        </div>
        <div style="padding:10px 26px 24px;">
          {blocks}
        </div>
      </section>
      <p style="margin:16px 4px 0;color:#607089;font-size:12px;line-height:1.5;">
        Context, not financial advice. You are receiving this because you joined Sentinel AI updates.
      </p>
    </main>
  </body>
</html>
"""


def _html_blocks(body_text: str) -> str:
    sections: list[str] = []
    current_title = ""
    current_lines: list[str] = []
    for raw in body_text.splitlines():
        line = raw.strip()
        if not line or set(line) <= {"-"}:
            continue
        if _is_heading(line):
            if current_title or current_lines:
                sections.append(_section_html(current_title, current_lines))
            current_title = line.title()
            current_lines = []
        else:
            current_lines.append(line)
    if current_title or current_lines:
        sections.append(_section_html(current_title, current_lines))
    return "\n".join(sections)


def _is_heading(line: str) -> bool:
    if len(line) > 42:
        return False
    letters = [c for c in line if c.isalpha()]
    return bool(letters) and line.upper() == line and not line.startswith("[")


def _section_html(title: str, lines: list[str]) -> str:
    section_kind = _section_kind(title)
    title_html = (
        f'<h2 style="margin:0 0 14px;font-size:14px;line-height:1.3;'
        f'letter-spacing:.08em;text-transform:uppercase;color:{_title_color(section_kind)};'
        f'font-weight:800;">{escape(title)}</h2>'
        if title
        else ""
    )
    body = _lines_html(lines, section_kind=section_kind)
    return (
        f'<section style="{_section_style(section_kind)}">'
        f"{title_html}{body}</section>"
    )


def _lines_html(lines: list[str], *, section_kind: str) -> str:
    out: list[str] = []
    bullet_items: list[str] = []
    for line in lines:
        if line.startswith(("- ", "  - ", "• ")):
            bullet_items.append(_inline_html(_strip_bullet(line)))
            continue
        if bullet_items:
            out.append(_bullet_list_html(bullet_items))
            bullet_items = []
        if _is_cta_line(line):
            out.append(_cta_html(line))
            continue
        if _is_ticker_priority(line):
            out.append(_ticker_priority_html(line))
            continue
        if _is_label_line(line):
            out.append(_label_html(line))
            continue
        if section_kind == "watchlist" and ":" in line:
            out.append(_watchlist_row_html(line))
            continue
        out.append(
            '<p style="margin:0 0 11px;font-size:15px;line-height:1.62;color:#334155;">'
            f"{_inline_html(line)}</p>"
        )
    if bullet_items:
        out.append(_bullet_list_html(bullet_items))
    return "\n".join(out)


def _bullet_list_html(items: list[str]) -> str:
    lis = "".join(
        '<li style="margin:0 0 9px;font-size:15px;line-height:1.55;color:#334155;">'
        f"{item}</li>"
        for item in items
    )
    return f'<ul style="margin:0 0 12px;padding-left:20px;">{lis}</ul>'


def _inline_html(text: str) -> str:
    link_match = re.fullmatch(r"\[\s*(.+?)\s*->\s*(https?://[^\]\s]+)\s*\]", text)
    if link_match:
        label, url = link_match.groups()
        return _button_link_html(label, url)
    escaped = escape(text)
    escaped = re.sub(
        r"(https?://[^\s<]+)",
        lambda m: (
            f'<a href="{escape(m.group(1), quote=True)}" '
            f'style="color:#0369a1;text-decoration:underline;font-weight:600;">{escape(m.group(1))}</a>'
        ),
        escaped,
    )
    return escaped


def _section_kind(title: str) -> str:
    title_upper = title.upper()
    if "YOUR WATCHLIST" in title_upper:
        return "watchlist"
    if "PRIORITY" in title_upper:
        return "priority"
    if "WHY" in title_upper:
        return "why"
    if "IGNORE" in title_upper:
        return "ignore"
    if "HEAR FROM SENTINEL" in title_upper or "WATCH NEXT" in title_upper:
        return "next"
    if "QUESTION" in title_upper:
        return "reflection"
    if "WANT" in title_upper:
        return "cta"
    return "default"


def _section_style(kind: str) -> str:
    if kind == "priority":
        return (
            "margin:16px 0;padding:18px 18px 16px;border:1px solid #cbd5e1;"
            "border-radius:10px;background:#f8fafc;"
        )
    if kind in {"why", "next"}:
        return (
            "margin:14px 0;padding:18px 18px 14px;border:1px solid #dbeafe;"
            "border-radius:10px;background:#f8fbff;"
        )
    if kind == "ignore":
        return (
            "margin:14px 0;padding:18px 18px 14px;border:1px solid #fed7aa;"
            "border-radius:10px;background:#fffaf5;"
        )
    if kind == "reflection":
        return (
            "margin:14px 0;padding:18px 18px 14px;border:1px solid #ddd6fe;"
            "border-radius:10px;background:#fbf9ff;"
        )
    if kind == "cta":
        return (
            "margin:16px 0 8px;padding:20px 18px 16px;border:1px solid #bae6fd;"
            "border-radius:10px;background:#f0f9ff;"
        )
    return "padding:18px 0 14px;border-bottom:1px solid #edf2f7;"


def _title_color(kind: str) -> str:
    if kind == "ignore":
        return "#c2410c"
    if kind == "reflection":
        return "#6d28d9"
    if kind == "cta":
        return "#0369a1"
    if kind in {"why", "next"}:
        return "#1d4ed8"
    return "#0f172a"


def _strip_bullet(line: str) -> str:
    return line.strip().lstrip("-•").strip()


def _is_cta_line(line: str) -> bool:
    return bool(re.fullmatch(r"\[\s*.+?\s*->\s*https?://[^\]\s]+\s*\]", line))


def _cta_html(line: str) -> str:
    return (
        '<div style="margin:16px 0 8px;">'
        f"{_inline_html(line)}"
        "</div>"
    )


def _button_link_html(label: str, url: str) -> str:
    return (
        f'<a href="{escape(url, quote=True)}" '
        'style="display:inline-block;background:#0b1220;color:#ffffff;'
        'text-decoration:none;border-radius:8px;padding:12px 16px;'
        'font-size:14px;line-height:1.2;font-weight:800;">'
        f"{escape(label)}</a>"
    )


def _is_ticker_priority(line: str) -> bool:
    return bool(re.search(r"\$[A-Z]{1,6}.*[-+]\d+(?:\.\d+)?%", line))


def _ticker_priority_html(line: str) -> str:
    return (
        '<div style="margin:0 0 14px;padding:16px;border-radius:10px;'
        'background:#0f172a;color:#ffffff;">'
        '<div style="font-size:17px;line-height:1.45;font-weight:800;">'
        f"{_inline_html(line)}</div>"
        "</div>"
    )


def _is_label_line(line: str) -> bool:
    labels = (
        "Bottom line:",
        "What it means:",
        "Evidence balance:",
    )
    return line in labels


def _label_html(line: str) -> str:
    return (
        '<p style="margin:14px 0 7px;font-size:13px;line-height:1.35;'
        'letter-spacing:.06em;text-transform:uppercase;color:#64748b;font-weight:800;">'
        f"{escape(line.rstrip(':'))}</p>"
    )


def _watchlist_row_html(line: str) -> str:
    ticker, detail = line.split(":", 1)
    return (
        '<div style="margin:0 0 10px;padding:12px 14px;border:1px solid #e2e8f0;'
        'border-radius:9px;background:#ffffff;">'
        '<span style="display:inline-block;min-width:58px;font-size:14px;'
        'font-weight:800;color:#0f172a;">'
        f"{escape(ticker.strip())}</span>"
        '<span style="font-size:14px;line-height:1.5;color:#334155;">'
        f"{_inline_html(detail.strip())}</span>"
        "</div>"
    )
