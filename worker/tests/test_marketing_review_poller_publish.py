"""Tests for review_poller routing into publishers (Week 4)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.marketing import bitable_fields as bf
from app.marketing.publishers.base import PublishResult
from app.marketing.review_poller import (
    PollResult,
    ReviewPollerError,
    fetch_approved_unpublished,
    run_once,
)


def _run(coro):
    return asyncio.run(coro)


class FakeFeishuClient:
    def __init__(self, *, pages: list[dict] | None = None) -> None:
        self.pages = pages or []
        self.updated_records: list[dict[str, Any]] = []
        self.sent_cards: list[dict] = []
        self.list_calls = 0
        self.config = type("C", (), {"webhook_url": None, "chat_id": "oc_fake"})()

    def bitable_list_records(self, app_token: str, table_id: str, *, page_size: int = 100, page_token: str | None = None) -> dict:
        idx = self.list_calls
        self.list_calls += 1
        if idx < len(self.pages):
            return self.pages[idx]
        return {"items": [], "has_more": False}

    def bitable_update_record(self, app_token: str, table_id: str, record_id: str, fields: dict) -> dict:
        self.updated_records.append({"record_id": record_id, "fields": fields})
        return {"record_id": record_id, "fields": fields}

    def send_card(self, card: dict) -> dict:
        self.sent_cards.append(card)
        return {"code": 0}

    def send_text(self, text: str) -> dict:
        return {"code": 0}


class FakePublisher:
    def __init__(self, platform: str, *, result_factory) -> None:
        self.platform = platform
        self._factory = result_factory
        self.calls: list[dict] = []

    async def publish(self, *, content_id: str, ticker: str, body: str, cta_url: str) -> PublishResult:
        self.calls.append(
            {"content_id": content_id, "ticker": ticker, "body": body, "cta_url": cta_url}
        )
        return self._factory(content_id, ticker)


def _record(
    record_id: str,
    *,
    status: str,
    platform: str = "Telegram",
    redline_result: str = "Pass",
    published_url: object = None,
    content_id: str | None = None,
    ticker: str = "NVDA",
    body: str = "sample body",
    cta_url_dict: object | None = None,
    quality_score: object = 4,
) -> dict:
    """Default quality_score=4 so existing tests behave like before the
    Task 4.2 Approve gate landed. Pass quality_score=None / 0 to verify
    the gate holds the row back."""
    return {
        "record_id": record_id,
        "fields": {
            "content_id": content_id or f"CT-{record_id}",
            "platform": platform,
            "ticker": ticker,
            "review_status": status,
            "redline_result": redline_result,
            "published_url": published_url,
            "body": body,
            "cta_url": cta_url_dict or {"link": "https://sentinel/stocks/NVDA", "text": "https://sentinel/stocks/NVDA"},
            "jojo_quality_score": quality_score,
        },
    }


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FEISHU_BITABLE_APP_TOKEN", "appFAKE")
    monkeypatch.setenv("FEISHU_CONTENT_QUEUE_TABLE_ID", "tblFAKE")


def test_fetch_handles_pagination(env: None) -> None:
    fake = FakeFeishuClient(pages=[
        {"items": [_record("rec1", status="Approved")], "has_more": True, "page_token": "pt2"},
        {"items": [_record("rec2", status="Approved")], "has_more": False},
    ])
    candidates = fetch_approved_unpublished(fake, "appFAKE", "tblFAKE")
    assert [r["record_id"] for r in candidates] == ["rec1", "rec2"]
    assert fake.list_calls == 2


def test_fetch_skips_non_approved_and_already_published(env: None) -> None:
    fake = FakeFeishuClient(pages=[
        {
            "items": [
                _record("rec1", status="Pending"),
                _record("rec2", status="Approved"),
                _record("rec3", status="Approved", published_url={"link": "https://t.me/x/1", "text": "..."}),
                _record("rec4", status="Rejected"),
                _record("rec5", status="Approved"),
            ],
            "has_more": False,
        }
    ])
    out = fetch_approved_unpublished(fake, "appFAKE", "tblFAKE")
    assert [r["record_id"] for r in out] == ["rec2", "rec5"]


def test_redline_blocked_marks_failed_without_publishing(env: None) -> None:
    fake = FakeFeishuClient(pages=[
        {
            "items": [
                _record("recBlock", status="Approved", redline_result="Blocked"),
            ],
            "has_more": False,
        }
    ])
    pub = FakePublisher(
        "Telegram",
        result_factory=lambda cid, t: PublishResult(
            platform="Telegram", content_id=cid, published=True, published_url="https://x", dry_run=False
        ),
    )
    result = _run(run_once(client=fake, publishers={"Telegram": pub}))
    assert result.scanned == 1
    assert result.processed == []
    assert len(result.failed) == 1
    assert pub.calls == []  # publisher MUST NOT be called for redline-blocked
    updated = fake.updated_records[0]
    assert updated["fields"][bf.REVIEW_STATUS] == bf.STATUS_FAILED
    assert "redline_result=Blocked" in updated["fields"][bf.REVIEWER_COMMENT]
    assert fake.sent_cards[0]["header"]["template"] == "red"


def test_telegram_live_publish_marks_published(env: None) -> None:
    fake = FakeFeishuClient(pages=[
        {
            "items": [
                _record("recA", status="Approved", platform="Telegram", content_id="CT-1"),
            ],
            "has_more": False,
        }
    ])
    pub = FakePublisher(
        "Telegram",
        result_factory=lambda cid, t: PublishResult(
            platform="Telegram",
            content_id=cid,
            published=True,
            published_url="https://t.me/SentinelAI_signals/42",
            dry_run=False,
            message_id="42",
        ),
    )
    result = _run(run_once(client=fake, publishers={"Telegram": pub}))
    assert result.scanned == 1
    assert len(result.processed) == 1
    assert result.processed[0]["outcome"] == "published"
    assert pub.calls[0]["content_id"] == "CT-1"

    updated = fake.updated_records[0]
    assert updated["fields"][bf.REVIEW_STATUS] == bf.STATUS_PUBLISHED
    assert updated["fields"][bf.PUBLISHED_URL]["link"] == "https://t.me/SentinelAI_signals/42"
    assert fake.sent_cards[0]["header"]["template"] == "blue"


def test_telegram_publish_failure_marks_failed(env: None) -> None:
    fake = FakeFeishuClient(pages=[
        {"items": [_record("recA", status="Approved", platform="Telegram")], "has_more": False}
    ])
    pub = FakePublisher(
        "Telegram",
        result_factory=lambda cid, t: PublishResult(
            platform="Telegram",
            content_id=cid,
            published=False,
            published_url=None,
            dry_run=False,
            error="telegram 401 unauthorized",
        ),
    )
    result = _run(run_once(client=fake, publishers={"Telegram": pub}))
    assert result.processed == []
    assert len(result.failed) == 1
    updated = fake.updated_records[0]
    assert updated["fields"][bf.REVIEW_STATUS] == bf.STATUS_FAILED
    assert "telegram 401" in updated["fields"][bf.REVIEWER_COMMENT]
    assert fake.sent_cards[0]["header"]["template"] == "red"


def test_telegram_publish_exception_marks_failed(env: None) -> None:
    fake = FakeFeishuClient(pages=[
        {"items": [_record("recA", status="Approved", platform="Telegram")], "has_more": False}
    ])

    class BoomPublisher:
        platform = "Telegram"

        async def publish(self, *, content_id, ticker, body, cta_url):
            raise RuntimeError("publisher crashed")

    result = _run(run_once(client=fake, publishers={"Telegram": BoomPublisher()}))
    assert len(result.failed) == 1
    assert "publisher_exception" in fake.updated_records[0]["fields"][bf.REVIEWER_COMMENT]


def test_missing_platform_publisher_marks_failed(env: None) -> None:
    fake = FakeFeishuClient(pages=[
        {
            "items": [
                _record("recX", status="Approved", platform="X", content_id="CT-x"),
                _record("recY", status="Approved", platform="YouTube Shorts", content_id="CT-y"),
            ],
            "has_more": False,
        }
    ])
    # Only Telegram publisher registered — X / Shorts must fall through to dry-run
    pub = FakePublisher(
        "Telegram",
        result_factory=lambda cid, t: PublishResult(
            platform="Telegram", content_id=cid, published=True, published_url="https://x", dry_run=False
        ),
    )
    result = _run(run_once(client=fake, publishers={"Telegram": pub}))
    assert pub.calls == []  # neither X nor Shorts reached Telegram publisher
    assert result.scanned == 2
    assert result.processed == []
    assert len(result.failed) == 2
    for outcome in result.failed:
        assert outcome["outcome"] == "failed"
        assert outcome["reason"].startswith("missing_publisher:")
    assert len(fake.updated_records) == 2
    for u in fake.updated_records:
        assert u["fields"][bf.REVIEW_STATUS] == bf.STATUS_FAILED
        assert u["fields"][bf.REVIEWER_COMMENT].startswith("[auto] missing_publisher:")


def test_run_once_with_no_publishers_dict_uses_default_registry(env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """If publishers=None, default_publishers() is consulted. Telegram publisher
    in default registry uses MARKETING_PUBLISH_DRY_RUN gate — without override
    it's dry-run, so the record still ends up Published with about:dryrun."""
    monkeypatch.setenv("MARKETING_PUBLISH_DRY_RUN", "true")
    fake = FakeFeishuClient(pages=[
        {"items": [_record("recA", status="Approved", platform="Telegram")], "has_more": False}
    ])
    result = _run(run_once(client=fake, publishers=None))
    assert result.scanned == 1
    assert len(result.processed) == 1
    assert result.processed[0]["outcome"] == "dry_run"


