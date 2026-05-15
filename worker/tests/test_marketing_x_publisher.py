from __future__ import annotations

import pytest

from app.marketing.publishers.x import XPublisher
from app.marketing.x_client import PostResult


class FakeXClient:
    def __init__(self, result: PostResult) -> None:
        self.result = result
        self.posts: list[str] = []

    async def post(self, text: str) -> PostResult:
        self.posts.append(text)
        return self.result


@pytest.mark.asyncio
async def test_x_publisher_global_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MARKETING_PUBLISH_DRY_RUN", "true")
    monkeypatch.setenv("X_DRY_RUN", "false")
    fake = FakeXClient(PostResult(posted=True, tweet_id="123", text="", dry_run=False))

    result = await XPublisher(client=fake).publish(
        content_id="CT-1",
        ticker="NVDA",
        body="Visual brief: card\n$NVDA risk flag.\n\nContext, not financial advice.",
        cta_url="https://sentinelai.com/stocks/NVDA",
    )

    assert result.dry_run is True
    assert result.published is False
    assert result.published_url == "about:dryrun?platform=X&content_id=CT-1"
    assert fake.posts == []


@pytest.mark.asyncio
async def test_x_publisher_live_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MARKETING_PUBLISH_DRY_RUN", "false")
    monkeypatch.setenv("X_DRY_RUN", "false")
    fake = FakeXClient(PostResult(posted=True, tweet_id="188", text="", dry_run=False))

    result = await XPublisher(client=fake).publish(
        content_id="CT-2",
        ticker="AAPL",
        body="Visual brief: card\n$AAPL risk flag.\n\nContext, not financial advice.",
        cta_url="https://sentinelai.com/stocks/AAPL",
    )

    assert result.published is True
    assert result.published_url == "https://x.com/i/web/status/188"
    assert fake.posts == [
        "$AAPL risk flag.\n\nContext, not financial advice.\n\nhttps://sentinelai.com/stocks/AAPL"
    ]


@pytest.mark.asyncio
async def test_x_publisher_rejects_overlong_body(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MARKETING_PUBLISH_DRY_RUN", "false")
    monkeypatch.setenv("X_DRY_RUN", "false")
    fake = FakeXClient(PostResult(posted=True, tweet_id="188", text="", dry_run=False))

    result = await XPublisher(client=fake).publish(
        content_id="CT-long",
        ticker="TSLA",
        body="x" * 281,
        cta_url="",
    )

    assert result.published is False
    assert result.error == "x_body_too_long:281>280"
    assert fake.posts == []
