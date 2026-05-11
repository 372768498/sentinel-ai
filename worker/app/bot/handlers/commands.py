"""
Command handlers: /watchlist /threshold /snooze /help
These run outside the onboarding ConversationHandler.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationHandlerStop,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .. import db
from ..templates import callback_actions as CB
from ..templates.telegram_messages import (
    HELP_MESSAGE,
    SNOOZE_OFF_CONFIRM,
    WATCHLIST_ADD_PROMPT,
    WATCHLIST_DASHBOARD_BUTTONS,
    WATCHLIST_EMPTY_HELP,
    WATCHLIST_QUIET_EDIT_PROMPT,
    WATCHLIST_REMOVE_PROMPT,
    WATCHLIST_REPLACE_BUTTONS,
    WATCHLIST_THRESHOLD_EDIT_PROMPT,
    snooze_confirm,
    watchlist_dashboard,
    watchlist_replace_confirm,
)
from .onboarding import TICKER_RE, MAX_TICKERS, _validate_tickers_async

logger = logging.getLogger(__name__)


def _make_keyboard(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(text, callback_data=cd) for text, cd in row]
        for row in rows
    ])


def _cancel_kb() -> InlineKeyboardMarkup:
    """Single inline button to cancel a pending watchlist action."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("❌ Cancel", callback_data=CB.WL_CANCEL_ACTION)
    ]])


async def _send_watchlist_dashboard(chat_id: int, user_id: int, bot) -> None:
    profile = await db.get_profile(user_id)
    if not profile or not profile.get("watchlist"):
        await bot.send_message(chat_id=chat_id, text=WATCHLIST_EMPTY_HELP, parse_mode="HTML")
        return

    threshold = profile.get("alert_threshold", 2.0)
    rows = [{"ticker": t, "threshold": threshold, "active": True}
            for t in profile["watchlist"]]
    text = watchlist_dashboard(rows)
    await bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="HTML",
        reply_markup=_make_keyboard(WATCHLIST_DASHBOARD_BUTTONS),
    )


# ── /watchlist ────────────────────────────────────────────────────────────────

async def watchlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return
    await _send_watchlist_dashboard(update.effective_chat.id, user.id, context.bot)


# ── /watchlist inline button callbacks ───────────────────────────────────────

async def cb_wl_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(
        WATCHLIST_ADD_PROMPT, parse_mode="HTML", reply_markup=_cancel_kb()
    )
    context.user_data["wl_pending_action"] = "add"


async def cb_wl_remove_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(
        WATCHLIST_REMOVE_PROMPT, parse_mode="HTML", reply_markup=_cancel_kb()
    )
    context.user_data["wl_pending_action"] = "remove"


async def cb_wl_threshold_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(
        WATCHLIST_THRESHOLD_EDIT_PROMPT, parse_mode="HTML", reply_markup=_cancel_kb()
    )
    context.user_data["wl_pending_action"] = "threshold"


async def cb_wl_quiet_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(
        WATCHLIST_QUIET_EDIT_PROMPT, parse_mode="HTML", reply_markup=_cancel_kb()
    )
    context.user_data["wl_pending_action"] = "quiet"


