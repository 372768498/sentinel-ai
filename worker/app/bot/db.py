"""
asyncpg-based DB layer for Telegram bot user profiles, cooldowns, and queued alerts.
All timestamps stored as UTC (TIMESTAMPTZ). Displayed to users in ET via tz_check.to_et().
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None
_pool_lock = asyncio.Lock()

_CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS telegram_bot_profile (
    telegram_user_id    BIGINT PRIMARY KEY,
    telegram_username   TEXT,
    telegram_first_name TEXT,
    watchlist           TEXT[]  NOT NULL DEFAULT '{}',
    alert_threshold     FLOAT   NOT NULL DEFAULT 2.0,
    quiet_hours_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    quiet_hours_start   INT     NOT NULL DEFAULT 22,
    quiet_hours_end     INT     NOT NULL DEFAULT 7,
    onboarding_completed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tbp_onboarding
    ON telegram_bot_profile (onboarding_completed);

-- Dedup: prevents re-alerting same ticker+direction within cooldown window
CREATE TABLE IF NOT EXISTS alert_cooldown (
    telegram_user_id BIGINT  NOT NULL,
    ticker           TEXT    NOT NULL,
    direction        CHAR(1) NOT NULL,  -- '+' or '-'
    triggered_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (telegram_user_id, ticker, direction)
);

-- Quiet-hours queue: alerts that couldn't be sent immediately
CREATE TABLE IF NOT EXISTS queued_alerts (
    id               SERIAL PRIMARY KEY,
    telegram_user_id BIGINT NOT NULL,
    ticker           TEXT   NOT NULL,
    payload_json     JSONB  NOT NULL,
    queued_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sent_at          TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_qa_unsent
    ON queued_alerts (telegram_user_id, sent_at)
    WHERE sent_at IS NULL;

-- Permanent log of every successfully delivered alert (powers Whop daily posts)
CREATE TABLE IF NOT EXISTS alert_log (
    id               SERIAL PRIMARY KEY,
    telegram_user_id BIGINT NOT NULL,
    ticker           TEXT   NOT NULL,
    change_pct       FLOAT  NOT NULL,
    direction        CHAR(1) NOT NULL,
    priority         TEXT   NOT NULL DEFAULT 'normal',
    sent_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alog_sent_at ON alert_log (sent_at);
CREATE INDEX IF NOT EXISTS idx_alog_user_sent
    ON alert_log (telegram_user_id, sent_at);
"""

COOLDOWN_MINUTES = 30


def _clean_dsn(raw: str) -> str:
    """Strip Prisma-specific query params (e.g. ?schema=public) that asyncpg rejects."""
    from urllib.parse import urlparse, urlunparse, parse_qs
    p = urlparse(raw)
    params = parse_qs(p.query)
    params.pop("schema", None)
    params.pop("connection_limit", None)
    import urllib.parse
    new_query = urllib.parse.urlencode({k: v[0] for k, v in params.items()})
    return urlunparse(p._replace(query=new_query))


async def get_pool() -> asyncpg.Pool:
    global _pool
    async with _pool_lock:
        if _pool is None:
            raw_dsn = os.environ.get("DATABASE_URL", "")
            if not raw_dsn:
                raise RuntimeError("DATABASE_URL is not set — bot DB unavailable")
            dsn = _clean_dsn(raw_dsn)
            _pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
            async with _pool.acquire() as conn:
                await conn.execute(_CREATE_TABLES_SQL)
            logger.info("bot DB pool ready (3 tables)")
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("bot DB pool closed")


# ── Profile CRUD ──────────────────────────────────────────────────────────────

async def get_profile(telegram_user_id: int) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM telegram_bot_profile WHERE telegram_user_id = $1",
            telegram_user_id,
        )
    return dict(row) if row else None


async def upsert_profile(telegram_user_id: int, **fields: Any) -> None:
    if not fields:
        return
    pool = await get_pool()
    cols = list(fields.keys())
    vals = list(fields.values())
    set_clause = ", ".join(f"{c} = ${i+2}" for i, c in enumerate(cols))
    set_clause += ", updated_at = NOW()"
    async with pool.acquire() as conn:
        await conn.execute(
            f"""
            INSERT INTO telegram_bot_profile (telegram_user_id, {', '.join(cols)})
            VALUES ($1, {', '.join(f'${i+2}' for i in range(len(cols)))})
            ON CONFLICT (telegram_user_id) DO UPDATE SET {set_clause}
            """,
            telegram_user_id,
            *vals,
        )


