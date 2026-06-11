"""
bot/keyboards/inline.py — Reusable inline keyboard builders
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def subscription_keyboard(channel_username: str, channel_title: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text=f"📢 {channel_title}",
        url=f"https://t.me/{channel_username}"
    ))
    builder.row(InlineKeyboardButton(
        text="✅ I've subscribed",
        callback_data="check_subscription"
    ))
    return builder.as_markup()


def retry_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Try Another Link", callback_data="retry")
    builder.button(text="📋 My History", callback_data="history")
    return builder.as_markup()


def help_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📖 Help Guide", callback_data="help")
    builder.button(text="📊 Stats", callback_data="stats")
    builder.adjust(2)
    return builder.as_markup()


def after_download_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 History", callback_data="history")
    builder.button(text="📊 Stats", callback_data="stats")
    builder.adjust(2)
    return builder.as_markup()
