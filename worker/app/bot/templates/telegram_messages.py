"""
All Telegram message templates for Sentinel AI bot.
Parse mode: HTML throughout.
Brand rules enforced:
  - Never imply buy/sell/price predictions
  - Always include "Context, not advice." or "Your call. Not advice."
  - Source links required for factual claims

All timestamps sent to users are in ET (America/New_York).
"""
from datetime import datetime
from enum import Enum
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")


class AlertPriority(str, Enum):
    """
    Alert priority tiers — drives notification behavior and (future) call escalation.

    NORMAL   = standard threshold crossing (default)
    URGENT   = >5% single-stock move, SEC investigation, earnings miss >10%
    CRITICAL = systemic events (Fed emergency, VIX spike >50%, halt/delist)
               → reserved should_call=True for future Twilio integration
    """
    NORMAL = "normal"
    URGENT = "urgent"
    CRITICAL = "critical"


# Event types that carry priority weight regardless of magnitude
_URGENT_EVENT_TYPES = {"sec_investigation", "earnings_miss_big"}
_CRITICAL_EVENT_TYPES = {"vix_spike", "fed_emergency", "halt", "delisting"}


def compute_priority(change_pct: float = 0.0, event_type: str = "threshold") -> AlertPriority:
    """Determine an alert's priority from magnitude + event semantics."""
    if event_type in _CRITICAL_EVENT_TYPES:
        return AlertPriority.CRITICAL
    if event_type in _URGENT_EVENT_TYPES or abs(change_pct) >= 5.0:
        return AlertPriority.URGENT
    return AlertPriority.NORMAL


def should_call_for(priority: AlertPriority) -> bool:
    """Reserved for future Twilio integration. Currently always False."""
    return priority == AlertPriority.CRITICAL


def _et_now_str() -> str:
    return datetime.now(_ET).strftime("%H:%M ET %b %d")


# ── Session anchoring ─────────────────────────────────────────────────────────
# Replaces a bare clock with a phase + countdown so the reader feels urgency
# without re-doing the math (e.g. "Final hour · 27m to close").

_PREMARKET_OPEN = (9, 30)   # ET — regular session start
_REGULAR_CLOSE = (16, 0)    # ET — regular session close
_AFTERHOURS_END = (20, 0)   # ET — extended hours close


def _minutes_between(a: tuple[int, int], b: tuple[int, int]) -> int:
    return (b[0] - a[0]) * 60 + (b[1] - a[1])


def _fmt_h_m(total_min: int) -> str:
    total_min = max(0, total_min)
    if total_min < 60:
        return f"{total_min}m"
    h, m = divmod(total_min, 60)
    return f"{h}h" if m == 0 else f"{h}h {m}m"


def session_anchor(now: datetime | None = None) -> str:
    """Return a phase + countdown anchor like "Final hour · 27m to close".

    Phases:
      - Pre-market · {N}m to open       (before 09:30 ET)
      - Open · first 30m                 (09:30–10:00 ET)
      - Intraday · {N}m to close         (10:00–15:00 ET)
      - Final hour · {N}m to close       (15:00–16:00 ET)
      - After hours · {N}m since close   (16:00–20:00 ET)
      - Overnight                        (20:00–next 08:00 ET)
      - Pre-market opening soon          (08:00–09:30 ET)
    """
    if now is None:
        now = datetime.now(_ET)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=_ET)
    else:
        now = now.astimezone(_ET)
    cur = (now.hour, now.minute)
    if cur < _PREMARKET_OPEN:
        if cur >= (8, 0):
            return f"Pre-market · {_fmt_h_m(_minutes_between(cur, _PREMARKET_OPEN))} to open"
        return "Overnight"
    if cur < (10, 0):
        mins_in = _minutes_between(_PREMARKET_OPEN, cur)
        return f"Open · {_fmt_h_m(mins_in)} in"
    if cur < (15, 0):
        return f"Intraday · {_fmt_h_m(_minutes_between(cur, _REGULAR_CLOSE))} to close"
    if cur < _REGULAR_CLOSE:
        return f"Final hour · {_fmt_h_m(_minutes_between(cur, _REGULAR_CLOSE))} to close"
    if cur < _AFTERHOURS_END:
        return f"After hours · {_fmt_h_m(_minutes_between(_REGULAR_CLOSE, cur))} since close"
    return "Overnight"


