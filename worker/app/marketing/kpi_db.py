"""asyncpg queries against the Prisma-managed Postgres for KPI rollups.

Prisma generates PascalCase table names + camelCase column names. Postgres
folds unquoted identifiers to lowercase, so every identifier MUST be quoted.

Connection: opens an asyncpg connection per query batch. KPI aggregation is
a once-per-day task — no need for a pool. The DATABASE_URL env var matches
the one used by Next.js and Prisma migrations.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

try:
    import asyncpg
except ImportError:  # pragma: no cover — tests inject a fake conn
    asyncpg = None

logger = logging.getLogger(__name__)


class KPIDBError(RuntimeError):
    pass


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise KPIDBError("DATABASE_URL is not set")
    return url


# Prisma sometimes appends `?schema=public` / `?connection_limit=N` to
# DATABASE_URL. asyncpg's connection parser rejects unknown query params with
# "unrecognized configuration parameter". Strip Prisma-only keys before
# handing the DSN to asyncpg.
_PRISMA_ONLY_QUERY_KEYS = frozenset({"schema", "connection_limit", "pool_timeout", "pgbouncer"})


def _strip_prisma_query_params(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.query:
        return url
    kept = [
        (k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in _PRISMA_ONLY_QUERY_KEYS
    ]
    return urlunparse(parsed._replace(query=urlencode(kept)))


@asynccontextmanager
async def _connect():
    if asyncpg is None:  # pragma: no cover
        raise KPIDBError("asyncpg is not installed in this environment")
    dsn = _strip_prisma_query_params(_database_url())
    conn = await asyncpg.connect(dsn=dsn)
    try:
        yield conn
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Query helpers (each accepts an injected connection for testability)
# ---------------------------------------------------------------------------

CLICKS_SQL = """
SELECT "utmContent" AS content_id, COUNT(*)::int AS clicks
FROM "VisitEvent"
WHERE "utmContent" IS NOT NULL
  AND "createdAt" >= $1
  AND "createdAt" < $2
GROUP BY "utmContent"
"""

EMAILS_SQL = """
SELECT "utmContent" AS content_id,
       COUNT(*)::int                                AS emails_captured,
       COUNT("verifiedAt")::int                     AS signups
FROM "EmailLead"
WHERE "utmContent" IS NOT NULL
  AND "createdAt" >= $1
  AND "createdAt" < $2
GROUP BY "utmContent"
"""

# Paid attribution: an EmailLead's utmContent gets credit if the linked User
# has an ACTIVE PRO subscription. We don't filter SubscriptionStatus by date —
# any active Pro lead, no matter when they upgraded, counts toward the content
# that captured them. The `as of` snapshot is the row's notes field.
PAID_SQL = """
SELECT el."utmContent" AS content_id,
       COUNT(DISTINCT u.id)::int AS paid_users
FROM "EmailLead" el
JOIN "User" u                  ON u.id = el."userId"
JOIN "SubscriptionStatus" s    ON s."userId" = u.id
WHERE el."utmContent" IS NOT NULL
  AND s.state = 'ACTIVE'
  AND s.plan  = 'PRO'
GROUP BY el."utmContent"
"""


async def fetch_clicks_by_content(
    start: datetime, end: datetime, *, conn=None
) -> dict[str, int]:
    if conn is not None:
        rows = await conn.fetch(CLICKS_SQL, start, end)
    else:
        async with _connect() as c:
            rows = await c.fetch(CLICKS_SQL, start, end)
    return {r["content_id"]: r["clicks"] for r in rows}


async def fetch_email_metrics_by_content(
    start: datetime, end: datetime, *, conn=None
) -> dict[str, dict[str, int]]:
    if conn is not None:
        rows = await conn.fetch(EMAILS_SQL, start, end)
    else:
        async with _connect() as c:
            rows = await c.fetch(EMAILS_SQL, start, end)
    return {
        r["content_id"]: {"emails_captured": r["emails_captured"], "signups": r["signups"]}
        for r in rows
    }


async def fetch_paid_users_by_content(*, conn=None) -> dict[str, int]:
    """All-time attribution (not date-windowed) — see SQL comment."""
    if conn is not None:
        rows = await conn.fetch(PAID_SQL)
    else:
        async with _connect() as c:
            rows = await c.fetch(PAID_SQL)
    return {r["content_id"]: r["paid_users"] for r in rows}


async def fetch_all_metrics(
    start: datetime,
    end: datetime,
    *,
    conn=None,
) -> dict[str, dict[str, int]]:
    """One-shot helper: union of all three queries keyed by content_id."""
    clicks = await fetch_clicks_by_content(start, end, conn=conn)
    emails = await fetch_email_metrics_by_content(start, end, conn=conn)
    paid = await fetch_paid_users_by_content(conn=conn)

    keys = set(clicks) | set(emails) | set(paid)
    out: dict[str, dict[str, int]] = {}
    for content_id in keys:
        e = emails.get(content_id, {})
        out[content_id] = {
            "clicks": clicks.get(content_id, 0),
            "emails_captured": e.get("emails_captured", 0),
            "signups": e.get("signups", 0),
            "paid_users": paid.get(content_id, 0),
        }
    return out
