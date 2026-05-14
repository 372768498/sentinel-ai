"""
Sentinel scoring package.

Wraps the xiangyu-finance-stock-analyzing skill (a Python CLI that returns
a 10-dimension fundamental/technical/sentiment score in JSON) and persists
daily scores to Postgres so the Telegram radar templates can show a
"Sentinel score 67/100 · Buy (▲ +3 vs prev)" line without re-computing on
every push.

Public API:
    init_db(pool)         — create the daily_scores table if missing
    score_one(ticker)     — run xiangyu --fast for one ticker, return ScoreSnapshot
    score_watchlist(ts)   — score N tickers in parallel
    store_score(...)      — upsert today's row into daily_scores
    get_latest_scores(ts) — return {ticker: ScoreRow} for the most recent
                            non-future date per ticker (used by morning/
                            mid-day briefs to read the score computed at
                            the previous post-close)
    get_score_delta(t)    — (today_score, prior_score) for delta arrow
"""

from .engine import ScoreSnapshot, rating_label_for, score_one, score_watchlist
from .store import (
    ScoreRow,
    get_latest_scores,
    get_score_delta,
    init_db,
    store_score,
)

__all__ = [
    "ScoreSnapshot",
    "ScoreRow",
    "rating_label_for",
    "score_one",
    "score_watchlist",
    "init_db",
    "store_score",
    "get_latest_scores",
    "get_score_delta",
]