# ── Onboarding ────────────────────────────────────────────────────────────────

def welcome_group(first_name: str, bot_username: str, telegram_user_id: int) -> str:
    deep_link = f"https://t.me/{bot_username}?start=uid_{telegram_user_id}"
    return (
        f"👋 <b>Welcome, {first_name}.</b>\n\n"
        f"You're in Sentinel Pro. I watch your tickers — quietly, until something matters.\n\n"
        f"<b>One step to activate your alerts:</b>\n"
        f'<a href="{deep_link}">→ Click here to set up your watchlist</a>\n\n'
        f"<i>Takes 30 seconds. Everything happens in our private chat.</i>"
    )


ONBOARDING_STEP1 = (
    "👋 <b>You're in.</b>\n\n"
    "Welcome to Sentinel Pro. I'm your sentinel.\n\n"
    "Let's get you set up in 30 seconds.\n\n"
    "<b>Step 1 of 3 — your tickers</b>\n\n"
    "Send me the tickers you want me to watch.\n"
    "Just type them, separated by spaces or commas:\n\n"
    "<code>Example: NVDA AAPL TSLA MSFT GOOGL</code>"
)

ONBOARDING_STEP1_BUTTONS = [
    ("📋 Use sample (5 tickers)", "onb:tickers:sample"),
    ("❌ Cancel setup", "onb:cancel"),
]

SAMPLE_TICKERS = ["NVDA", "AAPL", "TSLA", "MSFT", "GOOGL"]


# ── Alert inline keyboards ────────────────────────────────────────────────────
# Builds Telegram inline_keyboard payloads. Returned dicts are serialised to
# JSON by the sender layer (telegram.send_channel_message / _default_sender).

DEFAULT_PUBLIC_URL = "https://sentinel.jilo.ai"


def _stock_url(ticker: str, *, base: str, utm_campaign: str) -> str:
    return (
        f"{base.rstrip('/')}/stocks/{ticker.upper()}"
        f"?utm_source=telegram&utm_medium=alert&utm_campaign={utm_campaign}"
    )


def _pro_checkout_url(base: str) -> str:
    return (
        f"{base.rstrip('/')}/pro"
        "?utm_source=telegram&utm_medium=alert&utm_campaign=upgrade_pro"
    )


def build_alert_keyboard(
    ticker: str,
    *,
    public_url: str = DEFAULT_PUBLIC_URL,
    is_pro: bool = False,
) -> dict:
    """Build a 2-row inline keyboard for a single-ticker alert.

    Free users see Open Deep View + Watch + Upgrade Pro.
    Pro users see Open Deep View + Snooze + Threshold.
    """
    upper = ticker.upper()
    deep_view = {
        "text": f"📊 Open {upper} Deep View",
        "url": _stock_url(upper, base=public_url, utm_campaign="alert_threshold"),
    }
    if is_pro:
        return {
            "inline_keyboard": [
                [deep_view],
                [
                    {"text": "🔕 Snooze 2h", "callback_data": f"alert:snooze:{upper}:2"},
                    {"text": "⚙️ Threshold", "callback_data": f"wl:threshold:{upper}"},
                ],
            ]
        }
    return {
        "inline_keyboard": [
            [deep_view],
            [
                {"text": "➕ Watch this", "callback_data": f"wl:add:{upper}"},
                {"text": "🔔 Upgrade Pro", "url": _pro_checkout_url(public_url)},
            ],
        ]
    }


def build_radar_keyboard(
    tickers: list[str],
    *,
    public_url: str = DEFAULT_PUBLIC_URL,
) -> dict:
    """Radar broadcast keyboard — first 3 tickers + a Pro upsell row."""
    rows: list[list[dict]] = []
    for ticker in tickers[:3]:
        upper = ticker.upper()
        rows.append([
            {
                "text": f"📊 ${upper} Deep View",
                "url": _stock_url(upper, base=public_url, utm_campaign="radar"),
            }
        ])
    rows.append([
        {"text": "🛰 Get YOUR ticker alerts (Pro)", "url": _pro_checkout_url(public_url)},
    ])
    return {"inline_keyboard": rows}


