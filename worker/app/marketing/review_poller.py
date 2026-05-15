"""Review Poller - Layer 3 to Layer 4 handoff.

Polls the Feishu Content Queue Bitable for records where
`review_status = Approved` AND `published_url` is empty, then dispatches each
to its platform publisher.

Routing rules:
  - `redline_result = Blocked`: mark Failed, never publish.
  - Registered platform publisher: call `publisher.publish(...)`;
                                          live=Published, error=Failed
  - Missing platform publisher: mark Failed with `missing_publisher:*`.
  - `MARKETING_PUBLISH_DRY_RUN=true`: registered publishers dry-run safely.

Idempotency: a record with `review_status = Published` or non-empty
`published_url` is skipped on the next poll.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

from .feishu_client import FeishuAPIError, FeishuClient
from .publishers import (
    BasePublisher,
    PublishResult,
    TelegramPublisher,
    XPublisher,
)

logger = logging.getLogger(__name__)


class ReviewPollerError(RuntimeError):
    pass


@dataclass
class PollResult:
    scanned: int = 0
    processed: list[dict] = field(default_factory=list)
    failed: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)


PublisherRegistry = dict[str, BasePublisher]


def default_publishers() -> PublisherRegistry:
    """Construct the platform->publisher map used by the production scheduler.

    X and Telegram have live-capable publishers today. Reddit / TikTok /
    YouTube are intentionally not registered until their official adapters
    land; approving those rows marks them Failed instead of fake-published.
    """
    return {"Telegram": TelegramPublisher(), "X": XPublisher()}


# ---------------------------------------------------------------------------
# Bitable field helpers (single-select / text / url come back in different
# shapes depending on whether the row was created via OpenAPI or edited in UI).
# ---------------------------------------------------------------------------


def _read_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for seg in value:
            if isinstance(seg, dict):
                parts.append(seg.get("text", "") or "")
            else:
                parts.append(str(seg))
        return "".join(parts)
    if isinstance(value, dict):
        return value.get("text", "") or value.get("value", "") or ""
    return str(value)


def _read_url(value: object) -> str:
    if isinstance(value, dict):
        return value.get("link", "") or ""
    if isinstance(value, str):
        return value
    return ""


def _is_empty_url(value: object) -> bool:
    if not value:
        return True
    if isinstance(value, dict):
        return not value.get("link")
    if isinstance(value, str):
        return value.strip() == ""
    return False


def _has_quality_score(value: object) -> bool:
    """True when Operator-jojo has filled a 1-5 quality score on this row.

    Bitable number fields come back as int / float; missing is None.
    Zero is treated as "not yet scored" so the gate doesn't accidentally
    let a user-typed 0 through (we don't expose 0 as a valid score).
    """
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value > 0
    if isinstance(value, str):
        try:
            return float(value.strip()) > 0
        except (TypeError, ValueError):
            return False
    return False


# ---------------------------------------------------------------------------
# Bitable I/O
# ---------------------------------------------------------------------------


def fetch_approved_unpublished(client: FeishuClient, app_token: str, table_id: str) -> list[dict]:
    """Return Approved rows that are unpublished AND have a quality score.

    Approve gate (Task 4.2): a draft whose review_status flipped to
    Approved but has an empty jojo_quality_score field is held back
    until the operator fills the score. We never publish without an
    explicit numeric judgement on the row. Held rows aren't auto-
    rejected - they just sit in the queue so the operator notices.
    """
    page_token: Optional[str] = None
    out: list[dict] = []
    while True:
        page = client.bitable_list_records(
            app_token, table_id, page_size=100, page_token=page_token
        )
        for record in page.get("items", []):
            from . import bitable_fields as bf
            fields = bf.normalize_fields(record.get("fields", {}))
            if _read_text(fields.get(bf.REVIEW_STATUS)) != "Approved":
                continue
            if not _is_empty_url(fields.get(bf.PUBLISHED_URL)):
                continue
            if not _has_quality_score(fields.get(bf.QUALITY_SCORE)):
                continue
            out.append(record)
        if not page.get("has_more"):
            break
        page_token = page.get("page_token")
        if not page_token:
            break
    return out


# ---------------------------------------------------------------------------
# Notification cards
# ---------------------------------------------------------------------------


def _published_card(
    content_id: str, platform: str, ticker: str, published_url: str, dry_run: bool
) -> dict:
    template = "blue" if not dry_run else "grey"
    title_prefix = "Sentinel AI - Published" if not dry_run else "Sentinel AI - Published (dry-run)"
    button_label = "Open Published URL" if not dry_run else "View dry-run URL"
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"{title_prefix} - ${ticker}"},
            "template": template,
        },
        "elements": [
            {
                "tag": "div",
                "fields": [
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**Platform**\n{platform}"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**Ticker**\n${ticker}"}},
                ],
            },
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**content_id**\n{content_id}"}},
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": button_label},
                        "type": "primary" if not dry_run else "default",
                        "multi_url": {
                            "url": published_url,
                            "pc_url": published_url,
                            "android_url": published_url,
                            "ios_url": published_url,
                        },
                    }
                ],
            },
        ],
    }


def _failed_card(content_id: str, platform: str, ticker: str, reason: str) -> dict:
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"Sentinel AI - Publish Failed - ${ticker}"},
            "template": "red",
        },
        "elements": [
            {
                "tag": "div",
                "fields": [
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**Platform**\n{platform}"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**content_id**\n{content_id}"}},
                ],
            },
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**Failure**\n{reason}"}},
            {
                "tag": "note",
                "elements": [
                    {"tag": "plain_text", "content": "Bitable row marked Failed. Fix and re-Approve to retry."}
                ],
            },
        ],
    }


# ---------------------------------------------------------------------------
# Per-record processing
# ---------------------------------------------------------------------------


def _mark_failed(
    client: FeishuClient,
    app_token: str,
    table_id: str,
    record_id: str,
    reason: str,
) -> None:
    from . import bitable_fields as bf
    client.bitable_update_record(
        app_token,
        table_id,
        record_id,
        {
            bf.REVIEW_STATUS: "Failed",
            bf.REVIEWER_COMMENT: f"[auto] {reason[:480]}",
        },
    )


def _mark_published(
    client: FeishuClient,
    app_token: str,
    table_id: str,
    record_id: str,
    published_url: str,
) -> None:
    from . import bitable_fields as bf
    client.bitable_update_record(
        app_token,
        table_id,
        record_id,
        {
            bf.REVIEW_STATUS: "Published",
            bf.PUBLISHED_URL: {"link": published_url, "text": published_url},
            bf.PUBLISH_TIME: int(datetime.now(timezone.utc).timestamp() * 1000),
        },
    )


async def process_one(
    client: FeishuClient,
    app_token: str,
    table_id: str,
    record: dict,
    *,
    publishers: PublisherRegistry,
    notify_chat: bool = True,
) -> dict:
    from . import bitable_fields as bf
    fields = bf.normalize_fields(record.get("fields", {}))
    record_id = record["record_id"]
    content_id = _read_text(fields.get(bf.CONTENT_ID))
    platform = _read_text(fields.get(bf.PLATFORM))
    ticker = _read_text(fields.get(bf.TICKER))
    body = _read_text(fields.get(bf.BODY))
    cta_url = _read_url(fields.get(bf.CTA_URL))
    redline_result = _read_text(fields.get(bf.REDLINE_RESULT))

    # -- 1. Redline-blocked rows never publish, even if a human Approved them. --
    if redline_result == "Blocked":
        reason = "redline_result=Blocked - cannot publish."
        _mark_failed(client, app_token, table_id, record_id, reason)
        if notify_chat:
            client.send_card(_failed_card(content_id, platform, ticker, reason))
        return {
            "record_id": record_id,
            "content_id": content_id,
            "platform": platform,
            "outcome": "failed",
            "reason": reason,
            "published_url": None,
        }

    # -- 2. Dispatch to publisher. Missing adapters stay visible. --
    publisher = publishers.get(platform)
    if publisher is None:
        reason = f"missing_publisher:{platform}"
        _mark_failed(client, app_token, table_id, record_id, reason)
        if notify_chat:
            client.send_card(_failed_card(content_id, platform, ticker, reason))
        return {
            "record_id": record_id,
            "content_id": content_id,
            "platform": platform,
            "outcome": "failed",
            "reason": reason,
            "published_url": None,
        }
    else:
        try:
            result = await publisher.publish(
                content_id=content_id, ticker=ticker, body=body, cta_url=cta_url
            )
        except Exception as exc:
            logger.exception("[review_poller] publisher.publish raised for %s", content_id)
            result = PublishResult(
                platform=platform,
                content_id=content_id,
                published=False,
                published_url=None,
                dry_run=False,
                error=f"publisher_exception:{exc}",
            )

    # -- 3. Update Bitable based on result. --
    if result.published or result.dry_run:
        _mark_published(client, app_token, table_id, record_id, result.published_url or "")
        if notify_chat:
            client.send_card(
                _published_card(content_id, platform, ticker, result.published_url or "", result.dry_run)
            )
        return {
            "record_id": record_id,
            "content_id": content_id,
            "platform": platform,
            "ticker": ticker,
            "outcome": "published" if result.published else "dry_run",
            "published_url": result.published_url,
            "message_id": result.message_id,
        }

    # Live publish failure
    reason = result.error or "unknown_publish_failure"
    _mark_failed(client, app_token, table_id, record_id, reason)
    if notify_chat:
        client.send_card(_failed_card(content_id, platform, ticker, reason))
    return {
        "record_id": record_id,
        "content_id": content_id,
        "platform": platform,
        "outcome": "failed",
        "reason": reason,
        "published_url": None,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def run_once(
    *,
    client: Optional[FeishuClient] = None,
    publishers: Optional[PublisherRegistry] = None,
    notify_chat: bool = True,
) -> PollResult:
    app_token = os.environ.get("FEISHU_BITABLE_APP_TOKEN", "").strip()
    table_id = os.environ.get("FEISHU_CONTENT_QUEUE_TABLE_ID", "").strip()
    if not app_token or not table_id:
        raise ReviewPollerError(
            "FEISHU_BITABLE_APP_TOKEN and FEISHU_CONTENT_QUEUE_TABLE_ID must be set"
        )

    fb = client or FeishuClient()
    registry = publishers if publishers is not None else default_publishers()
    publisher_names = sorted(registry.keys()) or ["(none)"]
    dry_run = os.environ.get("MARKETING_PUBLISH_DRY_RUN", "true").strip().lower() not in {
        "0", "false", "no", "off"
    }
    logger.info(
        "[review_poller] tick start - publishers=%s dry_run=%s notify_chat=%s",
        ",".join(publisher_names),
        dry_run,
        notify_chat,
    )

    result = PollResult()

    try:
        candidates = fetch_approved_unpublished(fb, app_token, table_id)
    except FeishuAPIError as exc:
        raise ReviewPollerError(f"list_records failed: {exc}") from exc

    result.scanned = len(candidates)
    for record in candidates:
        try:
            outcome = await process_one(
                fb,
                app_token,
                table_id,
                record,
                publishers=registry,
                notify_chat=notify_chat,
            )
            if outcome.get("outcome") in {"published", "dry_run"}:
                result.processed.append(outcome)
            else:
                result.failed.append(outcome)
        except (FeishuAPIError, ReviewPollerError) as exc:
            logger.exception("process_one failed for %s", record.get("record_id"))
            result.errors.append({"record_id": record.get("record_id"), "error": str(exc)})

    logger.info(
        "[review_poller] tick done - scanned=%d processed=%d failed=%d errors=%d",
        result.scanned,
        len(result.processed),
        len(result.failed),
        len(result.errors),
    )
    return result


# Async wrapper for schedulers / CLI that need sync invocation
def run_once_sync(**kwargs) -> PollResult:
    import asyncio

    return asyncio.run(run_once(**kwargs))
