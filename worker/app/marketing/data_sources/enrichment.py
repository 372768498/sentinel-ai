"""Web-page enrichment adapter for URL → summary.

Primary path: Tavily (existing free tier sufficient for Week 6 needs).
Future fallbacks: Jina Reader (`https://r.jina.ai/{url}`), Firecrawl.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

TAVILY_BASE = "https://api.tavily.com/search"
DEFAULT_TIMEOUT = 15.0


@dataclass(frozen=True)
class SourceSummary:
    url: str
    title: str | None
    summary: str
    source: str  # tavily | jina | firecrawl


def _tavily_key() -> str | None:
    return os.environ.get("TAVILY_API_KEY", "").strip() or None


async def _tavily_summarize(url: str) -> SourceSummary | None:
    key = _tavily_key()
    if key is None:
        return None
    payload = {
        "api_key": key,
        "query": f"summarize the key facts of this URL: {url}",
        "search_depth": "advanced",
        "include_raw_content": False,
        "max_results": 3,
    }
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.post(TAVILY_BASE, json=payload)
        if resp.status_code != 200:
            logger.warning("[enrichment] tavily HTTP %s", resp.status_code)
            return None
        data = resp.json()
    except Exception as exc:
        logger.warning("[enrichment] tavily raised %s", exc)
        return None
    answer = data.get("answer") or ""
    if not answer:
        return None
    return SourceSummary(url=url, title=None, summary=answer[:800], source="tavily")


async def fetch_summaries(urls: list[str], *, limit: int = 5) -> list[SourceSummary]:
    """Summarize up to `limit` URLs. Returns [] when no provider configured.

    Reserved providers (not yet wired): Jina Reader, Firecrawl.
    """
    if not urls:
        return []
    if _tavily_key() is None:
        logger.info("[enrichment] no enrichment provider configured — returning []")
        return []
    out: list[SourceSummary] = []
    for url in urls[:limit]:
        summary = await _tavily_summarize(url)
        if summary is not None:
            out.append(summary)
    return out
