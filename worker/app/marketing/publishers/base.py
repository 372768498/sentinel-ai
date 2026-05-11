"""Common contracts for marketing publishers.

Every platform adapter (Telegram / X / Shorts / TikTok / Email) implements
`BasePublisher` and returns the same `PublishResult`. The review_poller routes
records by `platform` field; missing publishers fall back to dry-run.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol


DRY_RUN_URL_SCHEME = "about:dryrun"


class PublishError(RuntimeError):
    """Raised when a live publish attempt fails for a recoverable reason
    (auth, network, rate limit). Caller is expected to record this on the
    Bitable row and mark review_status=Failed."""


@dataclass(frozen=True)
class PublishResult:
    platform: str
    content_id: str
    published: bool
    published_url: str | None
    dry_run: bool
    error: str | None = None
    message_id: str | None = None


def build_dry_run_url(platform: str, content_id: str) -> str:
    """Stable placeholder URL emitted in dry-run mode.

    Lets the poller idempotency check (published_url empty?) treat dry-run runs
    as already-published while staying obviously non-clickable to humans.
    """
    return f"{DRY_RUN_URL_SCHEME}?platform={platform}&content_id={content_id}"


def is_global_dry_run() -> bool:
    """Master switch — `MARKETING_PUBLISH_DRY_RUN=true` forces every publisher
    into dry-run, regardless of platform-specific config. Defaults to true so
    the worker is safe to start without explicit opt-in."""
    raw = os.environ.get("MARKETING_PUBLISH_DRY_RUN", "true").strip().lower()
    return raw in {"1", "true", "yes", "on"}


class BasePublisher(Protocol):
    """Async publisher protocol. Implementations must NOT raise — they should
    catch their own errors and return a `PublishResult(published=False, error=...)`.
    """

    platform: str

    async def publish(
        self, *, content_id: str, ticker: str, body: str, cta_url: str
    ) -> PublishResult: ...
