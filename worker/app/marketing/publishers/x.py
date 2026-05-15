"""X publisher for Approved Growth OS drafts.

This adapter posts a single, review-approved text post through the existing
`XClient`. Threading and media upload stay out of scope for this first live
publisher; rows that still look too long are rejected so the operator can
tighten them in Feishu before approval.
"""

from __future__ import annotations

import logging
import os

from ..x_client import XClient
from .base import PublishResult, build_dry_run_url, is_global_dry_run

logger = logging.getLogger(__name__)

PLATFORM = "X"
MAX_X_CHARS = 280


def _platform_dry_run() -> bool:
    raw = os.environ.get("X_DRY_RUN", "true").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _strip_visual_brief(body: str) -> str:
    lines = []
    for line in body.splitlines():
        if line.strip().lower().startswith("visual brief:"):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _prepare_text(body: str, cta_url: str) -> str:
    text = _strip_visual_brief(body)
    if cta_url and cta_url not in text:
        text = f"{text}\n\n{cta_url}".strip()
    return text


def _published_url(tweet_id: str) -> str:
    return f"https://x.com/i/web/status/{tweet_id}"


class XPublisher:
    platform: str = PLATFORM

    def __init__(self, *, client: XClient | None = None) -> None:
        self._client = client

    def _is_dry_run(self) -> bool:
        return is_global_dry_run() or _platform_dry_run()

    async def publish(
        self, *, content_id: str, ticker: str, body: str, cta_url: str
    ) -> PublishResult:
        text = _prepare_text(body, cta_url)
        if len(text) > MAX_X_CHARS:
            return PublishResult(
                platform=self.platform,
                content_id=content_id,
                published=False,
                published_url=None,
                dry_run=False,
                error=f"x_body_too_long:{len(text)}>{MAX_X_CHARS}",
            )

        if self._is_dry_run():
            logger.info("[x-publisher] DRY-RUN %s - would post %d chars", content_id, len(text))
            return PublishResult(
                platform=self.platform,
                content_id=content_id,
                published=False,
                published_url=build_dry_run_url(self.platform, content_id),
                dry_run=True,
            )

        client = self._client or XClient(dry_run=False)
        result = await client.post(text)
        if not result.posted or not result.tweet_id:
            return PublishResult(
                platform=self.platform,
                content_id=content_id,
                published=False,
                published_url=None,
                dry_run=False,
                error=result.error or "x_post_returned_no_tweet_id",
            )

        return PublishResult(
            platform=self.platform,
            content_id=content_id,
            published=True,
            published_url=_published_url(result.tweet_id),
            dry_run=False,
            message_id=result.tweet_id,
        )