async def cb_wl_cancel_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cancel any pending watchlist action."""
    await update.callback_query.answer("Cancelled")
    context.user_data.pop("wl_pending_action", None)
    context.user_data.pop("wl_pending_tickers", None)
    await update.callback_query.message.reply_text(
        "✓ Cancelled. Send /watchlist to see your settings or just type a question."
    )


async def cb_wl_replace_yes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer()
    tickers = context.user_data.pop("wl_pending_tickers", [])
    if tickers:
        await db.set_watchlist(update.effective_user.id, tickers)
        await update.callback_query.message.reply_text(
            f"✓ Watchlist replaced: <code>{' · '.join(tickers)}</code>",
            parse_mode="HTML",
        )


async def cb_wl_replace_append(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer()
    user_id = update.effective_user.id
    new_tickers = context.user_data.pop("wl_pending_tickers", [])
    profile = await db.get_profile(user_id)
    existing = profile.get("watchlist", []) if profile else []
    merged = list(dict.fromkeys(existing + new_tickers))[:MAX_TICKERS]
    await db.set_watchlist(user_id, merged)
    await update.callback_query.message.reply_text(
        f"✓ Added. Watchlist now has {len(merged)} tickers.",
        parse_mode="HTML",
    )


async def cb_wl_replace_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer()
    context.user_data.pop("wl_pending_tickers", None)
    await update.callback_query.message.reply_text("Cancelled. Watchlist unchanged.")


# ── Handle pending watchlist text actions ─────────────────────────────────────

async def handle_pending_wl_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Process a text message when user has a pending watchlist action
    (set by clicking Add/Remove/Edit Threshold/Quiet Hours inline buttons).
    If no pending action, returns silently — the ticker query handler in group=1
    will then process the message via "What about X?" matching.
    """
    action = context.user_data.get("wl_pending_action")
    if not action:
        return  # No pending action — let group=1 handlers run

    text = (update.message.text or "").strip()
    user_id = update.effective_user.id

    if action == "add":
        context.user_data.pop("wl_pending_action", None)
        tickers = _extract_uppercase_tickers(text)
        if not tickers:
            await update.message.reply_text("No tickers found. Try: <code>AMD COIN</code>",
                                            parse_mode="HTML")
            return
        valid, invalid = await _validate_tickers_async(tickers)
        if not valid:
            await update.message.reply_text("Couldn't find those tickers. Check symbols.",
                                            parse_mode="HTML")
            return
        profile = await db.get_profile(user_id)
        existing = profile.get("watchlist", []) if profile else []
        if existing:
            context.user_data["wl_pending_tickers"] = valid
            confirm_text = watchlist_replace_confirm(len(existing), valid)
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("Yes, replace", callback_data=CB.WL_REPLACE_CONFIRM),
                InlineKeyboardButton("Add to existing", callback_data=CB.WL_APPEND_CONFIRM),
                InlineKeyboardButton("Cancel", callback_data=CB.WL_REPLACE_CANCEL),
            ]])
            await update.message.reply_text(confirm_text, parse_mode="HTML",
                                            reply_markup=keyboard)
        else:
            await db.set_watchlist(user_id, valid)
            note = f" (skipped: {', '.join(invalid)})" if invalid else ""
            await update.message.reply_text(
                f"✓ Watching {len(valid)} tickers{note}.", parse_mode="HTML"
            )

    elif action == "remove":
        context.user_data.pop("wl_pending_action", None)
        ticker = text.upper().strip()
        profile = await db.get_profile(user_id)
        existing = profile.get("watchlist", []) if profile else []
        updated = [t for t in existing if t != ticker]
        if len(updated) == len(existing):
            await update.message.reply_text(f"<code>{ticker}</code> not in your watchlist.",
                                            parse_mode="HTML")
        else:
            await db.set_watchlist(user_id, updated)
            await update.message.reply_text(
                f"✓ Removed <code>{ticker}</code>. {len(updated)} tickers remain.",
                parse_mode="HTML",
            )

    elif action == "threshold":
        context.user_data.pop("wl_pending_action", None)
        parts = text.upper().split()
        if len(parts) == 2 and parts[0] == "ALL":
            try:
                val = float(parts[1].replace("%", ""))
                val = max(0.5, min(10.0, val))
                await db.set_threshold(user_id, val)
                await update.message.reply_text(
                    f"✓ Threshold set to ±{val:.1f}% for all tickers.", parse_mode="HTML"
                )
            except ValueError:
                await update.message.reply_text("Format: <code>all 1.5</code>", parse_mode="HTML")
        elif len(parts) == 2:
            ticker, pct_str = parts
            try:
                val = float(pct_str.replace("%", ""))
                val = max(0.5, min(10.0, val))
                await db.set_threshold(user_id, val)
                await update.message.reply_text(
                    f"✓ Global threshold set to ±{val:.1f}%.\n"
                    f"<i>Per-ticker thresholds are not enabled yet; this applies to all tickers.</i>",
                    parse_mode="HTML",
                )
            except ValueError:
                await update.message.reply_text(
                    "Format: <code>TSLA 3</code>", parse_mode="HTML"
                )
        else:
            await update.message.reply_text(
                "Format: <code>TSLA 3</code> or <code>all 1.5</code>", parse_mode="HTML"
            )

    elif action == "quiet":
        context.user_data.pop("wl_pending_action", None)
        text_lower = text.lower().strip()
        if text_lower == "off":
            await db.set_quiet_hours(user_id, False)
            await update.message.reply_text("✓ Quiet hours disabled.")
        else:
            parts = text.split()
            if len(parts) == 2:
                try:
                    start, end = int(parts[0]) % 24, int(parts[1]) % 24
                    await db.set_quiet_hours(user_id, True, start, end)
                    await update.message.reply_text(
                        f"✓ Quiet hours: {start:02d}:00–{end:02d}:00 ET"
                    )
                    raise ApplicationHandlerStop
                except ValueError:
                    pass
            await update.message.reply_text(
                "Format: <code>22 7</code> or <code>off</code>", parse_mode="HTML"
            )

    # We actually processed the message — stop further handlers (group=1 ticker query)
    raise ApplicationHandlerStop


