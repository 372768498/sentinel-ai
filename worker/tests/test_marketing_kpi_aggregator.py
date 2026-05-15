"""Unit tests for kpi_aggregator — covers rollup math, idempotent upsert,
digest card composition, and Content Queue snapshot."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import pytest

from app.marketing.kpi_aggregator import (
    ContentRollup,
    DigestRunResult,
    DigestSummary,
    aggregate_and_push_digest,
    build_daily_digest_card,
    trading_day_window,
    upsert_performance_row,
)
from app.marketing import bitable_fields as bf


def _run(coro):
    return asyncio.run(coro)


class FakeFeishuClient:
    def __init__(
        self,
        *,
        perf_pages: list[dict] | None = None,
        queue_pages: list[dict] | None = None,
    ) -> None:
        self._perf_pages = perf_pages or [{"items": [], "has_more": False}]
        self._queue_pages = queue_pages or [{"items": [], "has_more": False}]
        self.created: list[dict] = []
        self.updated: list[dict] = []
        self.cards: list[dict] = []
        self._list_calls: dict[str, int] = {}
        self.config = type("C", (), {"webhook_url": None, "chat_id": "oc_fake"})()

    def bitable_list_records(
        self, app_token: str, table_id: str, *, page_size: int = 100, page_token: str | None = None
    ) -> dict:
        idx = self._list_calls.get(table_id, 0)
        self._list_calls[table_id] = idx + 1
        pages = self._perf_pages if table_id == "tblPERF" else self._queue_pages
        return pages[idx] if idx < len(pages) else {"items": [], "has_more": False}

    def bitable_create_record(self, app_token: str, table_id: str, fields: dict) -> dict:
        rec = {"record_id": f"recNEW{len(self.created)+1:03d}", "fields": fields}
        self.created.append({"app_token": app_token, "table_id": table_id, "fields": fields})
        return rec

    def bitable_update_record(self, app_token: str, table_id: str, record_id: str, fields: dict) -> dict:
        self.updated.append({"record_id": record_id, "fields": fields})
        return {"record_id": record_id, "fields": fields}

    def send_card(self, card: dict) -> dict:
        self.cards.append(card)
        return {"code": 0}


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FEISHU_BITABLE_APP_TOKEN", "appFAKE")
    monkeypatch.setenv("FEISHU_PERFORMANCE_TABLE_ID", "tblPERF")
    monkeypatch.setenv("FEISHU_CONTENT_QUEUE_TABLE_ID", "tblQUEUE")


# ---------------------------------------------------------------------------
# ContentRollup math
# ---------------------------------------------------------------------------


def test_rollup_rates() -> None:
    r = ContentRollup(content_id="c1", clicks=100, emails_captured=20, signups=15, paid_users=2)
    assert r.click_to_email_rate == 0.20
    assert r.free_to_paid_rate == 0.10


def test_rollup_rates_zero_division_safe() -> None:
    r = ContentRollup(content_id="c1", clicks=0, emails_captured=0, signups=0, paid_users=0)
    assert r.click_to_email_rate == 0.0
    assert r.free_to_paid_rate == 0.0


def test_digest_top_content_sorts_by_clicks_desc() -> None:
    summary = DigestSummary(
        date_label="2026-05-11",
        rollups=[
            ContentRollup("CT-A", 10, 1, 1, 0),
            ContentRollup("CT-B", 100, 5, 4, 1),
            ContentRollup("CT-C", 50, 8, 7, 0),
        ],
    )
    top = summary.top_content(2)
    assert [r.content_id for r in top] == ["CT-B", "CT-C"]


# ---------------------------------------------------------------------------
# Time window
# ---------------------------------------------------------------------------


def test_trading_day_window_uses_et_timezone() -> None:
    now = datetime(2026, 5, 11, 18, 45, tzinfo=timezone.utc)  # 14:45 ET
    start, end, label = trading_day_window(now)
    assert label == "2026-05-11"
    assert end == now
    # 2026-05-11 is EDT (UTC-4) → 00:00 ET = 04:00 UTC
    assert start == datetime(2026, 5, 11, 4, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Performance upsert
# ---------------------------------------------------------------------------


def test_upsert_creates_when_no_existing(env: None) -> None:
    fake = FakeFeishuClient()
    rollup = ContentRollup("CT-1", 12, 3, 2, 0)
    upsert_performance_row(
        fake, "appFAKE", "tblPERF", rollup, "2026-05-11",
        existing_by_content_id={},
    )
    assert len(fake.created) == 1
    assert fake.created[0]["fields"][bf.PERF_CONTENT_ID] == "CT-1"
    assert fake.created[0]["fields"][bf.PERF_CLICKS] == 12
    assert fake.created[0]["fields"][bf.PERF_NOTES] == "as of 2026-05-11 ET"
    assert fake.updated == []


def test_upsert_updates_when_existing(env: None) -> None:
    fake = FakeFeishuClient()
    rollup = ContentRollup("CT-1", 99, 9, 8, 1)
    upsert_performance_row(
        fake, "appFAKE", "tblPERF", rollup, "2026-05-11",
        existing_by_content_id={"CT-1": "recEXISTING"},
    )
    assert len(fake.updated) == 1
    assert fake.updated[0]["record_id"] == "recEXISTING"
    assert fake.updated[0]["fields"][bf.PERF_CLICKS] == 99
    assert fake.created == []


# ---------------------------------------------------------------------------
# Daily digest card
# ---------------------------------------------------------------------------


def test_build_daily_digest_card_includes_counts_and_top_content() -> None:
    summary = DigestSummary(
        date_label="2026-05-11",
        rollups=[
            ContentRollup("CT-NVDA-x", 300, 18, 14, 1),
            ContentRollup("CT-TSLA-tg", 120, 6, 5, 0),
            ContentRollup("CT-AAPL-yt", 80, 4, 3, 0),
            ContentRollup("CT-MSFT-x", 30, 1, 1, 0),
        ],
        pending_review=4,
        blocked_by_redline=2,
        failed_publish=1,
    )
    card = build_daily_digest_card(summary)

    assert "Daily Growth Digest" in card["header"]["title"]["content"]
    assert card["header"]["template"] == "indigo"

    flat = str(card)
    assert "**Pending Review**\\n4" in flat or "Pending Review" in flat and "4" in flat
    assert "Blocked (Redline)" in flat
    assert "Failed Publish" in flat
    assert "CT-NVDA-x" in flat
    assert "CT-TSLA-tg" in flat
    assert "CT-AAPL-yt" in flat
    # 4th-ranked content should NOT appear (top 3)
    assert "CT-MSFT-x" not in flat
    assert "2026-05-11" in flat


def test_build_daily_digest_card_empty_day() -> None:
    summary = DigestSummary(date_label="2026-05-12")
    card = build_daily_digest_card(summary)
    flat = str(card)
    assert "No content with traffic today" in flat


# ---------------------------------------------------------------------------
# End-to-end orchestrator with injected DB fetcher
# ---------------------------------------------------------------------------


def test_aggregate_and_push_digest_end_to_end(env: None) -> None:
    fake = FakeFeishuClient(
        perf_pages=[
            {
                "items": [
                    {"record_id": "recOLD", "fields": {bf.PERF_CONTENT_ID: "CT-NVDA-x"}},
                ],
                "has_more": False,
            }
        ],
        queue_pages=[
            {
                "items": [
                    {"record_id": "rec1", "fields": {bf.REVIEW_STATUS: "Pending", bf.REDLINE_RESULT: "Pass"}},
                    {"record_id": "rec2", "fields": {bf.REVIEW_STATUS: "Pending", bf.REDLINE_RESULT: "Pass"}},
                    {"record_id": "rec3", "fields": {bf.REVIEW_STATUS: "Failed", bf.REDLINE_RESULT: "Blocked"}},
                    {"record_id": "rec4", "fields": {bf.REVIEW_STATUS: "Approved", bf.REDLINE_RESULT: "Pass"}},
                    {"record_id": "rec5", "fields": {bf.REVIEW_STATUS: "Published", bf.REDLINE_RESULT: "Pass"}},
                ],
                "has_more": False,
            }
        ],
    )

    async def fake_fetcher(start, end):
        return {
            "CT-NVDA-x": {"clicks": 220, "emails_captured": 18, "signups": 14, "paid_users": 1},
            "CT-TSLA-tg": {"clicks": 80, "emails_captured": 5, "signups": 4, "paid_users": 0},
        }

    result = _run(
        aggregate_and_push_digest(
            client=fake,
            db_fetcher=fake_fetcher,
            now=datetime(2026, 5, 11, 18, 45, tzinfo=timezone.utc),
        )
    )

    assert isinstance(result, DigestRunResult)
    assert result.date_label == "2026-05-11"
    assert len(result.rollups) == 2
    # Snapshot counts
    assert result.pending_review == 2
    assert result.blocked_by_redline == 1
    assert result.failed_publish == 1
    # CT-NVDA-x existed → update; CT-TSLA-tg new → create
    assert len(fake.updated) == 1
    assert fake.updated[0]["record_id"] == "recOLD"
    assert len(fake.created) == 1
    assert fake.created[0]["fields"][bf.PERF_CONTENT_ID] == "CT-TSLA-tg"
    # Digest card sent
    assert result.notified is True
    assert len(fake.cards) == 1


def test_aggregate_skips_chat_when_notify_chat_false(env: None) -> None:
    fake = FakeFeishuClient()

    async def fake_fetcher(start, end):
        return {"CT-X": {"clicks": 5, "emails_captured": 0, "signups": 0, "paid_users": 0}}

    result = _run(
        aggregate_and_push_digest(
            client=fake, db_fetcher=fake_fetcher, notify_chat=False
        )
    )
    assert result.notified is False
    assert fake.cards == []
    # Performance upsert still happens
    assert len(fake.created) == 1


def test_aggregate_missing_env_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FEISHU_BITABLE_APP_TOKEN", raising=False)
    monkeypatch.delenv("FEISHU_PERFORMANCE_TABLE_ID", raising=False)
    monkeypatch.delenv("FEISHU_CONTENT_QUEUE_TABLE_ID", raising=False)
    from app.marketing.kpi_aggregator import KPIAggregatorError

    async def fake_fetcher(s, e):
        return {}

    with pytest.raises(KPIAggregatorError, match="Missing FEISHU_BITABLE_APP_TOKEN"):
        _run(aggregate_and_push_digest(client=FakeFeishuClient(), db_fetcher=fake_fetcher))


def test_aggregate_empty_day_produces_zero_rollups(env: None) -> None:
    fake = FakeFeishuClient()

    async def empty_fetcher(s, e):
        return {}

    result = _run(
        aggregate_and_push_digest(
            client=fake, db_fetcher=empty_fetcher,
            now=datetime(2026, 5, 11, 21, 0, tzinfo=timezone.utc),
        )
    )
    assert result.rollups == []
    assert result.performance_rows_upserted == 0
    # Card still sent with "No content with traffic today" message
    assert len(fake.cards) == 1
