"""YouTube Data API v3 adapter for competitor / topic research.

We use search.list (quota-heavy at 100 units per call) sparingly — only a few
queries per day. No upload, no playlist mutation — pure read.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

import httpx

logger = logging.getLogger(__name__)

YT_BASE = "https://www.googleapis.com/youtube/v3"
DEFAULT_TIMEOUT = 12.0


@dataclass(frozen=True)
class YouTubeSignal:
    video_id: str
    title: str
    channel_title: str
    published_at: datetime | None
    view_count: int | None
    like_count: int | None
    comment_count: int | None
    ticker: str | None
    url: str


def _api_key() -> str | None:
    return os.environ.get("YOUTUBE_DATA_API_KEY", "").strip() or None


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def _search_videos(query: str, *, max_results: int = 5) -> list[dict[str, Any]]:
    key = _api_key()
    if key is None:
        return []
    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "order": "viewCount",
        "publishedAfter": (datetime.now(timezone.utc).replace(microsecond=0).isoformat(timespec="seconds")
                          .replace("+00:00", "Z")),
        "maxResults": max_results,
        "key": key,
    }
    # publishedAfter limits to today onwards — we actually want the last 14 days.
    # Override with a 14-day lookback.
    from datetime import timedelta
    params["publishedAfter"] = (
        datetime.now(timezone.utc) - timedelta(days=14)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.get(f"{YT_BASE}/search", params=params)
        if resp.status_code != 200:
            logger.warning("[youtube] search HTTP %s for %r", resp.status_code, query)
            return []
        return resp.json().get("items", [])
    except Exception as exc:
        logger.warning("[youtube] search raised %s", exc)
        return []


async def _fetch_stats(video_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not video_ids:
        return {}
    key = _api_key()
    if key is None:
        return {}
    params = {"part": "statistics", "id": ",".join(video_ids), "key": key}
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.get(f"{YT_BASE}/videos", params=params)
        if resp.status_code != 200:
            return {}
        items = resp.json().get("items", [])
    except Exception as exc:
        logger.warning("[youtube] videos.list raised %s", exc)
        return {}
    return {item["id"]: item.get("statistics", {}) for item in items}


async def search_stock_videos(
    tickers: Iterable[str], *, max_results: int = 5
) -> list[YouTubeSignal]:
    """Search YouTube for `${TICKER} stock analysis` videos in the last 14 days.

    Quota notes: each search.list = 100 units. We cap to top-5 tickers
    per call to stay under the default 10K daily quota.
    """
    if _api_key() is None:
        logger.info("[youtube] YOUTUBE_DATA_API_KEY missing — returning empty list")
        return []

    tickers = [t.upper() for t in list(tickers)[:5]]
    if not tickers:
        return []

    all_items: list[tuple[str, dict[str, Any]]] = []
    for ticker in tickers:
        items = await _search_videos(f"${ticker} stock analysis", max_results=max_results)
        for item in items:
            all_items.append((ticker, item))

    video_ids = [it["id"]["videoId"] for _, it in all_items if "id" in it and "videoId" in it.get("id", {})]
    stats = await _fetch_stats(video_ids)

    signals: list[YouTubeSignal] = []
    for ticker, item in all_items:
        vid = item.get("id", {}).get("videoId")
        if not vid:
            continue
        snippet = item.get("snippet", {})
        stat = stats.get(vid, {})
        signals.append(
            YouTubeSignal(
                video_id=vid,
                title=snippet.get("title", "")[:200],
                channel_title=snippet.get("channelTitle", ""),
                published_at=_parse_iso(snippet.get("publishedAt")),
                view_count=_as_int(stat.get("viewCount")),
                like_count=_as_int(stat.get("likeCount")),
                comment_count=_as_int(stat.get("commentCount")),
                ticker=ticker,
                url=f"https://www.youtube.com/watch?v={vid}",
            )
        )
    return signals