def onboarding_step2(tickers: list[str]) -> str:
    ticker_str = " · ".join(tickers)
    count = len(tickers)
    return (
        f"✓ Got {count} ticker{'s' if count != 1 else ''}:\n"
        f"<code>{ticker_str}</code>\n\n"
        "<b>Step 2 of 3 — alert threshold</b>\n\n"
        "I'll ping you when any of these moves more than a certain percent intraday.\n\n"
        "Default is <b>±2%</b>. Most users keep it."
    )


ONBOARDING_STEP2_BUTTONS = [
    ("✓ Use default ±2%", "onb:threshold:default"),
    ("⚙️ Customize", "onb:threshold:custom"),
    ("Skip", "onb:threshold:skip"),
    ("❌ Cancel setup", "onb:cancel"),
]

ONBOARDING_STEP2_CUSTOM_PROMPT = (
    "Enter your threshold percentage (e.g. <code>1.5</code> for ±1.5%):\n\n"
    "<i>Range: 0.5% – 10%. Send /cancel to exit setup.</i>"
)


def onboarding_step3(threshold: float) -> str:
    return (
        f"✓ Threshold set: <b>±{threshold:.1f}%</b>\n\n"
        "<b>Step 3 of 3 — quiet hours</b>\n\n"
        "Want me to mute alerts at night?\n"
        "<i>(Alerts queue up, you see them in the morning digest)</i>"
    )


ONBOARDING_STEP3_BUTTONS = [
    ("😴 Yes, 22:00–07:00 ET", "onb:quiet:default"),
    ("🌍 Custom hours", "onb:quiet:custom"),
    ("No, never mute", "onb:quiet:never"),
    ("❌ Cancel setup", "onb:cancel"),
]

ONBOARDING_STEP3_CUSTOM_PROMPT = (
    "Send your quiet hours in this format:\n\n"
    "<code>22 7</code>  ← mute from 22:00 to 07:00 ET\n\n"
    "<i>Use 24-hour format (ET). First number = start, second = end.\n"
    "Send /cancel to exit setup.</i>"
)


def onboarding_done(tickers: list[str], threshold: float, quiet_enabled: bool,
                    quiet_start: int, quiet_end: int) -> str:
    ticker_str = " · ".join(tickers)
    quiet_line = (
        f"{quiet_start:02d}:00–{quiet_end:02d}:00 ET"
        if quiet_enabled
        else "off"
    )
    return (
        "🎉 <b>You're all set.</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Watchlist: {len(tickers)} tickers\n"
        f"<code>{ticker_str}</code>\n"
        f"Threshold: ±{threshold:.1f}% intraday\n"
        f"Quiet hours: {quiet_line}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "I'm watching now. You'll hear from me only when it matters.\n\n"
        "Need to change anything? Send /watchlist.\n"
        "Have a question? Just type it."
    )


# ── Watchlist dashboard ───────────────────────────────────────────────────────

def watchlist_dashboard(rows: list[dict]) -> str:
    """
    rows: [{"ticker": "NVDA", "threshold": 2.0, "active": True}]
    """
    if not rows:
        return (
            "📋 <b>Your Watchlist</b>\n\n"
            "Empty — you have no tickers yet.\n\n"
            "Send me tickers to start: <code>NVDA AAPL TSLA</code>"
        )
    count = len(rows)
    lines = [f"📋 <b>Your Watchlist ({count} tickers)</b>\n"]
    for r in rows:
        status = "✓ active" if r["active"] else "😴 muted"
        lines.append(
            f"<code>{r['ticker']:<6}</code> · ±{r['threshold']:.1f}% · {status}"
        )
    return "\n".join(lines)


WATCHLIST_DASHBOARD_BUTTONS = [
    [("➕ Add ticker", "wl:add"), ("➖ Remove", "wl:remove:start")],
    [("⚙️ Edit threshold", "wl:threshold:edit"), ("🌍 Quiet hours", "wl:quiet:edit")],
]

WATCHLIST_EMPTY_HELP = (
    "Your watchlist is empty.\n\n"
    "Just send me tickers to start:\n"
    "<code>NVDA AAPL TSLA MSFT GOOGL</code>"
)

WATCHLIST_ADD_PROMPT = (
    "Send me the tickers to add:\n\n"
    "<code>Example: AMD COIN PLTR</code>"
)

