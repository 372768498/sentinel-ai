"""Telegram publisher — sends Approved ContentDraft to the public channel.

Reuses `worker.app.telegram.send_channel_message` (already handles token +
channel-id fallback + HTML mode + message_id return).

Target resolution order (matches existing convention):
  1. TELEGRAM_CHANNEL_ID_PUBLIC  (numeric chat id, e.g. -1001234567890)
  2. TELEGRAM_CHANNEL_HANDLE     (e.g. @SentinelAI_signals)
  3. TELEGRAM_CHANNEL_PUBLIC     (legacy)

Dry-run is the safe default — flip with MARKETING_PUBLISH_DRY_RUN=false.
"""

from __future__ import annotations

import html
import logging
import os
from typing import Optional

from ...telegram import TelegramConfigError, send_channel_message
from .base import BasePublisher, PublishResult, build_dry_run_url, is_global_dry_run

logger = logging.getLogger(__name__)

PLATFORM = "Telegram"


def _truncate_for_telegram(text: str, max_chars: int = 4000) -> str:
    """Telegram caption limit is 4096 chars. Leave a small headroom."""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


def _published_url_from_message(message_id: int | str) -> str:
    handle = os.environ.get("TELEGRAM_CHANNEL_HANDLE", "").strip()
    if handle:
        stripped = handle.lstrip("@")
        return f"https://t.me/{stripped}/{message_id}"
    # Fallback when only numeric chat id is available — keep something
    # stable for Bitable URL field but not a real link.
    chat_id = os.environ.get("TELEGRAM_CHANNEL_ID_PUBLIC", "").strip()
    return f"telegram:message/{chat_id}/{message_id}" if chat_id else f"telegram:message/{message_id}"


def _format_body_html(ticker: str, body: str, cta_url: str) -> str:
    """Compose the Telegram message. body is the raw composer output; escape it
    for HTML parse_mode (Telegram is strict about unescaped < > &).

    The CTA URL is appended as a clean HTML link so the in-app preview is nice.
    """
    safe_body = html.escape(body)
    safe_cta = html.escape(cta_url, quote=True)
    return (
        f"{safe_body}\n\n"
        f'<a href="{safe_cta}">Full ${html.escape(ticker)} report →</a>'
    )


class TelegramPublisher:
    platform: str = PLATFORM

    def __init__(
        self,
        *,
        send_fn=send_channel_message,
        dry_run: Optional[bool] = None,
    ) -> None:
        # Allow explicit override per-instance; default to env switch
        self._send_fn = send_fn
        self._dry_run_override = dry_run

    def _is_dry_run(self) -> bool:
        if self._dry_run_override is not None:
            return self._dry_run_override
        return is_global_dry_run()

    @staticmethod
    def _target_available() -> bool:
        return bool(
            os.environ.get("TELEGRAM_CHANNEL_ID_PUBLIC", "").strip()
            or os.environ.get("TELEGRAM_CHANNEL_HANDLE", "").strip()
            or os.environ.get("TELEGRAM_CHANNEL_PUBLIC", "").strip()
        )

    @staticmethod
    def _token_available() -> bool:
        return bool(os.environ.get("TELEGRAM_BOT_TOKEN", "").strip())

    async def publish(
        self, *, content_id: str, ticker: str, body: str, cta_url: str
    ) -> PublishResult:
        if self._is_dry_run():
            url = build_dry_run_url(self.platform, content_id)
            logger.info(
                "[telegram-publisher] DRY-RUN %s — would post %d chars",
                content_id,
                len(body),
            )
            return PublishResult(
                platform=self.platform,
                content_id=content_id,
                published=False,
                published_url=url,
                dry_run=True,
            )

        if not self._token_available():
            return PublishResult(
                platform=self.platform,
                content_id=content_id,
                published=False,
                published_url=None,
                dry_run=False,
                error="missing_telegram_bot_token",
            )
        if not self._target_available():
            return PublishResult(
                platform=self.platform,
                content_id=content_id,
                published=False,
                published_url=None,
                dry_run=False,
                error="missing_telegram_channel_target",
            )

        text = _truncate_for_telegram(_format_body_html(ticker, body, cta_url))

        try:
            result = await self._send_fn(
                text,
                parse_mode="HTML",
                disable_web_page_preview=False,
            )
        except TelegramConfigError as exc:
            return PublishResult(
                platform=self.platform,
                content_id=content_id,
                published=False,
                published_url=None,
                dry_run=False,
                error=f"config:{exc}",
            )
        except Exception as exc:
            logger.exception("[telegram-publisher] live send failed for %s", content_id)
            return PublishResult(
                platform=self.platform,
                content_id=content_id,
                published=False,
                published_url=None,
                dry_run=False,
                error=str(exc),
            )

        message_id = result.get("message_id") if isinstance(result, dict) else None
        if message_id is None:
            return PublishResult(
                platform=self.platform,
                content_id=content_id,
                published=False,
                published_url=None,
                dry_run=False,
                error="telegram_api_returned_no_message_id",
            )

        url = _published_url_from_message(message_id)
        return PublishResult(
            platform=self.platform,
            content_id=content_id,
            published=True,
            published_url=url,
            dry_run=False,
            message_id=str(message_id),
        )
