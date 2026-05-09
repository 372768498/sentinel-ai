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

def alert_threshold_crossed(
    ticker: str,
    change_pct: float,
    prev_price: float,
    last_price: float,
    session: str,
    source_url: str = "",
) -> str:
    direction = "up" if change_pct > 0 else "down"
    arrow = "📈" if change_pct > 0 else "📉"
    sign = "+" if change_pct > 0 else ""
    source_line = f'\n<a href="{source_url}">→ Source</a>' if source_url else ""
    return (
        f"{arrow} <b>{ticker} crossed your threshold</b>\n\n"
        f"{ticker} moved {sign}{change_pct:.2f}% {direction} this {session.lower()}.\n"
        f"${prev_price:.2f} → <b>${last_price:.2f}</b>\n"
        f"{source_line}\n\n"
        "<i>Your call. Not advice.</i>"
    )


def alert_silence_day(tickers: list[str], date_str: str = "") -> str:
    ticker_str = " · ".join(tickers) if tickers else "your watchlist"
    date_str = date_str or datetime.now().strftime("%b %d")
    return (
        f"🔕 <b>Quiet day — {date_str}</b>\n\n"
        f"Nothing in {ticker_str} crossed your threshold today.\n\n"
        "Markets moved. Nothing that warranted a ping.\n\n"
        "<i>Context, not advice.</i>"
    )


def alert_sec_filing(
    ticker: str,
    company: str,
    filing_type: str,
    summary: str,
    source_url: str,
) -> str:
    return (
        f"📋 <b>{ticker} — {filing_type} filed</b>\n\n"
        f"<b>{company}</b> submitted a new {filing_type} with the SEC.\n\n"
        f"{summary}\n\n"
        f'<a href="{source_url}">→ Full filing (SEC EDGAR)</a>\n\n'
        "<i>Context, not advice.</i>"
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
        f"📊 <b>{ticker} — Earnings {result}</b>\n\n"
        f"<b>{company}</b> {beat_miss} EPS estimates by {diff_pct:.1f}%.\n\n"
        f"EPS: <b>${eps_actual:.2f}</b> vs ${eps_estimate:.2f} est.\n"
        f"Revenue: <b>{revenue_actual}</b> vs {revenue_estimate} est.\n\n"
        f'<a href="{source_url}">→ Source</a>\n\n'
        "<i>Your call. Not advice.</i>"
    )


def alert_fed_macro(
    event_name: str,
    headline: str,
    detail: str,
    affected_tickers: list[str],
    source_url: str,
) -> str:
    affected_str = (
        "Affected in your watchlist: " + " · ".join(affected_tickers)
        if affected_tickers
        else ""
    )
    affected_section = f"{affected_str}\n\n" if affected_str else ""
    return (
        f"🏦 <b>{event_name}</b>\n\n"
        f"<b>{headline}</b>\n\n"
        f"{detail}\n\n"
        f"{affected_section}"
        f'<a href="{source_url}">→ Source</a>\n\n'
        "<i>Context, not advice.</i>"
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
        f"Watchlist threshold: ±{threshold:.1f}% intraday"
        if on_watchlist
        else "Not in your watchlist — send /watchlist to add it"
    )
    no_ping_reason = (
        f"Why I haven't pinged you: moves stayed inside ±{threshold:.1f}%."
        if on_watchlist and abs(change_pct) < threshold
        else ""
    )
    return (
        f"<b>{ticker} — quick check</b>\n\n"
        f"Last threshold cross: {last_cross_desc}\n"
        f"Current: <b>${last_price:.2f}</b> ({sign}{change_pct:.2f}% session)\n"
        f"{watchlist_note}\n"
        f"Catalyst scan (last 4h): {catalyst_scan}\n\n"
        f"{no_ping_reason}\n"
        f"Want to adjust threshold? <code>/threshold {ticker} 1</code>\n\n"
        "<i>Context, not advice.</i>"
    )


def alert_eod_digest(
    crossings: list[dict],
    quiet_tickers: list[str],
    date_str: str = "",
) -> str:
    """
    crossings: [{"ticker": "NVDA", "change_pct": 2.3, "price": 125.0}]
    """
    date_str = date_str or datetime.now().strftime("%b %d")
    header = f"📅 <b>EOD Digest — {date_str}</b>\n\n"

    if not crossings:
        body = "Quiet session. Nothing in your watchlist crossed your threshold.\n\n"
        if quiet_tickers:
            body += "Watched: " + " · ".join(quiet_tickers) + "\n\n"
        return header + body + "<i>Context, not advice.</i>"

    lines = [f"<b>{len(crossings)} crossing{'s' if len(crossings) != 1 else ''}:</b>"]
    for c in sorted(crossings, key=lambda x: abs(x["change_pct"]), reverse=True):
        sign = "+" if c["change_pct"] > 0 else ""
        arrow = "📈" if c["change_pct"] > 0 else "📉"
        lines.append(
            f"{arrow} <b>{c['ticker']}</b> {sign}{c['change_pct']:.2f}% → ${c['price']:.2f}"
        )

    if quiet_tickers:
        lines.append(f"\nQuiet: {' · '.join(quiet_tickers)}")

    return header + "\n".join(lines) + "\n\n<i>Context, not advice.</i>"