WATCHLIST_REMOVE_PROMPT = (
    "Which ticker do you want to remove?\n"
    "Send its symbol: <code>TSLA</code>"
)

WATCHLIST_THRESHOLD_EDIT_PROMPT = (
    "Send the ticker and new threshold:\n\n"
    "<code>TSLA 3</code>  ← set TSLA to ±3%\n\n"
    "Or set all at once:\n"
    "<code>all 1.5</code>"
)

WATCHLIST_QUIET_EDIT_PROMPT = (
    "Send your quiet hours:\n\n"
    "<code>22 7</code>  ← mute 22:00–07:00 ET\n"
    "<code>off</code>  ← disable quiet hours"
)


def watchlist_replace_confirm(existing_count: int, new_tickers: list[str]) -> str:
    new_str = " · ".join(new_tickers)
    return (
        f"You already have {existing_count} tickers.\n\n"
        f"New tickers: <code>{new_str}</code>\n\n"
        "What would you like to do?"
    )


WATCHLIST_REPLACE_BUTTONS = [
    ("Yes, replace", "wl:replace:yes"),
    ("Add to existing", "wl:replace:append"),
    ("Cancel", "wl:replace:cancel"),
]


# ── 7 Alert templates ─────────────────────────────────────────────────────────

HELP_MESSAGE = (
    "🛡 <b>Sentinel — commands</b>\n\n"
    "/watchlist — view &amp; edit your tickers\n"
    "/threshold — adjust alert sensitivity\n"
    "/snooze — pause alerts temporarily\n"
    "/help — this message\n\n"
    "<b>Or just type naturally:</b>\n"
    "<code>What about TSLA?</code>\n"
    "<code>Why no alert on NVDA?</code>\n\n"
    "<i>I'm quiet until something matters. — Sentinel</i>"
)


def snooze_confirm(hours: int) -> str:
    return (
        f"😴 Alerts snoozed for {hours}h.\n\n"
        f"I'll resume watching at {hours}:00 ET.\n"
        "Send /snooze off to wake me early."
    )


SNOOZE_OFF_CONFIRM = "✓ Alerts resumed. I'm watching again."

INVALID_TICKERS_MSG = (
    "Couldn't find: <code>{invalid}</code>\n"
    "Check the ticker symbol and try again.\n\n"
    "Saved: {valid_count} ticker(s)."
)

TOO_MANY_TICKERS_MSG = (
    "That's more than 25 tickers — I'll watch the first 25.\n"
    "You can adjust anytime with /watchlist."
)

NO_TICKERS_FOUND_MSG = (
    "I didn't find any valid tickers in that message.\n\n"
    "Send them like: <code>NVDA AAPL TSLA</code>\n"
    "Or tap the button below to use a sample."
)


# ── Batch alert (3+ tickers crossing simultaneously) ─────────────────────────

# ---------------------------------------------------------------------------
# Value-dense push templates.
#
# Public radar, Pro daily brief, and alert surfaces keep their historical
# function signatures so jobs can publish without rewiring.
# ---------------------------------------------------------------------------

_PUBLIC_FOOTER = (
    "Sources: Yahoo Finance - SEC EDGAR - CNN F&amp;G\n"
    "Open stock context -> <a href=\"https://sentinel.jilo.ai\">sentinel.jilo.ai</a>\n\n"
    "<i>Context, not financial advice.</i>"
)

_PUBLIC_FOOTER_QUIET = (
    "Sentinel is quiet because the evidence is quiet. You'll hear when that changes.\n\n"
    "<i>Context, not financial advice.</i>"
)


def _score_line(m: dict) -> str | None:
    score = m.get("score_100")
    if score is None:
        return None
    rating = m.get("rating") or ""
    delta = m.get("score_change")
    line = f"Sentinel score {score}/100"
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


