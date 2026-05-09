"""
Thursday education posts — static rotation by ISO week number.
5 posts here; backlog for jojo to add 5-15 more later.

Brand rules:
  - No buy/sell/predict
  - Educational, source-aware
  - Always cite primary source where applicable
"""
from __future__ import annotations


EDUCATION_POSTS: list[dict] = [
    {
        "title": "📚 Why the 8-K matters",
        "content": (
            "When a company files a \"Material 8-K\" with the SEC, it means "
            "something happened that shareholders need to know — within 4 "
            "business days.\n\n"
            "Examples:\n"
            "• Executive departure\n"
            "• Acquisition / divestiture announcement\n"
            "• Lawsuit\n"
            "• Material asset write-down\n"
            "• Loss of major customer\n\n"
            "Why we watch them at Sentinel: 8-Ks often move stocks within "
            "minutes of filing. We monitor SEC EDGAR directly — primary "
            "source, no middleman.\n\n"
            "When a watchlist company files material 8-K, you hear from us "
            "in < 30 seconds.\n\n"
            "*Education, not advice. — Sentinel*"
        ),
    },
    {
        "title": "📚 Why we only cite primary sources",
        "content": (
            "Most market commentary you read is a guess dressed up as "
            "analysis. \"NVDA could rally.\" \"TSLA might break support.\" "
            "Confident-sounding. Unfalsifiable.\n\n"
            "We do the opposite at Sentinel. Every alert links to its "
            "primary source — SEC EDGAR, an earnings PR, a Fed statement. "
            "If we can't cite something concrete, we don't ping you.\n\n"
            "**Why it matters:** sources are checkable. Guesses are not. "
            "When you can verify the input, you can decide for yourself.\n\n"
            "Three sources we trust most:\n"
            "• **SEC EDGAR** — primary corporate filings\n"
            "• **Reuters / Bloomberg** — verified breaking news\n"
            "• **Fed / BLS / BEA** — official macro releases\n\n"
            "Everything else is commentary.\n\n"
            "*Context, not advice. — Sentinel*"
        ),
    },
    {
        "title": "📚 How to set your alert threshold",
        "content": (
            "When you onboard, we ask for an intraday move threshold. The "
            "default is ±2%. Here's the tradeoff:\n\n"
            "**±0.5% – ±1%** — high signal density. You'll hear from us "
            "every day in normal markets. Good if you trade actively or "
            "manage tight stops.\n\n"
            "**±2% (default)** — typical S&P 500 single-stock daily range. "
            "Most days, most of your watchlist won't cross. When it does, "
            "it's likely meaningful.\n\n"
            "**±5% or more** — only the loud moves. Earnings shocks, "
            "guidance cuts, regulatory hits. Quiet 90% of trading days.\n\n"
            "There's no \"right\" number. It depends on how often you want "
            "to be reachable. Change anytime: `/threshold all 1.5`\n\n"
            "*— Sentinel*"
        ),
    },
    {
        "title": "📚 Pre-market vs intraday — different beasts",
        "content": (
            "A 4% pre-market move and a 4% intraday move are not the same "
            "thing.\n\n"
            "**Pre-market (4:00 AM – 9:30 AM ET):** thin volume, wide "
            "spreads. A single block trade can swing the price 2-3% on a "
            "small-cap. Half of pre-market moves fade by the open.\n\n"
            "**Intraday (9:30 AM – 4:00 PM ET):** real liquidity. Moves "
            "stick more often, especially after 10:30 AM when overnight "
            "noise has settled.\n\n"
            "**After-hours (4:00 PM – 8:00 PM ET):** earnings releases land "
            "here. Moves are real but illiquid; often retraced at the next "
            "open.\n\n"
            "Sentinel logs the session for every alert so you know which "
            "tape you're looking at.\n\n"
            "*Context, not advice. — Sentinel*"
        ),
    },
    {
        "title": "📚 Quiet hours — why we recommend them",
        "content": (
            "Most Sentinel users set quiet hours from 22:00–07:00 ET. "
            "Here's why we recommend it.\n\n"
            "Markets are closed overnight. Pre-market trading is thin and "
            "noisy. A 3% pre-market move at 5:00 AM ET often retraces by "
            "the regular open. Waking up to it isn't useful.\n\n"
            "**What quiet hours actually do:**\n"
            "• Alerts during your quiet window are queued, not dropped\n"
            "• When your quiet window ends, the queue is delivered as one "
            "consolidated message\n"
            "• You see what happened overnight without 4 separate buzzes "
            "at 5 AM\n\n"
            "Critical events (Fed emergency, halt, delisting) bypass quiet "
            "hours. Everything else respects your sleep.\n\n"
            "Adjust anytime via `/watchlist` → 🌍 Quiet hours.\n\n"
            "*— Sentinel*"
        ),
    },
]


def education_post_for_week(iso_week: int) -> dict:
    """Return one education post by ISO week number, rotating through the list."""
    if not EDUCATION_POSTS:
        raise RuntimeError("EDUCATION_POSTS is empty")
    return EDUCATION_POSTS[iso_week % len(EDUCATION_POSTS)]
