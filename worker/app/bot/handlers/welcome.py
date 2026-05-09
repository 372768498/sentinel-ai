"""
Handler: new member joins the VIP group.
Sends a Welcome message in the group @-mentioning the user,
with a deep link button to start DM onboarding.
"""
from __future__ import annotations

import logging
import os

from telegram import ChatMemberUpdated, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ChatMemberHandler, ContextTypes

from ..templates.telegram_messages import welcome_group

logger = logging.getLogger(__name__)


def _bot_username() -> str:
    return os.environ.get("TELEGRAM_BOT_USERNAME", "").lstrip("@")


def _vip_group_id() -> int | None:
    val = os.environ.get("TELEGRAM_GROUP_ID_VIP", "").strip()
    try:
        return int(val)
    except ValueError:
        return None


def _is_new_member(update: ChatMemberUpdated) -> bool:
    old = update.old_chat_member.status
    new = update.new_chat_member.status
    return old in ("left", "kicked", "restricted") and new in ("member", "administrator")


async def handle_new_vip_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.chat_member:
        return

    change = update.chat_member
    chat_id = change.chat.id

    vip_id = _vip_group_id()
    if vip_id and chat_id != vip_id:
        return

    if not _is_new_member(change):
        return

    user = change.new_chat_member.user
    if user.is_bot:
        return

    bot_username = _bot_username()
    if not bot_username:
        logger.error("TELEGRAM_BOT_USERNAME not set — cannot build deep link")
        return

    text = welcome_group(
        first_name=user.first_name or "there",
        bot_username=bot_username,
        telegram_user_id=user.id,
    )
    deep_link = f"https://t.me/{bot_username}?start=uid_{user.id}"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("👋 Click here to set up your alerts", url=deep_link)]
    ])

    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )
        logger.info("welcome sent to user %s (%s) in chat %s", user.id, user.first_name, chat_id)
    except Exception as exc:
        logger.error("failed to send welcome to %s: %s", user.id, exc)


def get_handler() -> ChatMemberHandler:
    return ChatMemberHandler(handle_new_vip_member, ChatMemberHandler.CHAT_MEMBER)