def _mover_block(m: dict) -> str:
    sign = "+" if m["change_pct"] > 0 else ""
    arrow = "UP" if m["change_pct"] > 0 else "DOWN"
    price = m.get("price")
    prev = m.get("prev_close")
    rel_vol = m.get("relative_volume")
    why = (m.get("why_moving") or "").strip()
    risk = (m.get("risk_flag") or "").strip()

    head = f"<b>{m['ticker']}</b> - {arrow} {sign}{m['change_pct']:.2f}%"
    if price is not None:
        head += f" - ${price:.2f}"

    lines = [head]
    details: list[str] = []
    if rel_vol is not None:
        details.append(f"Vol {rel_vol:.1f}x avg")
    if prev is not None:
        details.append(f"prev ${prev:.2f}")
    if details:
        lines.append("Context: " + " - ".join(details))

    score_part = _score_line(m)
    if score_part:
        lines.append(score_part)
    if why:
        lines.append(f"Why it matters: {why}")
    if risk:
        lines.append(f"Risk flag: {risk}")
    return "\n".join(lines)


def _radar_block(header: str, date_str: str, time_label: str, items: list[dict]) -> str:
    body = "\n\n".join(_mover_block(m) for m in items)
    return (
        f"<b>{header}</b>\n"
        f"<i>{date_str} - {time_label} ET</i>\n\n"
        "<b>Today's priority:</b>\n"
        f"{body}\n\n"
        "<b>What to watch next:</b>\n"
        "- Follow-through with volume, not just a headline.\n"
        "- New filing, earnings, analyst, or macro catalyst.\n"
        "- Whether the move spreads to peers or stays isolated.\n\n"
        f"{_PUBLIC_FOOTER}"
    )


def _quiet_floor_block(intro: str, bullets: list[str] | None) -> str:
    cleaned = [b.strip() for b in (bullets or []) if b.strip()]
    lines = [intro]
    lines.extend(f"• {bullet}" for bullet in cleaned)
    lines.extend([
        "",
        "<b>Why no alert yet:</b>",
        "- No watchlist move has enough cross-signal confirmation.",
        "- Price action without a catalyst is still classified as noise.",
        "",
        "<b>Sentinel will alert if:</b>",
        "- A ticker breaks threshold with confirming volume.",
        "- A filing, earnings item, or macro headline changes the evidence.",
    ])
    return "\n".join(lines)


def public_premarket_brief_quiet(date_str: str, bullets: list[str] | None = None) -> str:
    body = _quiet_floor_block("Watchlist quiet before the open - here is the market floor:", bullets)
    return (
        "<b>Sentinel AI - Pre-market Radar</b>\n"
        f"<i>{date_str} - 08:30 ET</i>\n\n"
        f"{body}\n\n"
        f"{_PUBLIC_FOOTER_QUIET}"
    )


def public_premarket_brief_active(date_str: str, items: list[dict]) -> str:
    return _radar_block("Sentinel AI - Pre-market Radar", date_str, "08:30", items)


def public_midday_brief_quiet(date_str: str, bullets: list[str] | None = None) -> str:
    body = _quiet_floor_block("Watchlist quiet at mid-day - here is the session floor:", bullets)
    return (
        "<b>Sentinel AI - Mid-day Radar</b>\n"
        f"<i>{date_str} - 12:30 ET</i>\n\n"
        f"{body}\n\n"
        f"{_PUBLIC_FOOTER_QUIET}"
    )


def public_midday_brief_active(date_str: str, items: list[dict]) -> str:
    return _radar_block("Sentinel AI - Mid-day Radar", date_str, "12:30", items)


def public_postclose_digest(
    date_str: str,
    movers: list[dict],
    notes: list[str] | None = None,
    quiet_bullets: list[str] | None = None,
) -> str:
    notes = notes or []
    if not movers and not notes:
        body = _quiet_floor_block("Quiet close - here is the floor for tomorrow:", quiet_bullets)
        return (
            "<b>Sentinel AI - Post-close Recap</b>\n"
            f"<i>{date_str} - 16:30 ET</i>\n\n"
            f"{body}\n\n"
            f"{_PUBLIC_FOOTER_QUIET}"
        )

    body_parts: list[str] = []
    if movers:
        body_parts.append("<b>What mattered:</b>\n" + "\n\n".join(_mover_block(m) for m in movers[:5]))
    if notes:
        notes_block = "\n".join(f"- {n}" for n in notes[:3])
        body_parts.append(f"<b>Tomorrow watch:</b>\n{notes_block}")

    return (
        "<b>Sentinel AI - Post-close Recap</b>\n"
        f"<i>{date_str} - 16:30 ET</i>\n\n"
        + "\n\n".join(body_parts)
        + f"\n\n{_PUBLIC_FOOTER}"
    )


