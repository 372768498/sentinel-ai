"""
Whop forum post templates — 5 types rotating Mon-Fri.

Brand rules (same as Telegram):
  - No buy/sell/predict language
  - Quiet, numbers-first, minimal adjectives
  - Quiet day = still post, just acknowledge silence
"""
from __future__ import annotations


# ── Monday: Week ahead preview ────────────────────────────────────────────────

def monday_week_ahead(
    month_day: str,
    earnings_list: str = "",
    macro_events: str = "",
) -> dict:
    earnings_block = earnings_list.strip() or "No major earnings on the calendar."
    macro_block = macro_events.strip() or "No scheduled macro events of note."
    return {
        "title": f"🌅 Week ahead · {month_day}",
        "content": (
            "Markets reopen today. Here's what we're watching this week:\n\n"
            "**Earnings on watch:**\n"
            f"{earnings_block}\n\n"
            "**Macro events:**\n"
            f"{macro_block}\n\n"
            "**What we WON'T do:**\n"
            "× Forecast direction\n"
            "× Make trade calls\n"
            "× Hype the action\n\n"
            "We watch your watchlist. When something material crosses your "
            "threshold, you hear from us. Not before.\n\n"
            "*Quiet until it matters. — Sentinel*"
        ),
    }


# ── Tuesday: Yesterday's catch ────────────────────────────────────────────────

def tuesday_caught_recap(
    alert_count: int,
    alerts_summary: str = "",
    scanned_count: int = 0,
) -> dict:
    if alert_count == 0:
        return {
            "title": "🎯 Yesterday's catch",
            "content": (
                f"Yesterday: {scanned_count} events scanned, 0 alerts sent.\n\n"
                "No watchlist crossed. No noise to share. Just the silence "
                "we promise.\n\n"
                "*That's the product. — Sentinel*"
            ),
        }

    summary = alerts_summary.strip() or "*(see private alerts for ticker-level detail)*"
    return {
        "title": "🎯 Yesterday's catch",
        "content": (
            f"Yesterday we flagged {alert_count} thing{'s' if alert_count != 1 else ''} "
            "to Pro users:\n\n"
            f"{summary}\n\n"
            f"Behind these {alert_count} alert{'s' if alert_count != 1 else ''}: "
            f"{scanned_count} other events scanned and filtered out.\n\n"
            "That's the work we hide from you, so you only see what crossed "
            "your line.\n\n"
            "*Context, not advice. — Sentinel*"
        ),
    }


# ── Wednesday: Behind the scenes ──────────────────────────────────────────────

def wednesday_behind_scenes(
    scanned_count: int,
    filtered_count: int,
    crossed_count: int,
    crossed_details: str = "",
    closest_miss: str = "",
) -> dict:
    crossed_block = (
        crossed_details.strip()
        if crossed_details.strip()
        else "*(see private alerts for ticker-level detail)*"
    )
    miss_block = closest_miss.strip() or "Nothing came particularly close today."
    return {
        "title": "🔍 Scanner stats · Wednesday",
        "content": (
            "Today's work behind your watchlists:\n\n"
            f"**Events scanned:** {scanned_count}\n"
            f"**Filtered out (irrelevant):** {filtered_count}\n"
            f"**Crossed Pro user thresholds:** {crossed_count}\n\n"
            f"{crossed_block}\n\n"
            f"**Closest call (didn't cross):** {miss_block}\n\n"
            "Most days, this is what we look like. Working in silence.\n\n"
            "*— Sentinel*"
        ),
    }


# ── Friday: Week-in-review ────────────────────────────────────────────────────

def friday_week_review(
    start_date: str,
    end_date: str,
    weekly_scanned: int,
    weekly_filtered: int,
    weekly_alerts: int,
    loudest_day: str,
    loudest_alerts: int,
    quietest_day: str,
    quietest_alerts: int,
    loudest_event_summary: str = "",
) -> dict:
    pct_filtered = (
        round(weekly_filtered / weekly_scanned * 100, 1)
        if weekly_scanned > 0
        else 0.0
    )
    summary_block = (
        f"\n{loudest_event_summary.strip()}\n"
        if loudest_event_summary.strip()
        else ""
    )
    return {
        "title": f"📊 Week wrap · {start_date} → {end_date}",
        "content": (
            "5 trading days. Here's our week in numbers:\n\n"
            f"**Total events scanned:** {weekly_scanned}\n"
            f"**Filtered out as noise:** {weekly_filtered} "
            f"({pct_filtered}% of all events)\n"
            f"**Crossed Pro user thresholds:** {weekly_alerts}\n\n"
            f"**Loudest day:** {loudest_day} "
            f"({loudest_alerts} alert{'s' if loudest_alerts != 1 else ''})\n"
            f"**Quietest day:** {quietest_day} "
            f"({quietest_alerts} alert{'s' if quietest_alerts != 1 else ''})\n"
            f"{summary_block}\n"
            "Next week we watch again. Same discipline.\n\n"
            "*Have a quiet weekend. — Sentinel*"
        ),
    }


# ── Fallback: scanner had a hiccup or no data available ──────────────────────

def fallback_quiet_day(month_day: str = "") -> dict:
    suffix = f" · {month_day}" if month_day else ""
    return {
        "title": f"🌙 Quiet day{suffix}",
        "content": (
            "A quiet trading day. Nothing in our watchlists crossed Pro user "
            "thresholds today.\n\n"
            "Markets moved. Nothing material enough to ping anyone. That's "
            "the bar — context, not noise.\n\n"
            "*— Sentinel*"
        ),
    }
