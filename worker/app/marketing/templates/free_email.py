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
Subject: {subject_line}
Preview: {preview_line}

-------------------------
SENTINEL - DAILY RADAR
{date_long} - {timestamp_et} ET
-------------------------

TODAY'S WATCHLIST PRIORITY

Quiet. No confirmed public anomaly yet.
In plain English: nothing unusual reached the public radar.

{market_brief_section}

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
    market_brief_section: str = ""
    subject_line: str = "Sentinel AI 美股市场日报：市场复盘与明日观察"
    preview_line: str = "SPY · QQQ · IWM · VIX · 板块轮动 · 涨跌幅前10"


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
        subject_line=p.subject_line,
        preview_line=p.preview_line,
        date_long=p.date_long,
        timestamp_et=p.timestamp_et,
        scan_universe_size=p.scan_universe_size,
        seed_section=p.seed_section,
        pro_url=p.pro_url,
        market_brief_section=p.market_brief_section,
    )


def render_email_html(*, subject: str, preview: str, body_text: str) -> str:
    """Render a mobile-friendly HTML email while keeping text fallback separate."""
    blocks = _html_blocks(body_text)
    kpis = _kpi_strip_html(body_text)
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
          {kpis}
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
    if "\t" in line:
        return False
    if re.match(r"^[一二三四五六七八九十]+、", line):
        return True
    if _has_cjk(line):
        return False
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
    table_lines: list[str] = []

    def flush_bullets() -> None:
        nonlocal bullet_items
        if bullet_items:
            out.append(_bullet_list_html(bullet_items))
            bullet_items = []

    def flush_table() -> None:
        nonlocal table_lines
        if table_lines:
            out.append(_table_html(table_lines))
            table_lines = []

    for line in lines:
        if "\t" in line:
            flush_bullets()
            table_lines.append(line)
            continue
        flush_table()
        if line.startswith(("- ", "  - ", "• ")):
            bullet_items.append(_inline_html(_strip_bullet(line)))
            continue
        flush_bullets()
        if _is_cta_line(line):
            out.append(_cta_html(line))
            continue
        if _is_ticker_priority(line):
            out.append(_ticker_priority_html(line))
            continue
        if _is_label_line(line):
            out.append(_label_html(line))
            continue
        if line.startswith("🔒"):
            out.append(_locked_card_html(line))
            continue
        if section_kind == "watchlist" and ":" in line:
            out.append(_watchlist_row_html(line))
            continue
        out.append(
            '<p style="margin:0 0 11px;font-size:15px;line-height:1.62;color:#334155;">'
            f"{_inline_html(line)}</p>"
        )
    flush_table()
    flush_bullets()
    return "\n".join(out)


def _bullet_list_html(items: list[str]) -> str:
    lis = "".join(
        '<li style="margin:0 0 9px;font-size:15px;line-height:1.55;color:#334155;">'
        f"{item}</li>"
        for item in items
    )
    return f'<ul style="margin:0 0 12px;padding-left:20px;">{lis}</ul>'


def _table_html(lines: list[str]) -> str:
    rows = [[cell.strip() for cell in line.split("\t")] for line in lines]
    if not rows:
        return ""
    header, *body = rows
    if _is_stock_detail_table(header):
        return _stock_cards_html(header, body)
    head_cells = "".join(
        '<th style="padding:10px 11px;border-bottom:1px solid #cbd5e1;'
        'font-size:12px;line-height:1.35;text-align:left;color:#475569;'
        'font-weight:800;background:#f8fafc;white-space:nowrap;">'
        f"{_inline_html(cell)}</th>"
        for cell in header
    )
    body_rows = []
    for row_index, row in enumerate(body):
        row_bg = "#ffffff" if row_index % 2 == 0 else "#fbfdff"
        cells = "".join(
            f'<td style="{_table_cell_style(cell, col_index)}">'
            f"{_inline_html(cell)}</td>"
            for col_index, cell in enumerate(row)
        )
        body_rows.append(f'<tr style="background:{row_bg};">{cells}</tr>')
    return (
        '<div style="margin:10px 0 16px;overflow-x:auto;border:1px solid #e2e8f0;'
        'border-radius:10px;background:#ffffff;">'
        '<table role="presentation" cellspacing="0" cellpadding="0" '
        'style="width:100%;border-collapse:collapse;min-width:580px;">'
        f"<thead><tr>{head_cells}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody>"
        "</table></div>"
    )