def alert_threshold_crossed(
    ticker: str,
    change_pct: float,
    prev_price: float,
    last_price: float,
    session: str,
    source_url: str = "",
    *,
    score_100: int | None = None,
    rating: str | None = None,
    score_change: int | None = None,
    why_moving: str | None = None,
    risk_flag: str | None = None,
) -> str:
    direction = "up" if change_pct > 0 else "down"
    sign = "+" if change_pct > 0 else ""
    anchor = session_anchor()
    blocks = [
        f"<b>{ticker} crossed your threshold</b>",
        f"<i>{anchor}</i>",
        "",
        f"{ticker} moved {sign}{change_pct:.2f}% {direction} this {session.lower()}.",
        f"${prev_price:.2f} -> <b>${last_price:.2f}</b>",
    ]
    score_part = _score_line({
        "score_100": score_100,
        "rating": rating or "",
        "score_change": score_change,
    }) if score_100 is not None else None
    if score_part:
        blocks.extend(["", score_part])

    if why_moving and why_moving.strip():
        blocks.extend(["", f"<b>Why it matters:</b>\n{why_moving.strip()}"])
    if risk_flag and risk_flag.strip():
        blocks.extend(["", f"<b>Risk flag:</b>\n{risk_flag.strip()}"])
    blocks.extend([
        "",
        "<b>Watch next:</b>",
        "- Does the move hold with volume?",
        "- Is there a filing, earnings, or news catalyst behind it?",
    ])
    if source_url:
        blocks.extend(["", f'<a href="{source_url}">Source</a>'])
    blocks.extend(["", "<i>Your call. Not financial advice.</i>"])
    return "\n".join(blocks)


def alert_silence_day(tickers: list[str], date_str: str = "") -> str:
    ticker_str = " - ".join(tickers) if tickers else "your watchlist"
    date_str = date_str or datetime.now().strftime("%b %d")
    return (
        f"<b>Quiet day - {date_str}</b>\n\n"
        f"Watched: {ticker_str}\n\n"
        "No ticker crossed your threshold with enough confirmation.\n\n"
        "<b>Why that matters:</b>\n"
        "- Markets moved, but not enough to deserve a push.\n"
        "- Sentinel avoids sending noise just to fill space.\n\n"
        "<i>Context, not financial advice.</i>"
    )


def alert_sec_filing(
    ticker: str,
    company: str,
    filing_type: str,
    summary: str,
    source_url: str,
) -> str:
    return (
        f"<b>{ticker} - {filing_type} filed</b>\n\n"
        f"{company} submitted a new {filing_type} with the SEC.\n\n"
        f"<b>What changed:</b>\n{summary}\n\n"
        "<b>Watch next:</b>\n"
        "- Whether price and volume confirm the filing relevance.\n"
        "- Whether peers react the same way.\n\n"
        f'<a href="{source_url}">Full filing (SEC EDGAR)</a>\n\n'
        "<i>Context, not financial advice.</i>"
    )


def alert_earnings(
    ticker: str,
    company: str,
    result: str,
    eps_actual: float,
    eps_estimate: float,
    revenue_actual: str,
    revenue_estimate: str,
    source_url: str,
) -> str:
    beat_miss = "beat" if eps_actual >= eps_estimate else "missed"
    diff_pct = abs((eps_actual - eps_estimate) / eps_estimate * 100) if eps_estimate else 0
    return (
        f"<b>{ticker} - Earnings {result}</b>\n\n"
        f"{company} {beat_miss} EPS estimates by {diff_pct:.1f}%.\n"
        f"EPS: <b>${eps_actual:.2f}</b> vs ${eps_estimate:.2f} est.\n"
        f"Revenue: <b>{revenue_actual}</b> vs {revenue_estimate} est.\n\n"
        "<b>Watch next:</b>\n"
        "- Guidance tone and analyst revisions.\n"
        "- Whether peers confirm or reject the read-through.\n\n"
        f'<a href="{source_url}">Source</a>\n\n'
        "<i>Your call. Not financial advice.</i>"
    )


