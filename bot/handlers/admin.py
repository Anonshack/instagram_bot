"""
bot/handlers/admin.py — Admin-only commands

Restricted to user IDs listed in ADMIN_IDS env var.
Provides:
  /broadcast <text>  — send a message to all known users
  /dbstats           — raw DB row counts for debugging
  /cleanup           — manually trigger temp file wipe
"""

import logging
import os
import asyncio

from aiogram import Router, Bot
from aiogram.filters import Command
from aiogram.types import Message
import aiosqlite

from bot.utils.cleanup import cleanup_directory
from database import Database

logger = logging.getLogger(__name__)
router = Router(name="admin")

# ── Load admin IDs from env ───────────────────────────────────────────────────

def _load_admin_ids() -> set[int]:
    raw = os.getenv("ADMIN_IDS", "")
    ids = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return ids

ADMIN_IDS = _load_admin_ids()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ── Filters ───────────────────────────────────────────────────────────────────

async def _admin_filter(message: Message) -> bool:
    return is_admin(message.from_user.id)


# ── /broadcast ────────────────────────────────────────────────────────────────

@router.message(Command("broadcast"), _admin_filter)
async def cmd_broadcast(message: Message, bot: Bot, db: Database):
    text = message.text.removeprefix("/broadcast").strip()
    if not text:
        await message.answer("Usage: /broadcast Your message here")
        return

    # Fetch all known user IDs
    async with aiosqlite.connect(db.db_path) as conn:
        cursor = await conn.execute("SELECT user_id FROM users")
        rows = await cursor.fetchall()

    user_ids = [r[0] for r in rows]
    status = await message.answer(f"📡 Broadcasting to <b>{len(user_ids)}</b> users…", parse_mode="HTML")

    sent = 0
    failed = 0
    for uid in user_ids:
        try:
            await bot.send_message(uid, text, parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)  # ~20 msg/sec — stay under Telegram limits

    await status.edit_text(
        f"✅ Broadcast complete\n\n"
        f"📤 Sent: <b>{sent}</b>\n"
        f"❌ Failed: <b>{failed}</b>",
        parse_mode="HTML",
    )


# ── /dbstats ──────────────────────────────────────────────────────────────────

@router.message(Command("dbstats"), _admin_filter)
async def cmd_dbstats(message: Message, db: Database):
    async with aiosqlite.connect(db.db_path) as conn:
        u = await (await conn.execute("SELECT COUNT(*) FROM users")).fetchone()
        d = await (await conn.execute("SELECT COUNT(*) FROM downloads")).fetchone()
        ok = await (await conn.execute("SELECT COUNT(*) FROM downloads WHERE status='ok'")).fetchone()
        fail = await (await conn.execute("SELECT COUNT(*) FROM downloads WHERE status='failed'")).fetchone()

    await message.answer(
        "🗄 <b>Database Stats</b>\n\n"
        f"👥 Users:             <code>{u[0]}</code>\n"
        f"📦 Total downloads:   <code>{d[0]}</code>\n"
        f"  ✅ Successful:     <code>{ok[0]}</code>\n"
        f"  ❌ Failed:         <code>{fail[0]}</code>",
        parse_mode="HTML",
    )


# ── /cleanup ──────────────────────────────────────────────────────────────────

@router.message(Command("cleanup"), _admin_filter)
async def cmd_cleanup(message: Message, config):
    await cleanup_directory(config.TMP_DIR)
    await message.answer(f"🧹 Temp directory <code>{config.TMP_DIR}</code> wiped.", parse_mode="HTML")