def _is_stock_detail_table(header: list[str]) -> bool:
    keys = set(header)
    return {"股票", "中文解释", "涨跌"}.issubset(keys)


def _stock_cards_html(header: list[str], rows: list[list[str]]) -> str:
    index = {name: idx for idx, name in enumerate(header)}
    cards: list[str] = []
    for row in rows:
        ticker = _cell(row, index, "股票")
        desc = _cell(row, index, "中文解释")
        change = _cell(row, index, "涨跌")
        price = _cell(row, index, "价格")
        volume = _cell(row, index, "成交量")
        rank = _cell(row, index, "排名")
        rank_badge = (
            '<td style="width:30px;padding:0 10px 0 0;vertical-align:top;">'
            '<div style="width:28px;height:28px;border-radius:999px;background:#eef2ff;'
            'color:#3730a3;font-size:13px;line-height:28px;text-align:center;'
            'font-weight:850;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;">'
            f"{escape(rank)}</div></td>"
            if rank
            else ""
        )
        cards.append(
            '<div style="margin:0 0 10px;padding:13px 14px;border:1px solid #e2e8f0;'
            'border-radius:10px;background:#ffffff;">'
            '<table role="presentation" cellspacing="0" cellpadding="0" style="width:100%;border-collapse:collapse;">'
            f"<tr>{rank_badge}"
            '<td style="vertical-align:top;">'
            '<div style="font-size:18px;line-height:1.18;color:#0f172a;font-weight:900;'
            'font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;">'
            f"{escape(ticker)}</div>"
            '<div style="margin-top:5px;font-size:14px;line-height:1.38;color:#334155;'
            'font-weight:650;">'
            f"{_inline_html(desc)}</div>"
            "</td>"
            '<td style="width:96px;vertical-align:top;text-align:right;">'
            f'<div style="font-size:17px;line-height:1.2;font-weight:900;color:{_value_color(change)};'
            'font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;">'
            f"{escape(change)}</div>"
            '<div style="margin-top:7px;font-size:12px;line-height:1.35;color:#64748b;'
            'font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;">'
            f"${escape(price)} · {escape(volume)}</div>"
            "</td></tr></table></div>"
        )
    return (
        '<div style="margin:10px 0 16px;">'
        + "".join(cards)
        + "</div>"
    )


def _cell(row: list[str], index: dict[str, int], key: str) -> str:
    pos = index.get(key)
    if pos is None or pos >= len(row):
        return ""
    return row[pos]


def _table_cell_style(cell: str, col_index: int) -> str:
    align = "right" if _looks_numeric(cell) else "left"
    color = _value_color(cell)
    weight = "800" if col_index in (0, 1) else "500"
    family = (
        "ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"
        if _looks_numeric(cell) or col_index in (0, 2)
        else "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif"
    )
    return (
        "padding:10px 11px;border-bottom:1px solid #edf2f7;"
        f"font-size:13px;line-height:1.35;color:{color};vertical-align:top;"
        f"text-align:{align};font-weight:{weight};font-family:{family};"
        "white-space:nowrap;"
    )