def alert_fed_macro(
    event_name: str,
    headline: str,
    detail: str,
    affected_tickers: list[str],
    source_url: str,
) -> str:
    affected = " - ".join(affected_tickers)
    affected_section = f"Affected in your watchlist: {affected}\n\n" if affected else ""
    return (
        f"<b>{event_name}</b>\n\n"
        f"{headline}\n\n"
        f"{detail}\n\n"
        f"{affected_section}"
        "<b>Watch next:</b>\n"
        "- Whether the move is broad market beta or ticker-specific.\n"
        "- Whether your thresholds are hit after the headline settles.\n\n"
        f'<a href="{source_url}">Source</a>\n\n'
        "<i>Context, not financial advice.</i>"
    )


def alert_user_reply_ticker(
    ticker: str,
    last_price: float,
    change_pct: float,
    threshold: float,
    last_cross_desc: str,
    catalyst_scan: str,
) -> str:
    sign = "+" if change_pct > 0 else ""
    on_watchlist = threshold > 0
    watchlist_note = (
        f"Watchlist threshold: +/-{threshold:.1f}% intraday"
        if on_watchlist
        else "Not in your watchlist - send /watchlist to add it"
    )
    no_ping_reason = (
        f"Why no alert yet: move stayed inside +/-{threshold:.1f}%."
        if on_watchlist and abs(change_pct) < threshold
        else "Why it matters: this ticker is moving outside the quiet zone."
    )
    return (
        f"<b>{ticker} - quick check</b>\n\n"
        f"Current: <b>${last_price:.2f}</b> ({sign}{change_pct:.2f}% session)\n"
        f"Last threshold cross: {last_cross_desc}\n"
        f"{watchlist_note}\n"
        f"Catalyst scan (last 4h): {catalyst_scan}\n\n"
        f"{no_ping_reason}\n\n"
        f"Want to adjust threshold? <code>/threshold {ticker} 1</code>\n\n"
        "<i>Context, not financial advice.</i>"
    )


def alert_eod_digest(
    crossings: list[dict],
    quiet_tickers: list[str],
    date_str: str = "",
) -> str:
    date_str = date_str or datetime.now().strftime("%b %d")
    header = f"<b>EOD Digest - {date_str}</b>\n\n"
    if not crossings:
        watched = " - ".join(quiet_tickers) if quiet_tickers else "your watchlist"
        return (
            header +
            f"Watched: {watched}\n\n"
            "No threshold crossing needed a push today.\n\n"
            "<b>Tomorrow watch:</b>\n"
            "- Overnight index direction.\n"
            "- Earnings, filings, or macro headlines touching your names.\n\n"
            "<i>Context, not financial advice.</i>"
        )

    lines = [f"<b>{len(crossings)} crossing{'s' if len(crossings) != 1 else ''}:</b>"]
    for c in sorted(crossings, key=lambda x: abs(x["change_pct"]), reverse=True):
        sign = "+" if c["change_pct"] > 0 else ""
        lines.append(f"<b>{c['ticker']}</b> {sign}{c['change_pct']:.2f}% -> ${c['price']:.2f}")
    if quiet_tickers:
        lines.append(f"\nQuiet: {' - '.join(quiet_tickers)}")
    lines.extend([
        "",
        "<b>Read:</b> Review the largest move first, then check whether peers confirmed it.",
        "",
        "<i>Context, not advice.</i>",
    ])
    return header + "\n".join(lines)


