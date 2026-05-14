"""
Persistence layer for the daily 10-dimension score.

Schema (created idempotently at worker startup):

    daily_scores
        ticker            text         not null
        date              date         not null    -- ET trading date
        score_100         int          not null
        rating            text         not null    -- English label
        recommendation    text         not null    -- xiangyu's CN-flavored band
        components_json   jsonb        not null
        supporting_json   jsonb        not null
        caveats_json      jsonb        not null
        computed_at       timestamptz  not null default now()
        primary key (ticker, date)

Read patterns:
  - get_latest_scores(tickers)  → most recent row per ticker (used by
    08:30 / 12:30 ET briefs to pull "yesterday's post-close score")
  - get_score_delta(ticker)     → (latest_score, prior_score) for the
    "▲ +3 vs prev" arrow

Writes:
  - store_score(snapshot, et_date) — upsert; rerunning on the same day
    overwrites (we want the freshest computation, not the first).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date

import asyncpg

from .engine import ScoreSnapshot

logger = logging.getLogger(__name__)

_CREATE_SCORES_SQL = """
CREATE TABLE IF NOT EXISTS daily_scores (
    ticker          TEXT        NOT NULL,
    date            DATE        NOT NULL,
    score_100       INT         NOT NULL,
    rating          TEXT        NOT NULL,
    recommendation  TEXT        NOT NULL,
    components_json JSONB       NOT NULL DEFAULT '{}'::jsonb,
    supporting_json JSONB       NOT NULL DEFAULT '[]'::jsonb,
    caveats_json    JSONB       NOT NULL DEFAULT '[]'::jsonb,
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ticker, date)
);

CREATE INDEX IF NOT EXISTS idx_daily_scores_ticker_date_desc
    ON daily_scores (ticker, date DESC);
"""


@dataclass(frozen=True)
class ScoreRow:
    ticker: str
    date: date
    score_100: int
    rating: str
    recommendation: str


async def init_db(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(_CREATE_SCORES_SQL)
    logger.info("scoring DB ready (daily_scores table)")


async def store_score(
    pool: asyncpg.Pool, snapshot: ScoreSnapshot, et_date: date,
) -> None:
    """Upsert today's score for one ticker."""
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO daily_scores
                (ticker, date, score_100, rating, recommendation,
                 components_json, supporting_json, caveats_json, computed_at)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8::jsonb, NOW())
            ON CONFLICT (ticker, date) DO UPDATE SET
                score_100       = EXCLUDED.score_100,
                rating          = EXCLUDED.rating,
                recommendation  = EXCLUDED.recommendation,
                components_json = EXCLUDED.components_json,
                supporting_json = EXCLUDED.supporting_json,
                caveats_json    = EXCLUDED.caveats_json,
                computed_at     = NOW()
            """,
            snapshot.ticker.upper(),
            et_date,
            snapshot.score_100,
            snapshot.rating,
            snapshot.recommendation,
            json.dumps(snapshot.components, ensure_ascii=False),
            json.dumps(snapshot.supporting_points, ensure_ascii=False),
            json.dumps(snapshot.caveats, ensure_ascii=False),
        )


async def get_latest_scores(
    pool: asyncpg.Pool, tickers: list[str],
) -> dict[str, ScoreRow]:
    """
    Return the most recent score row per ticker. Empty dict on cold start
    (no rows yet) so callers should tolerate missing entries.
    """
    if not tickers:
        return {}
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT ON (ticker)
                   ticker, date, score_100, rating, recommendation
              FROM daily_scores
             WHERE ticker = ANY($1::text[])
             ORDER BY ticker, date DESC
            """,
            [t.upper() for t in tickers],
        )
    return {
        r["ticker"]: ScoreRow(
            ticker=r["ticker"],
            date=r["date"],
            score_100=r["score_100"],
            rating=r["rating"],
            recommendation=r["recommendation"],
        )
        for r in rows
    }


async def get_score_delta(
    pool: asyncpg.Pool, ticker: str,
) -> tuple[ScoreRow | None, ScoreRow | None]:
    """
    Return (latest, prior) for the score-change arrow.
    Either side may be None on cold start / single-day history.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT ticker, date, score_100, rating, recommendation
              FROM daily_scores
             WHERE ticker = $1
             ORDER BY date DESC
             LIMIT 2
            """,
            ticker.upper(),
        )
    parsed = [
        ScoreRow(
            ticker=r["ticker"], date=r["date"], score_100=r["score_100"],
            rating=r["rating"], recommendation=r["recommendation"],
        )
        for r in rows
    ]
    latest = parsed[0] if parsed else None
    prior = parsed[1] if len(parsed) > 1 else None
    return latest, prior