def _extract_uppercase_tickers(text: str) -> list[str]:
    found = TICKER_RE.findall(text.upper())
    return list(dict.fromkeys(found))


# ── /threshold ────────────────────────────────────────────────────────────────

async def threshold_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args or []
    user_id = update.effective_user.id

    if len(args) >= 2:
        _, pct_str = args[0].upper(), args[1]
        try:
            val = float(pct_str.replace("%", ""))
            val = max(0.5, min(10.0, val))
            await db.set_threshold(user_id, val)
            await update.message.reply_text(
                f"✓ Global alert threshold set to ±{val:.1f}% for all tickers.",
                parse_mode="HTML",
            )
        except ValueError:
            await update.message.reply_text(
                "Usage: <code>/threshold all 1.5</code>",
                parse_mode="HTML",
            )
    else:
        profile = await db.get_profile(user_id)
        current = profile.get("alert_threshold", 2.0) if profile else 2.0
        await update.message.reply_text(
            f"Current threshold: ±{current:.1f}%\n\n"
            "To change the global threshold: <code>/threshold all 1.5</code>",
            parse_mode="HTML",
        )


# ── /snooze ───────────────────────────────────────────────────────────────────

async def snooze_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args or []
    user_id = update.effective_user.id
    if args and args[0].lower() == "off":
        context.user_data.pop("snooze_until", None)
        await db.clear_snooze(user_id)
        await update.message.reply_text(SNOOZE_OFF_CONFIRM)
        return

    hours = 1
    if args:
        try:
            hours = max(1, min(24, int(args[0])))
        except ValueError:
            pass

    snooze_until = datetime.now(timezone.utc) + timedelta(hours=hours)
    context.user_data["snooze_until"] = snooze_until
    await db.set_snooze_until(user_id, snooze_until)
    await update.message.reply_text(snooze_confirm(hours), parse_mode="HTML")


# ── /help ─────────────────────────────────────────────────────────────────────

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_MESSAGE, parse_mode="HTML")


# ── Handler list for registration ─────────────────────────────────────────────

def get_handlers():
    return [
        CommandHandler("watchlist", watchlist_command),
        CommandHandler("threshold", threshold_command),
        CommandHandler("snooze", snooze_command),
        CommandHandler("help", help_command),
        CallbackQueryHandler(cb_wl_add, pattern=f"^{CB.WL_ADD}$"),
        CallbackQueryHandler(cb_wl_remove_start, pattern=f"^{CB.WL_REMOVE_START}$"),
        CallbackQueryHandler(cb_wl_threshold_edit, pattern=f"^{CB.WL_THRESHOLD_EDIT}$"),
        CallbackQueryHandler(cb_wl_quiet_edit, pattern=f"^{CB.WL_QUIET_EDIT}$"),
        CallbackQueryHandler(cb_wl_replace_yes, pattern=f"^{CB.WL_REPLACE_CONFIRM}$"),
        CallbackQueryHandler(cb_wl_replace_append, pattern=f"^{CB.WL_APPEND_CONFIRM}$"),
        CallbackQueryHandler(cb_wl_replace_cancel, pattern=f"^{CB.WL_REPLACE_CANCEL}$"),
        CallbackQueryHandler(cb_wl_cancel_action, pattern=f"^{CB.WL_CANCEL_ACTION}$"),
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_pending_wl_action,
        ),
    ]
