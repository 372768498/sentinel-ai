"""
Telegram bot Application factory and lifecycle management.
Runs in polling mode alongside FastAPI (same asyncio event loop).
Switch to webhook by setting BOT_WEBHOOK_URL in env.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal

from telegram.ext import Application, ApplicationBuilder

from . import db
from .handlers import commands, messages, onboarding, welcome

logger = logging.getLogger(__name__)

# Watchdog tunables — overridable via env for ops.
_WATCHDOG_INTERVAL_SECONDS = int(os.environ.get("BOT_WATCHDOG_INTERVAL_SECONDS", "60"))
_WATCHDOG_MAX_FAILURES = int(os.environ.get("BOT_WATCHDOG_MAX_FAILURES", "5"))


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


async def _polling_watchdog(app: Application) -> None:
    """
    Detect a "polling is alive in code but dead on the network" deadlock.

    Background:
      python-telegram-bot's network_retry_loop keeps `updater.running=True`
      even when every getUpdates is being rejected by Telegram (the
      Conflict-burst deadlock we hit after redeploy bursts). The only
      symptom from outside the worker is "messages aren't being received."

    Strategy:
      Every BOT_WATCHDOG_INTERVAL_SECONDS, sanity-check both
        - `bot.get_me()` round-trip succeeds (basic API liveness)
        - `app.updater.running` is True
      Failure count resets on the first success. After BOT_WATCHDOG_MAX_
      FAILURES consecutive failures the worker raises SIGTERM, which lets
      Railway's restart policy bring up a fresh container — and the fresh
      container's start_bot() will pre-emptively clear Telegram's server-
      side polling state via delete_webhook(drop_pending_updates=True).
    """
    failures = 0
    while True:
        try:
            await asyncio.sleep(_WATCHDOG_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            return

        try:
            await asyncio.wait_for(app.bot.get_me(), timeout=10.0)
            updater_running = bool(getattr(app.updater, "running", False))
        except Exception as exc:
            failures += 1
            logger.warning(
                "[bot watchdog] healthcheck %d/%d failed: %s",
                failures, _WATCHDOG_MAX_FAILURES, exc,
            )
        else:
            if not updater_running:
                failures += 1
                logger.warning(
                    "[bot watchdog] updater.running=False (%d/%d)",
                    failures, _WATCHDOG_MAX_FAILURES,
                )
            else:
                if failures > 0:
                    logger.info(
                        "[bot watchdog] recovered after %d failures",
                        failures,
                    )
                failures = 0

        if failures >= _WATCHDOG_MAX_FAILURES:
            logger.error(
                "[bot watchdog] polling unhealthy for %d×%ds — "
                "raising SIGTERM for clean restart",
                failures, _WATCHDOG_INTERVAL_SECONDS,
            )
            try:
                os.kill(os.getpid(), signal.SIGTERM)
            except Exception as exc:
                logger.error("[bot watchdog] SIGTERM failed: %s", exc)
            return


async def start_bot(app: Application) -> None:
    await db.get_pool()
    await app.initialize()

    # Critical: clear any leftover polling state Telegram is still holding
    # from a previous container (e.g. after a Railway redeploy where the
    # old polling connection hadn't timed out yet). Without this every
    # redeploy enters a 30-60s Conflict-burst that occasionally deadlocks
    # PTB's network_retry_loop. Idempotent and safe even on cold start.
    try:
        await app.bot.delete_webhook(drop_pending_updates=True)
        logger.info("[bot] cleared webhook + dropped pending updates")
    except Exception as exc:
        logger.warning("[bot] delete_webhook failed (non-fatal): %s", exc)

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

    # Attach watchdog AFTER successful start; cancel in stop_bot.
    app.bot_data["_watchdog_task"] = asyncio.create_task(_polling_watchdog(app))
    print(
        f"[bot] watchdog armed: interval={_WATCHDOG_INTERVAL_SECONDS}s "
        f"max_failures={_WATCHDOG_MAX_FAILURES}",
        flush=True,
    )


async def stop_bot(app: Application) -> None:
    watchdog: asyncio.Task | None = app.bot_data.pop("_watchdog_task", None)
    if watchdog is not None and not watchdog.done():
        watchdog.cancel()
        try:
            await watchdog
        except (asyncio.CancelledError, Exception):
            pass

    await app.updater.stop()
    await app.stop()
    await app.shutdown()
    await db.close_pool()
    logger.info("telegram bot stopped")


def is_bot_enabled() -> bool:
    bot_enabled = os.environ.get("BOT_ENABLED", "").lower() in ("1", "true", "yes")
    polling_disabled = os.environ.get("BOT_POLLING_ENABLED", "true").lower() in (
        "0",
        "false",
        "no",
        "off",
    )
    return bot_enabled and not polling_disabled
