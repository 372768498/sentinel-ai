"""FMP earnings calendar adapter — next scheduled earnings date per ticker.

Endpoint: GET /stable/earnings-calendar?symbol=TICKER&apikey=...

FMP free tier supports per-symbol queries. The Sentinel default seed list
is small (5-7 tickers), so per-symbol cost is negligible.

Returns the *next* upcoming (or today's) earnings date. Returns None when:
  - FMP_API_KEY is missing
  - No upcoming earnings in response
  - HTTP error of any kind
  - Response shape unexpected

NEVER raises — all errors degrade to None with a single WARN log.
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime
from typing import Iterable, Optional

import httpx

logger = logging.getLogger(__name__)

FMP_BASE = "https://financialmodelingprep.com"
DEFAULT_TIMEOUT = 12.0


def _api_key() -> Optional[str]:
    key = os.environ.get("FMP_API_KEY", "").strip()
    return key or None


async def _fetch_raw(ticker: str) -> Optional[list]:
    key = _api_key()
    if not key:
        return None
    url = f"{FMP_BASE}/stable/earnings-calendar"
    params = {"symbol": ticker.upper(), "apikey": key}
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.get(url, params=params)
        if resp.status_code != 200:
            logger.warning(
                "[earnings_calendar] %s returned HTTP %s",
                ticker,
                resp.status_code,
            )
            return None
        payload = resp.json()
        if not isinstance(payload, list):
            return None
        return payload
    except Exception as exc:
        logger.warning("[earnings_calendar] %s raised %s", ticker, exc)
        return None


def _parse_date(raw: object) -> Optional[date]:
    if not isinstance(raw, str):
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%fZ"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    # Try just the date prefix.
    if len(raw) >= 10:
        try:
            return datetime.strptime(raw[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


async def fetch_next_earnings_date(
    ticker: str,
    *,
    today: Optional[date] = None,
    fetcher=None,
) -> Optional[date]:
    """Return the next earnings date for `ticker`, or None.

    `fetcher` is an injectable async callable for tests; default uses
    real HTTP. Signature: `async fetcher(ticker) -> list | None`.
    """
    ref = today or date.today()
    raw = await (fetcher(ticker) if fetcher else _fetch_raw(ticker))
    if not raw:
        return None
    future_dates: list[date] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        d = _parse_date(row.get("date"))
        if d is None:
            continue
        if d >= ref:
            future_dates.append(d)
    return min(future_dates) if future_dates else None


async def fetch_earnings_dates(
    tickers: Iterable[str],
    *,
    today: Optional[date] = None,
    fetcher=None,
) -> dict[str, Optional[date]]:
    """Batch helper. Returns {TICKER_UPPER: date | None}, queries serially."""
    out: dict[str, Optional[date]] = {}
    for t in tickers:
        key = t.upper()
        out[key] = await fetch_next_earnings_date(
            key, today=today, fetcher=fetcher
        )
    return out