# ── Public channel templates ───────────────────────────────────────────────────

def public_premarket_brief_quiet(date_str: str) -> str:
    return (
        f"☀️ <b>Pre-market · {date_str}</b>\n\n"
        "Quiet open. No major catalysts in the pipeline this morning.\n\n"
        "Sentinel is watching. You'll hear when it matters.\n\n"
        "<i>Never miss the moment that matters. · Context, not advice.</i>"
    )


def public_premarket_brief_active(date_str: str, items: list[str]) -> str:
    bullet_lines = "\n".join(f"• {item}" for item in items)
    return (
        f"☀️ <b>Pre-market · {date_str}</b>\n\n"
        f"{bullet_lines}\n\n"
        "<i>Never miss the moment that matters. · Context, not advice.</i>"
    )


def public_postclose_digest(
    date_str: str,
    movers: list[dict],
    notes: list[str],
) -> str:
    header = f"🌙 <b>Post-close · {date_str}</b>\n\n"
    if not movers and not notes:
        return (
            header
            + "Quiet session. Markets moved within normal range — nothing exceptional.\n\n"
            "<i>Never miss the moment that matters. · Context, not advice.</i>"
        )

    lines = []
    if movers:
        lines.append("<b>Notable movers:</b>")
        for m in movers[:5]:
            sign = "+" if m["change_pct"] > 0 else ""
            arrow = "📈" if m["change_pct"] > 0 else "📉"
            lines.append(f"{arrow} <b>{m['ticker']}</b> {sign}{m['change_pct']:.2f}%")

    if notes:
        lines.append("\n<b>Context:</b>")
        for n in notes[:3]:
            lines.append(f"• {n}")

    return (
        header
        + "\n".join(lines)
        + "\n\n<i>Never miss the moment that matters. · Context, not advice.</i>"
    )


# ── Help & utility ────────────────────────────────────────────────────────────

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

def caught_moment_alert(
    ticker: str,
    headline: str,
    detail: str = "",
    source_url: str = "",
    change_pct: float = 0.0,
) -> str:
    """
    Operator-triggered alert — used by /api/bot/push-alert during 14-day public test.
    Operator hand-curates to avoid AI mis-reads or broken source links.
    """
    timestamp = _et_now_str()
    sign = "+" if change_pct > 0 else ""
    move_line = (
        f"{ticker} {sign}{change_pct:.2f}% session\n\n"
        if change_pct
        else ""
    )
    detail_block = f"{detail}\n\n" if detail else ""
    source_block = f'<a href="{source_url}">→ Source</a>\n\n' if source_url else ""
    return (
        f"⚡ <b>{ticker} — {headline}</b>\n"
        f"<i>{timestamp}</i>\n\n"
        f"{move_line}"
        f"{detail_block}"
        f"{source_block}"
        "<i>Context, not advice.</i>"
    )


def alert_threshold_crossed_batch(
    crossings: list[dict],
    session: str = "session",
) -> str:
    """
    crossings: [{"ticker": "NVDA", "change_pct": 2.5, "prev_price": 120.0, "price": 123.0}]
    Used when >= 3 tickers cross threshold simultaneously to prevent alert storms.
    """
    timestamp = _et_now_str()
    count = len(crossings)
    lines = [
        f"🔔 <b>{count} tickers crossed your threshold</b>",
        f"<i>{timestamp}</i>",
        "",
    ]
    for c in sorted(crossings, key=lambda x: abs(x["change_pct"]), reverse=True):
        sign = "+" if c["change_pct"] > 0 else ""
        arrow = "📈" if c["change_pct"] > 0 else "📉"
        lines.append(
            f"{arrow} <b>{c['ticker']}</b> {sign}{c['change_pct']:.2f}% "
            f"· ${c.get('prev_price', 0):.2f} → ${c.get('price', 0):.2f}"
        )
    lines += ["", "<i>Your call. Not advice.</i>"]
    return "\n".join(lines)