async def set_watchlist(telegram_user_id: int, tickers: list[str]) -> None:
    await upsert_profile(telegram_user_id, watchlist=tickers)


async def set_threshold(telegram_user_id: int, threshold: float) -> None:
    await upsert_profile(telegram_user_id, alert_threshold=threshold)


async def set_quiet_hours(
    telegram_user_id: int,
    enabled: bool,
    start: int = 22,
    end: int = 7,
) -> None:
    await upsert_profile(
        telegram_user_id,
        quiet_hours_enabled=enabled,
        quiet_hours_start=start,
        quiet_hours_end=end,
    )


async def mark_onboarding_done(telegram_user_id: int) -> None:
    await upsert_profile(telegram_user_id, onboarding_completed=True)


async def get_all_active_profiles() -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM telegram_bot_profile WHERE onboarding_completed = TRUE"
        )
    return [dict(r) for r in rows]


async def delete_profile(telegram_user_id: int) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM telegram_bot_profile WHERE telegram_user_id = $1",
            telegram_user_id,
        )


# ── Alert cooldown ────────────────────────────────────────────────────────────

async def is_on_cooldown(telegram_user_id: int, ticker: str, direction: str) -> bool:
    """True if this (user, ticker, direction) was already alerted within COOLDOWN_MINUTES."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT 1 FROM alert_cooldown
            WHERE telegram_user_id = $1
              AND ticker = $2
              AND direction = $3
              AND triggered_at > NOW() - ($4 * INTERVAL '1 minute')
            """,
            telegram_user_id,
            ticker,
            direction,
            COOLDOWN_MINUTES,
        )
    return row is not None


async def set_cooldown(telegram_user_id: int, ticker: str, direction: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO alert_cooldown (telegram_user_id, ticker, direction, triggered_at)
            VALUES ($1, $2, $3, NOW())
            ON CONFLICT (telegram_user_id, ticker, direction)
            DO UPDATE SET triggered_at = NOW()
            """,
            telegram_user_id,
            ticker,
            direction,
        )


async def clear_cooldowns(telegram_user_id: int) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM alert_cooldown WHERE telegram_user_id = $1",
            telegram_user_id,
        )


# ── Queued alerts ─────────────────────────────────────────────────────────────

async def queue_alert(telegram_user_id: int, ticker: str, payload: dict) -> int:
    """Queue an alert for later delivery (during quiet hours). Returns row id."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO queued_alerts (telegram_user_id, ticker, payload_json)
            VALUES ($1, $2, $3)
            RETURNING id
            """,
            telegram_user_id,
            ticker,
            json.dumps(payload),
        )
    return row["id"]


async def get_pending_queued_alerts() -> list[dict]:
    """All unsent queued alerts."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM queued_alerts WHERE sent_at IS NULL ORDER BY queued_at"
        )
    return [dict(r) for r in rows]


async def mark_queued_sent(alert_id: int) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE queued_alerts SET sent_at = NOW() WHERE id = $1",
            alert_id,
        )


async def delete_test_queued_alerts(telegram_user_id: int) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM queued_alerts WHERE telegram_user_id = $1",
            telegram_user_id,
        )


# ── Alert log (permanent record powering Whop daily posts) ────────────────────

async def log_alert_sent(
    telegram_user_id: int,
    ticker: str,
    change_pct: float,
    priority: str = "normal",
) -> None:
    direction = "+" if change_pct >= 0 else "-"
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO alert_log
                (telegram_user_id, ticker, change_pct, direction, priority)
            VALUES ($1, $2, $3, $4, $5)
            """,
            telegram_user_id, ticker, change_pct, direction, priority,
        )


async def alerts_in_window(
    start_utc, end_utc,
) -> list[dict]:
    """All alerts logged between [start_utc, end_utc). Used by Whop publisher."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM alert_log
            WHERE sent_at >= $1 AND sent_at < $2
            ORDER BY sent_at
            """,
            start_utc, end_utc,
        )
    return [dict(r) for r in rows]


async def delete_test_alert_log(telegram_user_id: int) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM alert_log WHERE telegram_user_id = $1",
            telegram_user_id,
        )
