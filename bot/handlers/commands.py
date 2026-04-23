"""
bot/handlers/commands.py — /start, /help, /history, /stats command handlers
"""

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from bot.keyboards.inline import help_keyboard, after_download_keyboard
from bot.utils.formatters import (
    welcome_message,
    help_message,
    format_history,
    format_stats,
)
from database import Database

logger = logging.getLogger(__name__)
router = Router(name="commands")


# ── /start ────────────────────────────────────────────────────────────────────

@router.message(Command("start"))
async def cmd_start(message: Message, db: Database):
    user = message.from_user
    await db.upsert_user(user.id, user.username, user.first_name)
    await message.answer(
        welcome_message(user.first_name or "there"),
        parse_mode="HTML",
        reply_markup=help_keyboard(),
    )


# ── /help ─────────────────────────────────────────────────────────────────────

@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(help_message(), parse_mode="HTML")


# ── /history ──────────────────────────────────────────────────────────────────

@router.message(Command("history"))
async def cmd_history(message: Message, db: Database):
    user_id = message.from_user.id
    records = await db.get_user_history(user_id, limit=5)
    await message.answer(format_history(records), parse_mode="HTML")


# ── /stats ────────────────────────────────────────────────────────────────────

@router.message(Command("stats"))
async def cmd_stats(message: Message, db: Database):
    user_id = message.from_user.id
    global_stats = await db.get_global_stats()
    user_stats = await db.get_user_stats(user_id)
    await message.answer(
        format_stats(global_stats, user_stats),
        parse_mode="HTML",
    )


# ── Callback handlers (inline buttons) ────────────────────────────────────────

@router.callback_query(lambda c: c.data == "help")
async def cb_help(callback: CallbackQuery):
    await callback.message.edit_text(help_message(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(lambda c: c.data == "history")
async def cb_history(callback: CallbackQuery, db: Database):
    records = await db.get_user_history(callback.from_user.id, limit=5)
    await callback.message.edit_text(format_history(records), parse_mode="HTML")
    await callback.answer()


@router.callback_query(lambda c: c.data == "stats")
async def cb_stats(callback: CallbackQuery, db: Database):
    global_stats = await db.get_global_stats()
    user_stats = await db.get_user_stats(callback.from_user.id)
    await callback.message.edit_text(
        format_stats(global_stats, user_stats), parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "retry")
async def cb_retry(callback: CallbackQuery):
    await callback.message.edit_text(
        "👇 <b>Send me an Instagram link</b>\n\n"
        "Paste any public post, reel, or story URL below:",
        parse_mode="HTML",
    )
    await callback.answer()