def test_missing_env_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FEISHU_BITABLE_APP_TOKEN", raising=False)
    monkeypatch.delenv("FEISHU_CONTENT_QUEUE_TABLE_ID", raising=False)
    with pytest.raises(ReviewPollerError, match="FEISHU_BITABLE_APP_TOKEN"):
        _run(run_once(client=FakeFeishuClient()))


def test_idempotent_second_run_finds_zero(env: None) -> None:
    """First run publishes; second run sees rec already has published_url and skips."""
    state = {"first_call": True}

    def page_factory():
        if state["first_call"]:
            state["first_call"] = False
            return [
                {
                    "items": [_record("recA", status="Approved", platform="Telegram")],
                    "has_more": False,
                }
            ]
        return [{"items": [], "has_more": False}]

    class StatefulClient(FakeFeishuClient):
        def bitable_list_records(self, *a, **kw):
            return page_factory()[0]

    fake = StatefulClient()
    pub = FakePublisher(
        "Telegram",
        result_factory=lambda cid, t: PublishResult(
            platform="Telegram", content_id=cid, published=True, published_url="https://t.me/x/1", dry_run=False
        ),
    )
    first = _run(run_once(client=fake, publishers={"Telegram": pub}))
    second = _run(run_once(client=fake, publishers={"Telegram": pub}))
    assert first.scanned == 1
    assert second.scanned == 0
    assert len(pub.calls) == 1  # publish only happened once


