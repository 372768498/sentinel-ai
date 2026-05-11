"""Tests for the read-only X intel module — Bearer-token search wrapper."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.marketing.intel import TickerBuzz, measure_ticker_buzz
from app.marketing.x_client import XClient


def _fake_tweet(*, author_id: str, likes: int, text: str = "x"):
    return {
        "id": "1",
        "text": text,
        "author_id": author_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "metrics": {"like_count": likes},
    }


@pytest.mark.asyncio
async def test_buzz_sorts_by_likes(monkeypatch):
    client = XClient(dry_run=False, bearer_token="dummy")

    async def _fake_search(self, query, *, max_results=20):
        assert "$NVDA" in query
        return [
            _fake_tweet(author_id="A", likes=2),
            _fake_tweet(author_id="B", likes=50),
            _fake_tweet(author_id="C", likes=15),
        ]

    monkeypatch.setattr(XClient, "search", _fake_search)
    buzz = await measure_ticker_buzz("NVDA", client=client)
    likes = [t["metrics"]["like_count"] for t in buzz.top_engagement]
    assert likes == [50, 15, 2]
    assert buzz.sample_count == 3


@pytest.mark.asyncio
async def test_kol_filter(monkeypatch):
    client = XClient(dry_run=False, bearer_token="dummy")

    async def _fake_search(self, query, *, max_results=20):
        return [
            _fake_tweet(author_id="A", likes=2),
            _fake_tweet(author_id="B", likes=50),
            _fake_tweet(author_id="C", likes=15),
        ]

    monkeypatch.setattr(XClient, "search", _fake_search)
    buzz = await measure_ticker_buzz("NVDA", client=client)
    kol_ids = buzz.kol_author_ids(min_likes=10)
    assert kol_ids == ["B", "C"]


@pytest.mark.asyncio
async def test_dry_run_returns_empty():
    client = XClient(dry_run=True, bearer_token="dummy")
    buzz = await measure_ticker_buzz("NVDA", client=client)
    assert buzz.sample_count == 0
    assert buzz.top_engagement == []


@pytest.mark.asyncio
async def test_no_bearer_returns_empty():
    client = XClient(dry_run=False)  # no creds at all
    client.bearer_token = None
    buzz = await measure_ticker_buzz("NVDA", client=client)
    assert buzz.sample_count == 0
