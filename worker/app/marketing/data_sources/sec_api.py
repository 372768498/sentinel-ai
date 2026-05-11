"""SEC filings adapter — preferred path is sec-api.io (SEC_API_KEY); falls back
to the existing in-repo EDGAR scraper (`worker.app.marketing.catalysts`).

Output is a uniform `CatalystSignal` regardless of which path supplied the data.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from ..catalysts import Catalyst, latest_catalyst

logger = logging.getLogger(__name__)

SEC_API_BASE = "https://api.sec-api.io"
DEFAULT_TIMEOUT = 12.0


@dataclass(frozen=True)
class CatalystSignal:
    ticker: str
    form: str
    headline: str
    url: str
    observed_at: datetime
    days_since_observed: int
    source: str  # sec_api | edgar_fallback


def _api_key() -> str | None:
    return os.environ.get("SEC_API_KEY", "").strip() or None


def _from_catalyst(catalyst: Catalyst, ticker: str) -> CatalystSignal:
    now = datetime.now(timezone.utc)
    # Catalyst.filing_date is datetime.date; promote to UTC midnight.
    observed = datetime.combine(
        catalyst.filing_date, datetime.min.time()
    ).replace(tzinfo=timezone.utc)
    days = max(0, (now.date() - catalyst.filing_date).days)
    return CatalystSignal(
        ticker=ticker.upper(),
        form=catalyst.form,
        headline=catalyst.headline(),
        url=catalyst.homepage_url,
        observed_at=observed,
        days_since_observed=days,
        source="edgar_fallback",
    )


def _from_sec_api_row(row: dict[str, Any], ticker: str) -> Optional[CatalystSignal]:
    """sec-api.io returns rows shaped like:
    { 'formType': '8-K', 'filedAt': '2026-05-11T13:15:00-04:00',
      'linkToFilingDetails': 'https://www.sec.gov/...', 'description': '...' }
    """
    form = row.get("formType") or row.get("form")
    filed_at_raw = row.get("filedAt") or row.get("filed_at")
    link = row.get("linkToFilingDetails") or row.get("link") or row.get("url")
    headline = row.get("description") or row.get("documentFormatFiles", [{}])[0].get(
        "description", form or "filing"
    ) or "filing"
    if not (form and filed_at_raw and link):
        return None
    try:
        # sec-api.io uses ISO-8601 with offset
        observed = datetime.fromisoformat(filed_at_raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return CatalystSignal(
        ticker=ticker.upper(),
        form=str(form),
        headline=str(headline)[:200],
        url=link,
        observed_at=observed,
        days_since_observed=max(0, (now - observed).days),
        source="sec_api",
    )


async def _fetch_via_sec_api(ticker: str, *, limit: int) -> list[CatalystSignal]:
    """Query sec-api.io's full-text search endpoint."""
    key = _api_key()
    if key is None:
        return []
    query = {
        "query": {
            "query_string": {
                "query": f'ticker:{ticker.upper()} AND (formType:"8-K" OR formType:"10-Q" OR formType:"10-K")'
            }
        },
        "from": "0",
        "size": str(limit),
        "sort": [{"filedAt": {"order": "desc"}}],
    }
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.post(
                f"{SEC_API_BASE}?token={key}", json=query
            )
        if resp.status_code != 200:
            logger.warning("[sec_api] HTTP %s for %s", resp.status_code, ticker)
            return []
        payload = resp.json()
    except Exception as exc:
        logger.warning("[sec_api] %s raised %s", ticker, exc)
        return []
    filings = payload.get("filings", []) if isinstance(payload, dict) else []
    out: list[CatalystSignal] = []
    for row in filings:
        signal = _from_sec_api_row(row, ticker)
        if signal is not None:
            out.append(signal)
    return out


async def fetch_recent_catalysts(ticker: str, *, limit: int = 3) -> list[CatalystSignal]:
    """Try sec-api.io first (if SEC_API_KEY set); fall back to EDGAR scraper.

    Always returns a list (possibly empty) — never raises.
    """
    if _api_key() is not None:
        signals = await _fetch_via_sec_api(ticker, limit=limit)
        if signals:
            return signals[:limit]

    # Fallback to existing EDGAR adapter (returns single most-recent catalyst)
    try:
        catalyst = await latest_catalyst(ticker)
    except Exception as exc:
        logger.warning("[sec_api] EDGAR fallback failed for %s: %s", ticker, exc)
        return []
    if catalyst is None:
        return []
    return [_from_catalyst(catalyst, ticker)]
