"""Unit tests for review_queue — covers validation, redline gating, and the
Feishu round-trip (bitable_create_record + send_text)."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import pytest

from app.marketing import bitable_fields as bf
from app.marketing.review_queue import (
    ContentDraft,
    ReviewQueueError,
    SubmissionResult,
    submit_to_review,
)


class FakeFeishuClient:
    """Minimal stand-in for FeishuClient — records calls for assertions."""

    def __init__(self) -> None:
        self.records: dict[str, dict[str, Any]] = {}
        self.created_records: list[dict[str, Any]] = []
        self.updated_records: list[dict[str, Any]] = []
        self.sent_messages: list[str] = []
        self.sent_cards: list[dict] = []
        self.config = type("C", (), {"webhook_url": None, "chat_id": "oc_fake"})()
        self._next_id = 1

    def seed_record(self, fields: dict[str, Any]) -> str:
        """Pre-populate a record (simulates a row that already exists in Bitable)."""
        rid = f"recSEED{self._next_id:03d}"
        self._next_id += 1
        self.records[rid] = dict(fields)
        return rid

    def bitable_create_record(self, app_token: str, table_id: str, fields: dict) -> dict:
        rid = f"recFAKE{self._next_id:03d}"
        self._next_id += 1
        self.records[rid] = dict(fields)
        record = {"record_id": rid, "fields": fields}
        self.created_records.append(
            {"app_token": app_token, "table_id": table_id, "fields": fields, "record_id": rid}
        )
        return record

    def bitable_update_record(
        self, app_token: str, table_id: str, record_id: str, fields: dict
    ) -> dict:
        merged = dict(self.records.get(record_id, {}))
        merged.update(fields)
        self.records[record_id] = merged
        self.updated_records.append(
            {"app_token": app_token, "table_id": table_id, "record_id": record_id, "fields": fields}
        )
        return {"record": {"record_id": record_id, "fields": merged}}

    def bitable_search_records(
        self,
        app_token: str,
        table_id: str,
        *,
        filter: dict | None = None,
        page_size: int = 100,
        page_token: str | None = None,
    ) -> dict:
        from app.marketing import bitable_fields as bf_mod

        conditions = (filter or {}).get("conditions", [])
        items: list[dict] = []
        for rid, fields in self.records.items():
            # Mirror the field map so a row stored under either English
            # legacy keys or current Chinese keys can match a filter that
            # references the other naming.
            normalised = bf_mod.normalize_fields(fields)
            matched = True
            for cond in conditions:
                field_name = cond["field_name"]
                operator = cond["operator"]
                wanted = cond["value"]
                actual = normalised.get(field_name)
                if operator == "is":
                    if actual not in wanted:
                        matched = False
                        break
                else:
                    raise NotImplementedError(f"FakeFeishuClient: operator {operator} not supported")
            if matched:
                items.append({"record_id": rid, "fields": fields})
        return {"items": items, "has_more": False, "total": len(items)}

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
    assert fields[bf.CONTENT_ID] == "CT-20260511-NVDA-x"
    assert fields[bf.PLATFORM] == "X"
    assert fields[bf.REVIEW_STATUS] == "Pending"
    assert fields[bf.REDLINE_RESULT] == "Pass"
    assert fields[bf.BODY] == _clean_draft().body
    assert fields[bf.CTA_URL] == {"link": "https://sentinel.ai/stocks/NVDA", "text": "https://sentinel.ai/stocks/NVDA"}

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
    assert fields[bf.REVIEW_STATUS] == "Blocked"
    assert fields[bf.REDLINE_RESULT] == "Blocked"
    assert "forbidden:buy" in fields[bf.REDLINE_HITS]


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
    assert fields[bf.PUBLISH_TIME] == int(ts.timestamp() * 1000)


# ---------------------------------------------------------------------------
# Bitable dedup (候选 5): submit_to_review must upsert by content_id.
# ---------------------------------------------------------------------------


def test_dedup_creates_when_content_id_absent(env: None) -> None:
    fake = FakeFeishuClient()
    submit_to_review(_clean_draft(content_id="CT-20260513-NVDA-tg"), client=fake)
    assert len(fake.created_records) == 1
    assert fake.updated_records == []
    assert fake.created_records[0]["fields"][bf.CONTENT_ID] == "CT-20260513-NVDA-tg"


def test_dedup_updates_when_content_id_exists(env: None) -> None:
    fake = FakeFeishuClient()
    existing_id = fake.seed_record(
        {
            bf.CONTENT_ID: "CT-20260513-NVDA-tg",
            bf.PLATFORM: "Telegram",
            bf.BODY: "stale body",
            bf.REVIEW_STATUS: "Pending",
        }
    )

    result = submit_to_review(
        _clean_draft(content_id="CT-20260513-NVDA-tg", hook="fresh hook"),
        client=fake,
    )

    assert fake.created_records == []
    assert len(fake.updated_records) == 1
    assert fake.updated_records[0]["record_id"] == existing_id
    assert fake.updated_records[0]["fields"][bf.HOOK] == "fresh hook"
    assert result.record_id == existing_id


def test_dedup_filter_uses_chinese_field_key(env: None) -> None:
    fake = FakeFeishuClient()
    captured: list[dict] = []
    original = fake.bitable_search_records

    def spy(app_token: str, table_id: str, **kwargs: Any) -> dict:
        captured.append(kwargs.get("filter") or {})
        return original(app_token, table_id, **kwargs)

    fake.bitable_search_records = spy  # type: ignore[assignment]

    submit_to_review(_clean_draft(content_id="CT-20260513-AMD-tg"), client=fake)

    assert len(captured) == 1
    cond = captured[0]["conditions"][0]
    assert cond["field_name"] == bf.CONTENT_ID  # 内容ID
    assert cond["value"] == ["CT-20260513-AMD-tg"]


def test_dedup_recognises_legacy_english_row(env: None) -> None:
    """A row written by a pre-rename worker (English keys) must still be
    recognised as a duplicate when the new code searches by Chinese key.

    The mirroring is done by `normalize_fields()`, which is the migration
    bridge documented in bitable_fields.py.
    """
    fake = FakeFeishuClient()
    legacy_id = fake.seed_record(
        {
            "content_id": "CT-20260513-TSLA-tg",
            "platform": "Telegram",
            "body": "legacy body",
            "review_status": "Pending",
        }
    )

    submit_to_review(_clean_draft(content_id="CT-20260513-TSLA-tg"), client=fake)

    assert fake.created_records == []
    assert len(fake.updated_records) == 1
    assert fake.updated_records[0]["record_id"] == legacy_id


def test_redline_blocked_still_dedups_into_queue(env: None) -> None:
    """Blocked drafts must still flow through the review queue (so jojo
    can see what got rejected) — and dedup must apply to them too.
    The poller (not submit_to_review) is what guarantees Blocked rows
    never publish; that is asserted in test_marketing_review_poller_publish.py.
    """
    fake = FakeFeishuClient()
    bad_body = "$NVDA strong buy — price target $200. https://x.com\n\nNot financial advice."

    first = submit_to_review(_clean_draft(content_id="CT-DUP-1", body=bad_body), client=fake)
    second = submit_to_review(_clean_draft(content_id="CT-DUP-1", body=bad_body), client=fake)

    assert first.review_status == "Blocked"
    assert second.review_status == "Blocked"
    assert len(fake.created_records) == 1
    assert len(fake.updated_records) == 1
    assert second.record_id == first.record_id
    assert fake.records[first.record_id][bf.REVIEW_STATUS] == "Blocked"


def test_normalize_fields_mirrors_english_to_chinese() -> None:
    """Regression guard for the migration helper: English-only legacy
    rows gain Chinese mirrors so downstream code can look up by either
    name. (Direct unit test, independent of the dedup flow.)"""
    legacy = {"content_id": "CT-1", "platform": "Telegram", "body": "x"}
    mirrored = bf.normalize_fields(legacy)
    assert mirrored[bf.CONTENT_ID] == "CT-1"
    assert mirrored[bf.PLATFORM] == "Telegram"
    assert mirrored[bf.BODY] == "x"
    # Original English keys preserved for backward compatibility.
    assert mirrored["content_id"] == "CT-1"
