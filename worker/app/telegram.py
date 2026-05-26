from __future__ import annotations

import json
import logging
import os

import httpx

logger = logging.getLogger(__name__)


class TelegramConfigError(RuntimeError):
    pass


def _get_token() -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise TelegramConfigError("TELEGRAM_BOT_TOKEN is not set")
    return token


def _get_public_channel() -> str:
    channel = (
        os.environ.get("TELEGRAM_CHANNEL_ID_PUBLIC", "").strip()
        or os.environ.get("TELEGRAM_CHANNEL_HANDLE", "").strip()
        or os.environ.get("TELEGRAM_CHANNEL_PUBLIC", "").strip()
    )
    if not channel:
        raise TelegramConfigError(
            "Set TELEGRAM_CHANNEL_ID_PUBLIC (numeric chat id) or TELEGRAM_CHANNEL_HANDLE"
        )
    return channel


async def send_channel_message(
    text: str,
    *,
    chat_id: str | None = None,
    parse_mode: str = "HTML",
    disable_web_page_preview: bool = True,
    reply_markup: dict | None = None,
) -> dict:
    token = _get_token()
    target = chat_id or _get_public_channel()

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload: dict = {
        "chat_id": target,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": disable_web_page_preview,
    }
    if reply_markup is not None:
        payload["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(url, json=payload)
        data = response.json()

    if not data.get("ok"):
        raise RuntimeError(
            f"Telegram sendMessage failed: {data.get('error_code')} {data.get('description')}"
        )

    logger.info("telegram message sent to %s (id=%s)", target, data["result"]["message_id"])
    return data["result"]