def pro_daily_brief_card(
    date_str: str,
    *,
    user_first_name: str,
    mover: dict,
    score_100: int | None,
    rating: str | None,
    score_change: int | None,
    why_moving: str | None = None,
    risk_flag: str | None = None,
    strongest: list[tuple[str, str]],
    weakest: list[tuple[str, str]],
    peer_tickers: list[str],
) -> str:
    sign = "+" if mover["change_pct"] > 0 else ""
    header = (
        "<b>Sentinel Pro - Daily Brief</b>\n"
        f"<i>{date_str} - 09:00 ET · {session_anchor()} - for {user_first_name}</i>"
    )
    lines = [
        header,
        "",
        "<b>Today's priority:</b>",
        f"<b>${mover['ticker']}</b> - ${mover['price']:.2f} - {sign}{mover['change_pct']:.2f}%",
    ]
    details: list[str] = []
    if mover.get("relative_volume") is not None:
        details.append(f"Vol {mover['relative_volume']:.1f}x avg")
    if mover.get("prev_close") is not None:
        details.append(f"prev ${mover['prev_close']:.2f}")
    if details:
        lines.append("Context: " + " - ".join(details))
    score_part = _score_line({
        "score_100": score_100,
        "rating": rating or "",
        "score_change": score_change,
    }) if score_100 is not None else None
    if score_part:
        lines.extend(["", f"<b>{score_part}</b>"])
    if why_moving and why_moving.strip():
        lines.extend(["", "<b>Why it matters:</b>", why_moving.strip()])
    if risk_flag and risk_flag.strip():
        lines.extend(["", "<b>Risk flag:</b>", risk_flag.strip()])
    if strongest:
        lines.extend(["", "<b>Strongest dimensions:</b>"])
        lines.extend(f"- {label}: {hi}" for label, hi in strongest[:3])
    if weakest:
        lines.extend(["", "<b>Weakest dimensions:</b>"])
        lines.extend(f"- {label}: {hi}" for label, hi in weakest[:3])
    if peer_tickers:
        lines.extend(["", f"<b>Peers:</b> {' - '.join(peer_tickers[:5])}"])
    lines.extend([
        "",
        "<b>You will hear from Sentinel if:</b>",
        "- This move widens past your threshold.",
        "- New filings, earnings, or news alter the read.",
        "",
        "Sources: Yahoo Finance - SEC EDGAR - CNN F&amp;G",
        "Full report -> <a href=\"https://sentinel.jilo.ai\">sentinel.jilo.ai</a>",
        "",
        "<i>Context, not financial advice.</i>",
    ])
    return "\n".join(lines)


def pro_daily_brief_quiet(date_str: str, user_first_name: str) -> str:
    return (
        "<b>Sentinel Pro - Daily Brief</b>\n"
        f"<i>{date_str} - 09:00 ET - for {user_first_name}</i>\n\n"
        "<b>Today's priority:</b>\n"
        "Quiet. No watchlist ticker crossed your threshold with enough confirmation.\n\n"
        "<b>Why no alert yet:</b>\n"
        "- Price moves stayed inside your threshold or lacked a catalyst.\n"
        "- No filing, earnings, or news item changed the evidence balance.\n\n"
        "<b>You will hear from Sentinel if:</b>\n"
        "- A ticker breaks threshold with confirming volume.\n"
        "- The evidence flips from noisy to actionable.\n\n"
        "<i>Context, not financial advice.</i>"
    )


def caught_moment_alert(
    ticker: str,
    headline: str,
    detail: str = "",
    source_url: str = "",
    change_pct: float = 0.0,
) -> str:
    timestamp = _et_now_str()
    anchor = session_anchor()
    sign = "+" if change_pct > 0 else ""
    move_line = f"{ticker} {sign}{change_pct:.2f}% session\n\n" if change_pct else ""
    detail_block = f"<b>Why it matters:</b>\n{detail}\n\n" if detail else ""
    source_block = f'<a href="{source_url}">Source</a>\n\n' if source_url else ""
    return (
        f"<b>{ticker} - {headline}</b>\n"
        f"<i>{timestamp} · {anchor}</i>\n\n"
        f"{move_line}"
        f"{detail_block}"
        "<b>Watch next:</b>\n"
        "- Does volume confirm the headline?\n"
        "- Does the move spread to peers?\n\n"
        f"{source_block}"
        "<i>Context, not financial advice.</i>"
    )


def alert_threshold_crossed_batch(
    crossings: list[dict],
    session: str = "session",
) -> str:
    timestamp = _et_now_str()
    count = len(crossings)
    lines = [
        f"<b>{count} tickers crossed your threshold</b>",
        f"<i>{timestamp}</i>",
        "",
        "<b>Priority order:</b>",
    ]
    for c in sorted(crossings, key=lambda x: abs(x["change_pct"]), reverse=True):
        sign = "+" if c["change_pct"] > 0 else ""
        lines.append(
            f"- <b>{c['ticker']}</b> {sign}{c['change_pct']:.2f}% "
            f"${c.get('prev_price', 0):.2f} -> ${c.get('price', 0):.2f}"
        )
    lines.extend([
        "",
        "<b>Read:</b> Start with the largest absolute move, then check catalysts.",
        "",
        "<i>Your call. Not financial advice.</i>",
    ])
    return "\n".join(lines)
