"""Financial Modeling Prep (FMP) adapter — market movers + quote enrichment.

Endpoint reference: https://site.financialmodelingprep.com/developer/docs

FMP deprecated `/api/v3/*` on 2025-08-31. All endpoints are now under
`/stable/*` with slightly different field naming:
  - /stable/quote               → `changePercentage` (singular, with quote+enrichment)
  - /stable/biggest-gainers     → `changesPercentage` (plural)
  - /stable/biggest-losers      → `changesPercentage`
  - /stable/most-actives        → `changesPercentage`

Key-missing behavior: returns [] with a single WARN log line.
HTTP errors are caught and turned into [] — never raise.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Iterable, Optional

import httpx

logger = logging.getLogger(__name__)

FMP_BASE = "https://financialmodelingprep.com"
DEFAULT_TIMEOUT = 12.0


@dataclass(frozen=True)
class MarketMover:
    ticker: str
    price: float | None
    change_pct: float | None
    volume: int | None
    market_cap: int | None
    company_name: str | None
    source_url: str
    relative_volume: float | None = None


def _api_key() -> str | None:
    key = os.environ.get("FMP_API_KEY", "").strip()
    return key or None


async def _get(path: str, params: dict[str, Any]) -> Any:
    key = _api_key()
    if not key:
        return None
    params = dict(params)
    params["apikey"] = key
    url = f"{FMP_BASE}{path}"
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.get(url, params=params)
        if resp.status_code != 200:
            logger.warning("[fmp] %s returned HTTP %s", path, resp.status_code)
            return None
        return resp.json()
    except Exception as exc:
        logger.warning("[fmp] %s raised %s", path, exc)
        return None


def _row_to_mover(row: dict[str, Any], source_url: str) -> Optional[MarketMover]:
    """Map an FMP row (movers OR quote) to MarketMover.

    Handles both naming variants:
      - movers endpoints:  `changesPercentage` (plural)
      - quote endpoint:    `changePercentage`  (singular)
    """
    ticker = row.get("symbol") or row.get("ticker")
    if not ticker:
        return None
    change = (
        row.get("changesPercentage")
        if row.get("changesPercentage") is not None
        else row.get("changePercentage")
    )
    return MarketMover(
        ticker=str(ticker).upper(),
        price=_as_float(row.get("price")),
        change_pct=_as_float(change),
        volume=_as_int(row.get("volume")),
        market_cap=_as_int(row.get("marketCap")),
        company_name=row.get("name") or row.get("companyName"),
        source_url=source_url,
        relative_volume=None,  # /stable/quote doesn't expose avg-volume; future enrichment
    )


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        # FMP sometimes returns "+1.23%" or "1.23%"
        if isinstance(value, str):
            value = value.replace("%", "").replace("+", "")
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


async def fetch_market_movers(*, limit: int = 20) -> list[MarketMover]:
    """Returns the union of gainers/losers/actives, deduplicated by ticker.

    With no FMP_API_KEY → returns [] silently (after a single WARN log).
    Note: this discovery flow is dominated by micro-caps. Use
    `fetch_quotes_for_tickers` to enrich known watchlist tickers.
    """
    if _api_key() is None:
        logger.info("[fmp] FMP_API_KEY missing — returning empty market mover list")
        return []

    gainers = await _get("/stable/biggest-gainers", {})
    losers = await _get("/stable/biggest-losers", {})
    actives = await _get("/stable/most-actives", {})

    seen: set[str] = set()
    movers: list[MarketMover] = []
    for payload, label in (
        (gainers, f"{FMP_BASE}/stable/biggest-gainers"),
        (losers, f"{FMP_BASE}/stable/biggest-losers"),
        (actives, f"{FMP_BASE}/stable/most-actives"),
    ):
        if not isinstance(payload, list):
            continue
        for row in payload:
            mover = _row_to_mover(row, label)
            if mover is None or mover.ticker in seen:
                continue
            seen.add(mover.ticker)
            movers.append(mover)
            if len(movers) >= limit:
                return movers
    return movers


async def fetch_quotes_for_tickers(tickers: Iterable[str]) -> list[MarketMover]:
    """Per-ticker quote lookup via /stable/quote?symbol=TICKER.

    FMP free tier returns HTTP 402 on batch (`symbol=A,B,C`) — only single-
    ticker queries are free. Issue one request per ticker (still cheap;
    5 tickers/day = 5/250 daily quota).

    This is the right discovery flow for known watchlist tickers (NVDA / AAPL /
    etc) — they rarely appear in biggest-gainers (which is dominated by
    micro-cap volatility).
    """
    if _api_key() is None:
        logger.info("[fmp] FMP_API_KEY missing — returning empty quote list")
        return []
    cleaned = [t.strip().upper() for t in tickers if t and t.strip()]
    if not cleaned:
        return []
    out: list[MarketMover] = []
    for ticker in cleaned:
        payload = await _get("/stable/quote", {"symbol": ticker})
        if not isinstance(payload, list) or not payload:
            continue
        source_url = f"{FMP_BASE}/stable/quote?symbol={ticker}"
        mover = _row_to_mover(payload[0], source_url)
        if mover is not None:
            out.append(mover)
    return out
