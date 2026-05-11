"""
Onboarding ConversationHandler — 3-step DM setup.
State flow: STEP_TICKERS → STEP_THRESHOLD → STEP_QUIET → END

In-memory conversation state (PTB default) — acceptable for v1.
Persistent data (watchlist/threshold/quiet) saved to DB via db.py.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any

import yfinance as yf
from telegram import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from .. import db
from ..templates import callback_actions as CB
from ..templates.telegram_messages import (
    ONBOARDING_STEP1,
    ONBOARDING_STEP1_BUTTONS,
    ONBOARDING_STEP2_BUTTONS,
    ONBOARDING_STEP2_CUSTOM_PROMPT,
    ONBOARDING_STEP3_BUTTONS,
    ONBOARDING_STEP3_CUSTOM_PROMPT,
    NO_TICKERS_FOUND_MSG,
    SAMPLE_TICKERS,
    TOO_MANY_TICKERS_MSG,
    onboarding_done,
    onboarding_step2,
    onboarding_step3,
)

logger = logging.getLogger(__name__)

STEP_TICKERS = 0
STEP_THRESHOLD = 1
STEP_QUIET = 2
STEP_QUIET_CUSTOM = 3
STEP_THRESHOLD_CUSTOM = 4

MAX_TICKERS = 25
TICKER_RE = re.compile(r"\b[A-Z]{1,5}\b")
START_PAYLOAD_RE = re.compile(
    r"^(?:src_)?(?P<source>[a-z][a-z0-9]{0,8})(?:_(?P<campaign>[a-z0-9-]{1,24}))?"
    r"(?:_(?P<ticker>[A-Za-z]{1,5}))?(?:_[0-9]{6,8})?$"
)


def _make_keyboard(buttons: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(text, callback_data=cd)] for text, cd in buttons]
    )


def _extract_tickers(text: str) -> list[str]:
    raw = text.upper()
    found = TICKER_RE.findall(raw)
    seen: dict[str, None] = {}
    for t in found:
        seen[t] = None
    return list(seen.keys())


def _parse_start_payload(payload: str | None) -> dict[str, Any]:
    if not payload:
        return {}
    clean = payload.strip()[:64]
    if not clean or clean.startswith("uid_"):
        return {"signup_payload_raw": clean} if clean else {}
    match = START_PAYLOAD_RE.match(clean)
    if not match:
        return {"signup_payload_raw": clean}
    data: dict[str, Any] = {
        "signup_source": match.group("source"),
        "signup_payload_raw": clean,
        "signup_at": datetime.now(timezone.utc),
    }
    campaign = match.group("campaign")
    ticker = match.group("ticker")
    if campaign:
        data["signup_campaign"] = campaign
    if ticker:
        data["signup_ticker"] = ticker.upper()
    return data


async def _validate_tickers_async(tickers: list[str]) -> tuple[list[str], list[str]]:
    """Returns (valid, invalid) by checking yfinance in a thread pool."""
    loop = asyncio.get_running_loop()

    def _check(ticker: str) -> bool:
        try:
            data = yf.Ticker(ticker).fast_info
            return bool(getattr(data, "last_price", None))
        except Exception:
            return False

    results = await asyncio.gather(
        *[loop.run_in_executor(None, _check, t) for t in tickers]
    )
    valid = [t for t, ok in zip(tickers, results) if ok]
    invalid = [t for t, ok in zip(tickers, results) if not ok]
    return valid, invalid


# ── Entry point: /start ────────────────────────────────────────────────────────

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not user:
        return ConversationHandler.END

    profile = await db.get_profile(user.id)
    if profile and profile.get("onboarding_completed"):
        await update.message.reply_text(
            "You're already set up. Send /watchlist to see your settings.",
            parse_mode="HTML",
        )
        return ConversationHandler.END

    await db.upsert_profile(
        user.id,
        telegram_username=user.username,
        telegram_first_name=user.first_name,
        **_parse_start_payload(context.args[0] if context.args else None),
    )

    await update.message.reply_text(
        ONBOARDING_STEP1,
        parse_mode="HTML",
        reply_markup=_make_keyboard(ONBOARDING_STEP1_BUTTONS),
    )
    return STEP_TICKERS


# ── Step 1: Receive tickers (text or sample button) ──────────────────────────

async def _finish_tickers(
    update: Update, context: ContextTypes.DEFAULT_TYPE, tickers: list[str]
) -> int:
    if not tickers:
        msg = update.message or (update.callback_query and update.callback_query.message)
        await msg.reply_text(NO_TICKERS_FOUND_MSG, parse_mode="HTML",
                             reply_markup=_make_keyboard(ONBOARDING_STEP1_BUTTONS))
        return STEP_TICKERS

    warned_too_many = False
    if len(tickers) > MAX_TICKERS:
        tickers = tickers[:MAX_TICKERS]
        warned_too_many = True

    valid, invalid = await _validate_tickers_async(tickers)

    if not valid:
        msg_text = (
            f"Couldn't find any of those tickers. "
            f"Check the symbols and try again, or use the sample."
        )
        target = update.message or update.callback_query.message
        await target.reply_text(msg_text, parse_mode="HTML",
                                reply_markup=_make_keyboard(ONBOARDING_STEP1_BUTTONS))
        return STEP_TICKERS

    context.user_data["onb_tickers"] = valid

    parts = []
    if warned_too_many:
        parts.append(TOO_MANY_TICKERS_MSG)
    if invalid:
        parts.append(f"⚠️ Couldn't find: <code>{', '.join(invalid)}</code> — skipped.")

    reply_text = onboarding_step2(valid)
    if parts:
        reply_text = "\n\n".join(parts) + "\n\n" + reply_text

    target = update.message or update.callback_query.message
    await target.reply_text(
        reply_text, parse_mode="HTML",
        reply_markup=_make_keyboard(ONBOARDING_STEP2_BUTTONS),
    )
    return STEP_THRESHOLD


async def receive_tickers_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tickers = _extract_tickers(update.message.text or "")
    return await _finish_tickers(update, context, tickers)


async def use_sample_tickers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    return await _finish_tickers(update, context, list(SAMPLE_TICKERS))


# ── Step 2: Threshold ─────────────────────────────────────────────────────────

async def use_default_threshold(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    context.user_data["onb_threshold"] = 2.0
    await update.callback_query.message.reply_text(
        onboarding_step3(2.0), parse_mode="HTML",
        reply_markup=_make_keyboard(ONBOARDING_STEP3_BUTTONS),
    )
    return STEP_QUIET


async def request_custom_threshold(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(
        ONBOARDING_STEP2_CUSTOM_PROMPT, parse_mode="HTML"
    )
    return STEP_THRESHOLD_CUSTOM


async def receive_custom_threshold(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip().replace("%", "")
    try:
        val = float(text)
    except ValueError:
        await update.message.reply_text(
            "I'm waiting for a threshold number, e.g. <code>1.5</code>.\n"
            "Send /cancel to exit setup.",
            parse_mode="HTML",
        )
        return STEP_THRESHOLD_CUSTOM

    val = max(0.5, min(10.0, val))
    context.user_data["onb_threshold"] = val
    await update.message.reply_text(
        onboarding_step3(val), parse_mode="HTML",
        reply_markup=_make_keyboard(ONBOARDING_STEP3_BUTTONS),
    )
    return STEP_QUIET


async def skip_threshold(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    context.user_data["onb_threshold"] = 2.0
    await update.callback_query.message.reply_text(
        onboarding_step3(2.0), parse_mode="HTML",
        reply_markup=_make_keyboard(ONBOARDING_STEP3_BUTTONS),
    )
    return STEP_QUIET


# ── Step 3: Quiet hours ───────────────────────────────────────────────────────

async def _finish_onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE,
                             quiet_enabled: bool, quiet_start: int = 22,
                             quiet_end: int = 7) -> int:
    user = update.effective_user
    tickers: list[str] = context.user_data.get("onb_tickers", [])
    threshold: float = context.user_data.get("onb_threshold", 2.0)

    await db.upsert_profile(
        user.id,
        watchlist=tickers,
        alert_threshold=threshold,
        quiet_hours_enabled=quiet_enabled,
        quiet_hours_start=quiet_start,
        quiet_hours_end=quiet_end,
        onboarding_completed=True,
    )

    target = update.message or update.callback_query.message
    await target.reply_text(
        onboarding_done(tickers, threshold, quiet_enabled, quiet_start, quiet_end),
        parse_mode="HTML",
    )
    context.user_data.clear()
    return ConversationHandler.END


async def use_default_quiet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    return await _finish_onboarding(update, context, True, 22, 7)


async def no_quiet_hours(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    return await _finish_onboarding(update, context, False)


async def request_custom_quiet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(
        ONBOARDING_STEP3_CUSTOM_PROMPT, parse_mode="HTML"
    )
    return STEP_QUIET_CUSTOM


async def receive_custom_quiet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    parts = text.split()
    if len(parts) == 2:
        try:
            start, end = int(parts[0]) % 24, int(parts[1]) % 24
            return await _finish_onboarding(update, context, True, start, end)
        except ValueError:
            pass
    await update.message.reply_text(
        "I'm waiting for quiet hours in this format: <code>22 7</code> "
        "(start end, 24h ET).\n"
        "Send /cancel to exit setup.",
        parse_mode="HTML",
    )
    return STEP_QUIET_CUSTOM


async def cancel_onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    target = update.message or (update.callback_query and update.callback_query.message)
    if update.callback_query:
        await update.callback_query.answer("Setup cancelled")
    if target:
        await target.reply_text("Setup cancelled. Send /start to begin again.")
    return ConversationHandler.END


# ── ConversationHandler factory ───────────────────────────────────────────────

def get_handler() -> ConversationHandler:
    cancel_button = CallbackQueryHandler(cancel_onboarding, pattern=f"^{CB.ONB_CANCEL}$")
    return ConversationHandler(
        entry_points=[CommandHandler("start", start_command)],
        states={
            STEP_TICKERS: [
                CallbackQueryHandler(use_sample_tickers, pattern=f"^{CB.ONB_TICKERS_SAMPLE}$"),
                cancel_button,
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_tickers_text),
            ],
            STEP_THRESHOLD: [
                CallbackQueryHandler(use_default_threshold, pattern=f"^{CB.ONB_THRESHOLD_DEFAULT}$"),
                CallbackQueryHandler(request_custom_threshold, pattern=f"^{CB.ONB_THRESHOLD_CUSTOM}$"),
                CallbackQueryHandler(skip_threshold, pattern=f"^{CB.ONB_THRESHOLD_SKIP}$"),
                cancel_button,
            ],
            STEP_THRESHOLD_CUSTOM: [
                cancel_button,
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_custom_threshold),
            ],
            STEP_QUIET: [
                CallbackQueryHandler(use_default_quiet, pattern=f"^{CB.ONB_QUIET_DEFAULT}$"),
                CallbackQueryHandler(no_quiet_hours, pattern=f"^{CB.ONB_QUIET_NEVER}$"),
                CallbackQueryHandler(request_custom_quiet, pattern=f"^{CB.ONB_QUIET_CUSTOM}$"),
                cancel_button,
            ],
            STEP_QUIET_CUSTOM: [
                cancel_button,
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_custom_quiet),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_onboarding)],
        per_chat=True,
        per_user=True,
        per_message=False,
        allow_reentry=True,
        conversation_timeout=1800,
    )
