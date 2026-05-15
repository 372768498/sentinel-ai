"""KPI aggregator · Week 5.

Pipeline (typically runs once per US trading day, post-close 16:30 ET):

    fetch_all_metrics(start, end)        # from Postgres VisitEvent / EmailLead
        ↓
    enrich with Feishu Content Queue snapshot (pending, blocked counts)
        ↓
    upsert rows into Feishu Performance table  (idempotent by content_id)
        ↓
    push Daily Growth Digest card to the review chat

KPI shape per content_id:
  - clicks              (VisitEvent count, date-windowed)
  - emails_captured     (EmailLead count, date-windowed)
  - signups             (EmailLead.verifiedAt IS NOT NULL, date-windowed)
  - paid_users          (linked User has ACTIVE+PRO sub, all-time attribution)
  - click_to_email_rate (emails_captured / clicks)
  - free_to_paid_rate   (paid_users / emails_captured)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from .feishu_client import FeishuAPIError, FeishuClient
from .kpi_db import KPIDBError, fetch_all_metrics

logger = logging.getLogger(__name__)

ET_TZ = ZoneInfo("America/New_York")


class KPIAggregatorError(RuntimeError):
    pass


@dataclass(frozen=True)
class ContentRollup:
    content_id: str
    clicks: int
    emails_captured: int
    signups: int
    paid_users: int

    @property
    def click_to_email_rate(self) -> float:
        return self.emails_captured / self.clicks if self.clicks > 0 else 0.0

    @property
    def free_to_paid_rate(self) -> float:
        return self.paid_users / self.emails_captured if self.emails_captured > 0 else 0.0


@dataclass
class DigestSummary:
    date_label: str
    rollups: list[ContentRollup] = field(default_factory=list)
    pending_review: int = 0
    blocked_by_redline: int = 0
    failed_publish: int = 0

    def top_content(self, limit: int = 3) -> list[ContentRollup]:
        return sorted(
            self.rollups,
            key=lambda r: (-r.clicks, -r.emails_captured, r.content_id),
        )[:limit]


# ---------------------------------------------------------------------------
# Time-window helpers
# ---------------------------------------------------------------------------


def trading_day_window(now: Optional[datetime] = None) -> tuple[datetime, datetime, str]:
    """Window covering 'today' in America/New_York — 00:00 ET → now (or 23:59 if
    in the past). Returns (start_utc, end_utc, label='YYYY-MM-DD').
    """
    now_utc = now.astimezone(timezone.utc) if now else datetime.now(timezone.utc)
    now_et = now_utc.astimezone(ET_TZ)
    start_et = now_et.replace(hour=0, minute=0, second=0, microsecond=0)
    start_utc = start_et.astimezone(timezone.utc)
    end_utc = now_utc
    return start_utc, end_utc, start_et.strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Feishu Performance upsert
# ---------------------------------------------------------------------------


def _performance_fields(rollup: ContentRollup, date_label: str) -> dict:
    from . import bitable_fields as bf

    return {
        bf.PERF_CONTENT_ID: rollup.content_id,
        bf.PERF_CLICKS: rollup.clicks,
        bf.PERF_EMAILS_CAPTURED: rollup.emails_captured,
        bf.PERF_SIGNUPS: rollup.signups,
        bf.PERF_PAID_USERS: rollup.paid_users,
        bf.PERF_CLICK_TO_EMAIL_RATE: round(rollup.click_to_email_rate, 4),
        bf.PERF_FREE_TO_PAID_RATE: round(rollup.free_to_paid_rate, 4),
        bf.PERF_NOTES: f"as of {date_label} ET",
    }


def upsert_performance_row(
    client: FeishuClient,
    app_token: str,
    table_id: str,
    rollup: ContentRollup,
    date_label: str,
    *,
    existing_by_content_id: dict[str, str],
) -> str:
    """Insert or update one Performance row, keyed by content_id.

    `existing_by_content_id` is a pre-fetched map content_id → record_id to
    avoid an N+1 list call per row.
    """
    fields = _performance_fields(rollup, date_label)
    record_id = existing_by_content_id.get(rollup.content_id)
    if record_id:
        client.bitable_update_record(app_token, table_id, record_id, fields)
        return record_id
    record = client.bitable_create_record(app_token, table_id, fields)
    return record["record_id"]


def _list_performance_index(
    client: FeishuClient, app_token: str, table_id: str
) -> dict[str, str]:
    out: dict[str, str] = {}
    page_token: Optional[str] = None
    while True:
        page = client.bitable_list_records(
            app_token, table_id, page_size=100, page_token=page_token
        )
        for record in page.get("items", []):
            from . import bitable_fields as bf

            fields = bf.normalize_fields(record.get("fields", {}))
            content_id = fields.get(bf.PERF_CONTENT_ID)
            if isinstance(content_id, list):
                # multi-text field shape
                content_id = "".join(
                    seg.get("text", "") for seg in content_id if isinstance(seg, dict)
                )
            if content_id:
                out[content_id] = record["record_id"]
        if not page.get("has_more"):
            break
        page_token = page.get("page_token")
        if not page_token:
            break
    return out


def _scan_content_queue_snapshot(
    client: FeishuClient, app_token: str, content_queue_table_id: str
) -> tuple[int, int, int]:
    """Return (pending_review, blocked_by_redline, failed_publish) snapshot."""
    pending = 0
    blocked = 0
    failed = 0
    page_token: Optional[str] = None
    while True:
        page = client.bitable_list_records(
            app_token, content_queue_table_id, page_size=100, page_token=page_token
        )
        for record in page.get("items", []):
            from . import bitable_fields as bf

            fields = bf.normalize_fields(record.get("fields", {}))
            status = bf.normalize_review_status(_read_text(fields.get(bf.REVIEW_STATUS)))
            redline = _read_text(fields.get(bf.REDLINE_RESULT))
            if status == bf.STATUS_PENDING:
                pending += 1
            if status == bf.STATUS_FAILED:
                failed += 1
            if redline == "Blocked":
                blocked += 1
        if not page.get("has_more"):
            break
        page_token = page.get("page_token")
        if not page_token:
            break
    return pending, blocked, failed


def _read_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(
            seg.get("text", "") if isinstance(seg, dict) else str(seg) for seg in value
        )
    if isinstance(value, dict):
        return value.get("text", "") or value.get("value", "") or ""
    return str(value)


# ---------------------------------------------------------------------------
# Daily Digest card
# ---------------------------------------------------------------------------


def _format_rollup_line(r: ContentRollup) -> str:
    return (
        f"**{r.content_id}**\n"
        f"Clicks: {r.clicks} · Emails: {r.emails_captured} · "
        f"Signups: {r.signups} · Paid: {r.paid_users}"
    )


def build_daily_digest_card(summary: DigestSummary) -> dict:
    top = summary.top_content(3)
    if top:
        top_blocks = [
            {"tag": "div", "text": {"tag": "lark_md", "content": _format_rollup_line(r)}}
            for r in top
        ]
    else:
        top_blocks = [
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": "_No content with traffic today._"},
            }
        ]

    elements: list[dict] = [
        {
            "tag": "div",
            "fields": [
                {"is_short": True, "text": {"tag": "lark_md", "content": f"**Pending Review**\n{summary.pending_review}"}},
                {"is_short": True, "text": {"tag": "lark_md", "content": f"**Blocked (Redline)**\n{summary.blocked_by_redline}"}},
                {"is_short": True, "text": {"tag": "lark_md", "content": f"**Failed Publish**\n{summary.failed_publish}"}},
                {"is_short": True, "text": {"tag": "lark_md", "content": f"**Total Tracked**\n{len(summary.rollups)}"}},
            ],
        },
        {"tag": "hr"},
        {"tag": "div", "text": {"tag": "lark_md", "content": "**Top Content**"}},
    ]
    elements.extend(top_blocks)
    elements.append(
        {
            "tag": "note",
            "elements": [{"tag": "plain_text", "content": f"Window: {summary.date_label} (ET)"}],
        }
    )
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "Sentinel AI · Daily Growth Digest"},
            "template": "indigo",
        },
        "elements": elements,
    }


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


@dataclass
class DigestRunResult:
    date_label: str
    rollups: list[ContentRollup]
    pending_review: int
    blocked_by_redline: int
    failed_publish: int
    performance_rows_upserted: int
    notified: bool


async def aggregate_and_push_digest(
    *,
    client: Optional[FeishuClient] = None,
    db_fetcher=fetch_all_metrics,
    notify_chat: bool = True,
    now: Optional[datetime] = None,
) -> DigestRunResult:
    """End-to-end Week 5 entry point.

    Side effects:
      1. Reads VisitEvent / EmailLead / SubscriptionStatus from Postgres.
      2. Reads Feishu Content Queue for pending/blocked snapshot.
      3. Upserts Feishu Performance table by content_id.
      4. Pushes a Daily Growth Digest card to the review chat.

    `db_fetcher` is injectable so tests can avoid spinning up Postgres.
    """
    app_token = os.environ.get("FEISHU_BITABLE_APP_TOKEN", "").strip()
    perf_table = os.environ.get("FEISHU_PERFORMANCE_TABLE_ID", "").strip()
    queue_table = os.environ.get("FEISHU_CONTENT_QUEUE_TABLE_ID", "").strip()
    if not app_token or not perf_table or not queue_table:
        raise KPIAggregatorError(
            "Missing FEISHU_BITABLE_APP_TOKEN / FEISHU_PERFORMANCE_TABLE_ID / "
            "FEISHU_CONTENT_QUEUE_TABLE_ID — set them in .env.local"
        )

    fb = client or FeishuClient()

    start, end, date_label = trading_day_window(now)
    logger.info(
        "[kpi_aggregator] run start — date=%s window=%s→%s notify_chat=%s",
        date_label,
        start.isoformat(),
        end.isoformat(),
        notify_chat,
    )
    try:
        metrics = await db_fetcher(start, end)
    except KPIDBError as exc:
        raise KPIAggregatorError(f"DB fetch failed: {exc}") from exc

    rollups = [
        ContentRollup(
            content_id=cid,
            clicks=m["clicks"],
            emails_captured=m["emails_captured"],
            signups=m["signups"],
            paid_users=m["paid_users"],
        )
        for cid, m in metrics.items()
    ]

    try:
        existing = _list_performance_index(fb, app_token, perf_table)
        pending, blocked, failed = _scan_content_queue_snapshot(fb, app_token, queue_table)
    except FeishuAPIError as exc:
        raise KPIAggregatorError(f"Feishu read failed: {exc}") from exc

    upserted = 0
    for rollup in rollups:
        try:
            upsert_performance_row(
                fb, app_token, perf_table, rollup, date_label,
                existing_by_content_id=existing,
            )
            upserted += 1
        except FeishuAPIError as exc:
            logger.warning("[kpi_aggregator] upsert failed for %s: %s", rollup.content_id, exc)

    summary = DigestSummary(
        date_label=date_label,
        rollups=rollups,
        pending_review=pending,
        blocked_by_redline=blocked,
        failed_publish=failed,
    )

    notified = False
    if notify_chat:
        try:
            fb.send_card(build_daily_digest_card(summary))
            notified = True
        except FeishuAPIError as exc:
            logger.warning("[kpi_aggregator] digest send failed: %s", exc)

    logger.info(
        "[kpi_aggregator] run done — date=%s rollups=%d upserted=%d pending=%d "
        "blocked=%d failed_publish=%d notified=%s",
        date_label,
        len(rollups),
        upserted,
        pending,
        blocked,
        failed,
        notified,
    )
    return DigestRunResult(
        date_label=date_label,
        rollups=rollups,
        pending_review=pending,
        blocked_by_redline=blocked,
        failed_publish=failed,
        performance_rows_upserted=upserted,
        notified=notified,
    )