def _kpi_strip_html(body_text: str) -> str:
    rows = _market_overview_rows(body_text)
    if not rows:
        return ""
    wanted = ("SPY", "QQQ", "IWM", "VIX")
    cards: list[str] = []
    for ticker in wanted:
        row = rows.get(ticker)
        if row is None:
            continue
        label, desc, value, change = row
        cards.append(
            '<td style="width:25%;padding:0 6px 12px 0;vertical-align:top;">'
            '<div style="border:1px solid #dbe5f1;border-radius:10px;background:#ffffff;'
            'padding:13px 14px;min-height:94px;">'
            '<div style="font-size:11px;line-height:1.25;letter-spacing:.08em;'
            'text-transform:uppercase;color:#64748b;font-weight:800;">'
            f"{escape(label)}</div>"
            '<div style="margin-top:8px;font-size:24px;line-height:1;'
            'font-weight:850;color:#0f172a;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;">'
            f"{escape(value)}</div>"
            f'<div style="margin-top:7px;font-size:13px;line-height:1.2;font-weight:800;color:{_value_color(change)};">'
            f"{escape(change)}</div>"
            '<div style="margin-top:7px;font-size:11px;line-height:1.35;color:#64748b;">'
            f"{escape(_short_kpi_desc(desc))}</div>"
            "</div></td>"
        )
    if not cards:
        return ""
    return (
        '<table role="presentation" cellspacing="0" cellpadding="0" '
        'style="width:100%;border-collapse:collapse;margin:18px 0 8px;">'
        f"<tr>{''.join(cards)}</tr></table>"
    )


def _market_overview_rows(body_text: str) -> dict[str, tuple[str, str, str, str]]:
    rows: dict[str, tuple[str, str, str, str]] = {}
    for raw in body_text.splitlines():
        parts = [p.strip() for p in raw.split("\t")]
        if len(parts) != 4:
            continue
        label, desc, value, change = parts
        if label in {"SPY", "QQQ", "DIA", "IWM", "VIX", "10Y Yield"}:
            rows[label] = (label, desc, value, change)
    return rows


def _short_kpi_desc(desc: str) -> str:
    if "大盘" in desc:
        return "美国大盘"
    if "科技" in desc:
        return "大型科技股"
    if "小盘" in desc:
        return "小盘股"
    if "波动" in desc or "恐慌" in desc:
        return "波动预期"
    return desc[:14]


def _locked_card_html(line: str) -> str:
    text = line.lstrip("🔒").strip()
    return (
        '<div style="margin:18px 0;padding:18px 18px 17px;border:1px solid #f0be4e;'
        'border-radius:12px;background:#fff7df;">'
        '<div style="font-size:12px;line-height:1.3;letter-spacing:.12em;'
        'text-transform:uppercase;color:#9a6700;font-weight:900;">Pro unlock / Pro 可见</div>'
        '<div style="margin-top:8px;font-size:18px;line-height:1.25;color:#2f2305;'
        'font-weight:900;">完整异动归因 · 新闻源 · 成交量验证 · 实时推送</div>'
        '<p style="margin:9px 0 13px;font-size:14px;line-height:1.55;color:#4b3b10;">'
        f"{_inline_html(text)}</p>"
        '<a href="https://sentinelai.com/pro" '
        'style="display:inline-block;background:#0f172a;color:#ffffff;text-decoration:none;'
        'border-radius:8px;padding:11px 14px;font-size:14px;line-height:1.2;font-weight:850;">'
        'Try Pro Watch / 查看 Pro</a>'
        "</div>"
    )


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


def _looks_numeric(text: str) -> bool:
    return bool(re.fullmatch(r"[-+]?\d+(?:\.\d+)?%?|[-+]?\d+\s*bp|\d+(?:\.\d+)?[MK]?", text.strip()))


def _value_color(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("+"):
        return "#15803d"
    if stripped.startswith("-"):
        return "#b91c1c"
    return "#334155"


def _has_cjk(text: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", text))


def _section_kind(title: str) -> str:
    title_upper = title.upper()
    if "涨幅" in title or "跌幅" in title or "总览" in title or "强弱榜" in title:
        return "why"
    if "今日盯防" in title or "明早" in title:
        return "next"
    if "一句话总结" in title:
        return "reflection"
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
