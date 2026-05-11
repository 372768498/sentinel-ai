"""Read-only X intel: monitor $TICKER discussions, surface KOL candidates.

Uses Bearer Token (OAuth 2.0 App-only). Free tier: 1 request / 15 sec, 60 reqs/15-min.
Sentinel typical use: 1 query per qualified ticker per session = 3-5 reqs/session.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from .x_client import XClient

logger = logging.getLogger(__name__)


@dataclass
class TickerBuzz:
    ticker: str
    sample_count: int
    top_engagement: list[dict]  # tweets sorted by like_count desc

    def kol_author_ids(self, *, min_likes: int = 10) -> list[str]:
        return [
            t["author_id"]
            for t in self.top_engagement
            if t["author_id"] and t.get("metrics", {}).get("like_count", 0) >= min_likes
        ]


async def measure_ticker_buzz(
    ticker: str,
    *,
    client: Optional[XClient] = None,
    max_results: int = 30,
) -> TickerBuzz:
    """Fetch recent $TICKER mentions, sorted by engagement."""
    client = client or XClient()
    query = f"${ticker} -is:retweet lang:en"
    tweets = await client.search(query, max_results=max_results)
    sorted_by_likes = sorted(
        tweets,
        key=lambda t: t.get("metrics", {}).get("like_count", 0),
        reverse=True,
    )
    return TickerBuzz(
        ticker=ticker,
        sample_count=len(tweets),
        top_engagement=sorted_by_likes[:10],
    )
