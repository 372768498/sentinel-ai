"""
Telegram bot Application factory and lifecycle management.
Runs in polling mode alongside FastAPI (same asyncio event loop).
Switch to webhook by setting BOT_WEBHOOK_URL in env.
"""
from __future__ import annotations

import logging
import os

from telegram.ext import Application, ApplicationBuilder

from . import db
from .handlers import commands, messages, onboarding, welcome

logger = logging.getLogger(__name__)


def _bot_token() -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    return token


def build_application() -> Application:
    app = (
        ApplicationBuilder()
        .token(_bot_token())
        .build()
    )

    # Group 0: onboarding ConversationHandler + commands + WL pending-action handler
    app.add_handler(onboarding.get_handler())

    for h in commands.get_handlers():
        app.add_handler(h)

    # Group 1: free-text ticker query handler ("What about TSLA?")
    # Separated so it doesn't compete with the WL pending-action MessageHandler.
    # The WL handler raises ApplicationHandlerStop when it actually processes,
    # otherwise this group=1 handler runs to interpret natural-language queries.
    app.add_handler(messages.get_handler(), group=1)

    app.add_handler(welcome.get_handler())

    return app


async def start_bot(app: Application) -> None:
    await db.get_pool()
    await app.initialize()
    await app.start()
    await app.updater.start_polling(
        allowed_updates=[
            "message",
            "callback_query",
            "chat_member",
        ],
        drop_pending_updates=True,
    )
    me = await app.bot.get_me()
    print(f"[bot] polling started as @{me.username} (id={me.id})", flush=True)
    logger.info("telegram bot started (polling)")


async def stop_bot(app: Application) -> None:
    await app.updater.stop()
    await app.stop()
    await app.shutdown()
    await db.close_pool()
    logger.info("telegram bot stopped")


def is_bot_enabled() -> bool:
    return os.environ.get("BOT_ENABLED", "").lower() in ("1", "true", "yes")
