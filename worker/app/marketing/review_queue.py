"""Review Queue · ContentDraft → Feishu Content Queue + bot notification.

Pipeline:

    ContentDraft (Python dataclass)
      → redline.scan()
      → FeishuClient.bitable_create_record(Content Queue)
      → FeishuClient.send_text(review chat)
      → SubmissionResult

Feishu Content Queue is the source of truth for review state. Reviewer toggles
`review_status` in the Bitable UI; a future poller mirrors it back to Prisma
ContentItem.

This module is intentionally stateless — caller decides whether to persist the
returned `record_id` to Postgres (Prisma `ContentItem.feishuRecordId`).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .feishu_client import FeishuAPIError, FeishuClient
from .redline import RedlineResult, scan as redline_scan

ALLOWED_PLATFORMS = ("X", "Telegram", "TikTok", "YouTube Shorts", "YouTube Long", "Email")
ALLOWED_RISK_LEVELS = ("Low", "Medium", "High")


class ReviewQueueError(RuntimeError):
    """Raised when a draft cannot be submitted (validation or upstream error)."""


@dataclass(frozen=True)
class ContentDraft:
    content_id: str
    campaign_id: str
    platform: str
    ticker: str
    hook: str
    body: str
    cta_url: str
    risk_level: str = "Low"
    publish_time: Optional[datetime] = None
    source_opportunity_id: Optional[str] = None

    def validate(self) -> None:
        if self.platform not in ALLOWED_PLATFORMS:
            raise ReviewQueueError(
                f"platform must be one of {ALLOWED_PLATFORMS}, got {self.platform!r}"
            )
        if self.risk_level not in ALLOWED_RISK_LEVELS:
            raise ReviewQueueError(
                f"risk_level must be one of {ALLOWED_RISK_LEVELS}, got {self.risk_level!r}"
            )
        if not self.content_id:
            raise ReviewQueueError("content_id is required")
        if not self.body:
            raise ReviewQueueError("body is required")
        if not self.cta_url.startswith(("http://", "https://")):
            raise ReviewQueueError(f"cta_url must be absolute URL, got {self.cta_url!r}")


@dataclass(frozen=True)
class SubmissionResult:
    record_id: str
    record_url: str
    redline: RedlineResult
    review_status: str  # "Pending" if redline passes, "Blocked" if not


def _fields_payload(draft: ContentDraft, redline: RedlineResult, review_status: str) -> dict:
    from . import bitable_fields as bf

    redline_result = "Pass" if redline.ok else ("Blocked" if not redline.has_source or not redline.has_disclaimer or redline.violations else "Needs Edit")
    if not redline.ok:
        redline_result = "Blocked"

    fields: dict = {
        bf.CONTENT_ID: draft.content_id,
        bf.CAMPAIGN_ID: draft.campaign_id,
        bf.PLATFORM: draft.platform,
        bf.TICKER: draft.ticker,
        bf.HOOK: draft.hook,
        bf.BODY: draft.body,
        bf.CTA_URL: {"link": draft.cta_url, "text": draft.cta_url},
        bf.RISK_LEVEL: draft.risk_level,
        bf.REDLINE_RESULT: redline_result,
        bf.REDLINE_HITS: redline.reason(),
        bf.REVIEW_STATUS: review_status,
    }
    if draft.publish_time is not None:
        ts = draft.publish_time
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        fields[bf.PUBLISH_TIME] = int(ts.timestamp() * 1000)
    return fields


def _record_url(app_token: str, table_id: str, record_id: str) -> str:
    host = os.environ.get("FEISHU_HOST", "https://bq66x8yqgk.feishu.cn")
    return f"{host}/base/{app_token}?table={table_id}&view=&record={record_id}"


def _build_review_card(
    draft: ContentDraft,
    redline: RedlineResult,
    review_status: str,
    record_url: str,
) -> dict:
    """Build an interactive Feishu card with action buttons.

    Buttons:
      - Open in Bitable → jumps to the record so reviewer can change `review_status`
      - Preview Stock Page → opens the CTA URL (with UTM)
    """
    body_preview = draft.body if len(draft.body) <= 400 else draft.body[:397] + "..."
    template = "green" if review_status == "Pending" else "red"
    redline_label = "Pass ✅" if redline.ok else f"Blocked ❌ — {redline.reason()}"

    return {
        "config": {"wide_screen_mode": True, "enable_forward": True},
        "header": {
            "title": {
                "tag": "plain_text",
                "content": f"Sentinel AI · Review Needed — ${draft.ticker}",
            },
            "template": template,
        },
        "elements": [
            {
                "tag": "div",
                "fields": [
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**Platform**\n{draft.platform}"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**Risk**\n{draft.risk_level}"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**Redline**\n{redline_label}"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**Status**\n{review_status}"}},
                ],
            },
            {"tag": "hr"},
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**Hook**\n{draft.hook}"}},
            {"tag": "hr"},
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**Body preview**\n{body_preview}"}},
            {"tag": "hr"},
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "Open in Bitable →"},
                        "type": "primary",
                        "multi_url": {
                            "url": record_url,
                            "pc_url": record_url,
                            "android_url": record_url,
                            "ios_url": record_url,
                        },
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "Preview Stock Page"},
                        "type": "default",
                        "multi_url": {
                            "url": draft.cta_url,
                            "pc_url": draft.cta_url,
                            "android_url": draft.cta_url,
                            "ios_url": draft.cta_url,
                        },
                    },
                ],
            },
            {
                "tag": "note",
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": "In Bitable, change `review_status` to Approved or Rejected to advance.",
                    }
                ],
            },
            {
                "tag": "note",
                "elements": [{"tag": "plain_text", "content": f"content_id: {draft.content_id}"}],
            },
        ],
    }


def submit_to_review(
    draft: ContentDraft,
    *,
    client: Optional[FeishuClient] = None,
    notify_chat: bool = True,
) -> SubmissionResult:
    """Submit a draft to the Feishu review queue.

    1. Validate draft shape.
    2. Run redline scan.
    3. Write a record to the Content Queue table (review_status=Pending if
       redline passes, Blocked otherwise).
    4. Post a notification message to the review chat (unless `notify_chat=False`).
    """
    draft.validate()

    app_token = os.environ.get("FEISHU_BITABLE_APP_TOKEN", "").strip()
    table_id = os.environ.get("FEISHU_CONTENT_QUEUE_TABLE_ID", "").strip()
    if not app_token or not table_id:
        raise ReviewQueueError(
            "FEISHU_BITABLE_APP_TOKEN and FEISHU_CONTENT_QUEUE_TABLE_ID must be set"
        )

    redline = redline_scan(draft.body)
    review_status = "Pending" if redline.ok else "Blocked"

    fb = client or FeishuClient()
    fields = _fields_payload(draft, redline, review_status)

    try:
        record = fb.bitable_create_record(app_token, table_id, fields)
    except FeishuAPIError as exc:
        raise ReviewQueueError(f"Feishu create_record failed: {exc}") from exc

    record_id = record["record_id"]
    record_url = _record_url(app_token, table_id, record_id)

    if notify_chat:
        try:
            card = _build_review_card(draft, redline, review_status, record_url)
            fb.send_card(card)
        except FeishuAPIError as exc:
            raise ReviewQueueError(
                f"Record {record_id} created but chat notification failed: {exc}"
            ) from exc

    return SubmissionResult(
        record_id=record_id,
        record_url=record_url,
        redline=redline,
        review_status=review_status,
    )


async def submit_draft_to_review(
    draft: ContentDraft,
    *,
    client: Optional[FeishuClient] = None,
    notify_chat: bool = True,
) -> SubmissionResult:
    """Async wrapper around `submit_to_review` for use inside async pipelines.

    Feishu API calls themselves are sync (httpx.Client), so this runs the
    submission in the default thread executor.
    """
    import asyncio

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, lambda: submit_to_review(draft, client=client, notify_chat=notify_chat)
    )
