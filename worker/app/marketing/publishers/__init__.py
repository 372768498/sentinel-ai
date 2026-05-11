"""Marketing publishers — platform adapters that turn an Approved ContentDraft
into a real (or dry-run) post on a destination platform."""

from .base import (
    DRY_RUN_URL_SCHEME,
    BasePublisher,
    PublishError,
    PublishResult,
    build_dry_run_url,
)
from .telegram import TelegramPublisher

__all__ = [
    "DRY_RUN_URL_SCHEME",
    "BasePublisher",
    "PublishError",
    "PublishResult",
    "TelegramPublisher",
    "build_dry_run_url",
]
