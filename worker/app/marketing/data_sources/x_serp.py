"""X (Twitter) signal scanner via SERP — bypasses the suspended official X API.

Primary path: DataForSEO SERP API (`site:x.com "$TICKER" ...`).
Fallback path: Tavily search.

Intent classification is keyword-based for this phase — purely defensive. We
never emit `buy / sell / hold` recommendations even when X posts contain them;
we only LABEL the intent so the Content Factory can pick a safe angle.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

import httpx

logger = logging.getLogger(__name__)

DATAFORSEO_BASE = "https://api.dataforseo.com/v3"
TAVILY_BASE = "https://api.tavily.com/search"
DEFAULT_TIMEOUT = 15.0

INTENT_TICKER_BUZZ = "ticker_buzz"
INTENT_HIGH_INTENT_QUESTION = "high_intent_question"
INTENT_COMPETITOR_ALTERNATIVE = "competitor_alternative"
INTENT_RISK_DISCUSSION = "risk_discussion"

# Competitor terms — used both to seed queries AND to classify result intent.
COMPETITOR_TERMS: tuple[str, ...] = (
    "tipranks alternative",
    "simply wall st alternative",
    "seeking alpha alternative",
    "stock analysis tool",
    "ai stock analysis",
)


@dataclass(frozen=True)
class SocialSignal:
    source: str  # dataforseo | tavily | apify
    query: str
    ticker: str | None
    title: str
    url: str
    snippet: str
    observed_at: datetime
    estimated_engagement: int | None
    intent: str


def _classify_intent(text: str) -> str:
    lowered = text.lower()
    if any(t in lowered for t in COMPETITOR_TERMS):
        return INTENT_COMPETITOR_ALTERNATIVE
    if any(
        marker in lowered
        for marker in ("is ", "should i", "anyone using", "what do you think", "?")
    ):
        return INTENT_HIGH_INTENT_QUESTION
    if any(t in lowered for t in ("risk", "overvalued", "bubble", "decline", "miss", "concern")):
        return INTENT_RISK_DISCUSSION
    return INTENT_TICKER_BUZZ


def build_x_queries(tickers: Iterable[str]) -> list[str]:
    """8-query basket per spec — ticker-specific + competitor-alternative."""
    queries: list[str] = []
    for ticker in tickers:
        t = ticker.upper()
        queries.extend(
            [
                f'site:x.com "${t}" stock',
                f'site:x.com "${t}" earnings',
                f'site:x.com "${t}" overvalued',
                f'site:x.com "${t}" risk',
            ]
        )
    # competitor queries are global, not per-ticker
    for term in (
        '"TipRanks alternative"',
        '"Simply Wall St alternative"',
        '"AI stock analysis"',
    ):
        queries.append(f"site:x.com {term}")
    return queries


def _extract_ticker(query: str, tickers: list[str]) -> str | None:
    for t in tickers:
        if f'"${t.upper()}"' in query:
            return t.upper()
    return None


# ---------------------------------------------------------------------------
# DataForSEO path
# ---------------------------------------------------------------------------


def _dataforseo_credentials() -> str | None:
    login = os.environ.get("DATAFORSEO_LOGIN", "").strip()
    password = os.environ.get("DATAFORSEO_PASSWORD", "").strip()
    if not login or not password:
        return None
    token = base64.b64encode(f"{login}:{password}".encode()).decode()
    return f"Basic {token}"


async def _query_dataforseo(query: str) -> list[dict[str, Any]]:
    auth = _dataforseo_credentials()
    if auth is None:
        return []
    payload = [
        {"language_code": "en", "location_code": 2840, "keyword": query, "depth": 10}
    ]
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.post(
                f"{DATAFORSEO_BASE}/serp/google/organic/live/regular",
                json=payload,
                headers={"Authorization": auth},
            )
        if resp.status_code != 200:
            logger.warning("[x_serp] DataForSEO HTTP %s for %r", resp.status_code, query[:60])
            return []
        data = resp.json()
    except Exception as exc:
        logger.warning("[x_serp] DataForSEO raised %s", exc)
        return []
    try:
        items = data["tasks"][0]["result"][0]["items"]
    except (KeyError, IndexError, TypeError):
        return []
    return [
        {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": item.get("description", "") or item.get("snippet", ""),
        }
        for item in items
        if isinstance(item, dict) and item.get("url", "").startswith("https://x.com")
    ]


# ---------------------------------------------------------------------------
# Tavily fallback path
# ---------------------------------------------------------------------------


def _tavily_key() -> str | None:
    return os.environ.get("TAVILY_API_KEY", "").strip() or None


async def _query_tavily(query: str) -> list[dict[str, Any]]:
    key = _tavily_key()
    if key is None:
        return []
    payload = {
        "api_key": key,
        "query": query,
        "search_depth": "basic",
        "include_domains": ["x.com", "twitter.com"],
        "max_results": 10,
    }
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.post(TAVILY_BASE, json=payload)
        if resp.status_code != 200:
            logger.warning("[x_serp] Tavily HTTP %s for %r", resp.status_code, query[:60])
            return []
        data = resp.json()
    except Exception as exc:
        logger.warning("[x_serp] Tavily raised %s", exc)
        return []
    return [
        {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "snippet": r.get("content", "") or r.get("snippet", ""),
        }
        for r in data.get("results", [])
        if isinstance(r, dict) and r.get("url", "").startswith(("https://x.com", "https://twitter.com"))
    ]


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


async def scan_x_serp_signals(tickers: list[str], *, queries_per_run: int = 12) -> list[SocialSignal]:
    """Run a query basket against DataForSEO (primary) + Tavily (fallback).

    Returns deduplicated SocialSignals (by URL). Always returns a list — empty
    when neither provider has credentials.
    """
    if not tickers:
        return []

    all_queries = build_x_queries(tickers)[:queries_per_run]
    if not all_queries:
        return []

    has_dataforseo = _dataforseo_credentials() is not None
    has_tavily = _tavily_key() is not None
    if not has_dataforseo and not has_tavily:
        logger.info("[x_serp] no DataForSEO or Tavily creds — returning []")
        return []

    tasks: list[asyncio.Task] = []
    sources: list[tuple[str, str]] = []  # (query, source)
    for query in all_queries:
        if has_dataforseo:
            tasks.append(asyncio.create_task(_query_dataforseo(query)))
            sources.append((query, "dataforseo"))
        elif has_tavily:
            tasks.append(asyncio.create_task(_query_tavily(query)))
            sources.append((query, "tavily"))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    now = datetime.now(timezone.utc)
    seen_urls: set[str] = set()
    signals: list[SocialSignal] = []
    for (query, source), raw in zip(sources, results):
        if isinstance(raw, Exception) or not raw:
            continue
        for item in raw:
            url = item.get("url", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            blob = f"{item.get('title','')} {item.get('snippet','')}"
            ticker = _extract_ticker(query, tickers)
            signals.append(
                SocialSignal(
                    source=source,
                    query=query,
                    ticker=ticker,
                    title=item.get("title", "")[:200],
                    url=url,
                    snippet=item.get("snippet", "")[:300],
                    observed_at=now,
                    estimated_engagement=None,
                    intent=_classify_intent(blob),
                )
            )
    return signals
