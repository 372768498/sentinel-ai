"""Financial Modeling Prep (FMP) adapter — market movers + quote enrichment.

Endpoint reference: https://site.financialmodelingprep.com/developer/docs

Key-missing behavior: returns [] with a single WARN log line.
HTTP errors are caught and turned into [] — never raise.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

FMP_BASE = "https://financialmodelingprep.com/api/v3"
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
    """Map an FMP gainers/losers/actives row to MarketMover. Returns None on
    rows that don't look right (no ticker symbol)."""
    ticker = row.get("symbol") or row.get("ticker")
    if not ticker:
        return None
    return MarketMover(
        ticker=str(ticker).upper(),
        price=_as_float(row.get("price")),
        change_pct=_as_float(row.get("changesPercentage") or row.get("change_pct")),
        volume=_as_int(row.get("volume")),
        market_cap=_as_int(row.get("marketCap")),
        company_name=row.get("name") or row.get("companyName"),
        source_url=source_url,
        relative_volume=_as_float(row.get("avgVolume") and row.get("volume") and (
            row["volume"] / row["avgVolume"] if row.get("avgVolume") else None
        )),
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
    """
    if _api_key() is None:
        logger.info("[fmp] FMP_API_KEY missing — returning empty market mover list")
        return []

    gainers = await _get("/stock_market/gainers", {})
    losers = await _get("/stock_market/losers", {})
    actives = await _get("/stock_market/actives", {})

    seen: set[str] = set()
    movers: list[MarketMover] = []
    for payload, label in (
        (gainers, f"{FMP_BASE}/stock_market/gainers"),
        (losers, f"{FMP_BASE}/stock_market/losers"),
        (actives, f"{FMP_BASE}/stock_market/actives"),
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
