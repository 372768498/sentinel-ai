"""Unit tests for review_queue — covers validation, redline gating, and the
Feishu round-trip (bitable_create_record + send_text)."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import pytest

from app.marketing.review_queue import (
    ContentDraft,
    ReviewQueueError,
    SubmissionResult,
    submit_to_review,
)


class FakeFeishuClient:
    """Minimal stand-in for FeishuClient — records calls for assertions."""

    def __init__(self) -> None:
        self.created_records: list[dict[str, Any]] = []
        self.sent_messages: list[str] = []
        self.sent_cards: list[dict] = []
        self.config = type("C", (), {"webhook_url": None, "chat_id": "oc_fake"})()

    def bitable_create_record(self, app_token: str, table_id: str, fields: dict) -> dict:
        record = {"record_id": f"recFAKE{len(self.created_records) + 1:03d}", "fields": fields}
        self.created_records.append({"app_token": app_token, "table_id": table_id, "fields": fields})
        return record

    def send_text(self, text: str) -> dict:
        self.sent_messages.append(text)
        return {"code": 0, "msg": "ok"}

    def send_card(self, card: dict) -> dict:
        self.sent_cards.append(card)
        return {"code": 0, "msg": "ok"}


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FEISHU_BITABLE_APP_TOKEN", "appFAKE")
    monkeypatch.setenv("FEISHU_CONTENT_QUEUE_TABLE_ID", "tblFAKE")


def _clean_draft(**overrides: Any) -> ContentDraft:
    defaults: dict[str, Any] = dict(
        content_id="CT-20260511-NVDA-x",
        campaign_id="CMP-20260511-01",
        platform="X",
        ticker="NVDA",
        hook="$NVDA Sentinel AI score 78/100 — one risk stands out.",
        body=(
            "$NVDA Sentinel AI score 78/100 (SOLID).\n"
            "Margins expanded. Main risk flag: export restrictions.\n"
            "https://sentinel.ai/stocks/NVDA\n\n"
            "Context, not financial advice."
        ),
        cta_url="https://sentinel.ai/stocks/NVDA",
        risk_level="Medium",
    )
    defaults.update(overrides)
    return ContentDraft(**defaults)


def test_clean_draft_passes_and_posts(env: None) -> None:
    fake = FakeFeishuClient()
    result = submit_to_review(_clean_draft(), client=fake)

    assert isinstance(result, SubmissionResult)
    assert result.review_status == "Pending"
    assert result.redline.ok
    assert result.record_id.startswith("recFAKE")
    assert len(fake.created_records) == 1
    assert len(fake.sent_cards) == 1
    assert fake.sent_messages == []

    fields = fake.created_records[0]["fields"]
    assert fields["content_id"] == "CT-20260511-NVDA-x"
    assert fields["platform"] == "X"
    assert fields["review_status"] == "Pending"
    assert fields["redline_result"] == "Pass"
    assert fields["cta_url"] == {"link": "https://sentinel.ai/stocks/NVDA", "text": "https://sentinel.ai/stocks/NVDA"}

    card = fake.sent_cards[0]
    assert card["header"]["template"] == "green"
    assert "$NVDA" in card["header"]["title"]["content"]
    action_buttons = next(el for el in card["elements"] if el.get("tag") == "action")["actions"]
    button_labels = [b["text"]["content"] for b in action_buttons]
    assert "Open in Bitable →" in button_labels
    assert "Preview Stock Page" in button_labels


def test_redline_block_writes_record_with_blocked_status(env: None) -> None:
    fake = FakeFeishuClient()
    bad = _clean_draft(body=(
        "$NVDA strong buy — price target $200. https://x.com\n\nNot financial advice."
    ))
    result = submit_to_review(bad, client=fake)

    assert result.review_status == "Blocked"
    assert not result.redline.ok
    assert "forbidden:buy" in result.redline.violations
    assert "forbidden:price target" in result.redline.violations
    fields = fake.created_records[0]["fields"]
    assert fields["review_status"] == "Blocked"
    assert fields["redline_result"] == "Blocked"
    assert "forbidden:buy" in fields["redline_hits"]


def test_invalid_platform_raises(env: None) -> None:
    fake = FakeFeishuClient()
    with pytest.raises(ReviewQueueError, match="platform must be one of"):
        submit_to_review(_clean_draft(platform="Mastodon"), client=fake)
    assert fake.created_records == []


def test_invalid_risk_level_raises(env: None) -> None:
    fake = FakeFeishuClient()
    with pytest.raises(ReviewQueueError, match="risk_level must be one of"):
        submit_to_review(_clean_draft(risk_level="Severe"), client=fake)


def test_missing_cta_url_scheme_raises(env: None) -> None:
    fake = FakeFeishuClient()
    with pytest.raises(ReviewQueueError, match="cta_url must be absolute URL"):
        submit_to_review(_clean_draft(cta_url="/stocks/NVDA"), client=fake)


def test_missing_env_vars_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FEISHU_BITABLE_APP_TOKEN", raising=False)
    monkeypatch.delenv("FEISHU_CONTENT_QUEUE_TABLE_ID", raising=False)
    fake = FakeFeishuClient()
    with pytest.raises(ReviewQueueError, match="FEISHU_BITABLE_APP_TOKEN"):
        submit_to_review(_clean_draft(), client=fake)


def test_notify_chat_false_skips_send(env: None) -> None:
    fake = FakeFeishuClient()
    submit_to_review(_clean_draft(), client=fake, notify_chat=False)
    assert len(fake.created_records) == 1
    assert fake.sent_cards == []
    assert fake.sent_messages == []


def test_blocked_card_uses_red_template(env: None) -> None:
    fake = FakeFeishuClient()
    bad = _clean_draft(body="$NVDA buy now! https://x.com\n\nNot financial advice.")
    submit_to_review(bad, client=fake)
    card = fake.sent_cards[0]
    assert card["header"]["template"] == "red"


def test_publish_time_serialised_to_millis(env: None) -> None:
    fake = FakeFeishuClient()
    ts = datetime(2026, 5, 11, 13, 0, tzinfo=timezone.utc)
    submit_to_review(_clean_draft(publish_time=ts), client=fake)
    fields = fake.created_records[0]["fields"]
    assert fields["publish_time"] == int(ts.timestamp() * 1000)