# ---- Task 4.2: Approve gate (quality_score required) -------------------


@pytest.mark.parametrize("score", [None, 0])
def test_approved_without_quality_score_is_held(env, score) -> None:
    """A row marked Approved but with empty/0 jojo_quality_score must
    be held back from publishing. The gate enforces that every published
    draft carries an explicit operator judgement."""
    fake = FakeFeishuClient(
        pages=[
            {
                "items": [_record("recHELD", status="Approved", quality_score=score)],
                "has_more": False,
            }
        ]
    )
    pub = FakePublisher(
        "Telegram",
        result_factory=lambda cid, t: PublishResult(
            platform="Telegram", content_id=cid, published=True,
            published_url="https://t.me/x/1", dry_run=False,
        ),
    )
    result = _run(run_once(client=fake, publishers={"Telegram": pub}))
    assert result.scanned == 0  # gate filtered out
    assert len(pub.calls) == 0   # no publisher call
    assert len(fake.updated_records) == 0  # no Published status flip


@pytest.mark.parametrize("score", [1, 3, 5])
def test_approved_with_quality_score_publishes(env, score) -> None:
    """1-5 inclusive should let the row through. Specifically guard the
    boundary 1 (lowest valid score)."""
    fake = FakeFeishuClient(
        pages=[
            {
                "items": [_record("recOK", status="Approved", quality_score=score)],
                "has_more": False,
            }
        ]
    )
    pub = FakePublisher(
        "Telegram",
        result_factory=lambda cid, t: PublishResult(
            platform="Telegram", content_id=cid, published=True,
            published_url="https://t.me/x/1", dry_run=False,
        ),
    )
    result = _run(run_once(client=fake, publishers={"Telegram": pub}))
    assert result.scanned == 1
    assert len(pub.calls) == 1


def test_approved_with_string_quality_score_parses(env) -> None:
    """Some Bitable number fields surface as strings via API edge cases.
    The gate should still recognise a numeric string."""
    fake = FakeFeishuClient(
        pages=[
            {
                "items": [_record("recSTR", status="Approved", quality_score="4")],
                "has_more": False,
            }
        ]
    )
    pub = FakePublisher(
        "Telegram",
        result_factory=lambda cid, t: PublishResult(
            platform="Telegram", content_id=cid, published=True,
            published_url="https://t.me/x/1", dry_run=False,
        ),
    )
    result = _run(run_once(client=fake, publishers={"Telegram": pub}))
    assert result.scanned == 1
