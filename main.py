"""
main.py — Application entry point

Starts the aiogram 3 bot using long-polling.
All dependencies (DB, Downloader) are injected into handlers via middleware.
"""

import asyncio
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from config import load_config
from database import Database
from bot.handlers import setup_routers
from bot.services import InstagramDownloader
from bot.utils.cleanup import ensure_tmp_dir, cleanup_directory
from bot.utils.logger import setup_logging
from middleware import DependencyMiddleware
from middlewares import ThrottleMiddleware

import logging
logger = logging.getLogger(__name__)


# ── Bot commands (shown in Telegram menu) ─────────────────────────────────────

BOT_COMMANDS = [
    BotCommand(command="start",   description="👋 Welcome screen"),
    BotCommand(command="help",    description="📖 Usage guide"),
    BotCommand(command="history", description="📋 Last 5 downloads"),
    BotCommand(command="stats",   description="📊 Usage statistics"),
]


# ── Startup / Shutdown ────────────────────────────────────────────────────────

async def on_startup(bot: Bot, db: Database, config):
    await db.init()
    ensure_tmp_dir(config.TMP_DIR)
    await bot.set_my_commands(BOT_COMMANDS)
    me = await bot.get_me()
    logger.info("🚀  Bot started: @%s  (id=%s)", me.username, me.id)


async def on_shutdown(bot: Bot, config):
    logger.info("🧹  Cleaning up temp files…")
    await cleanup_directory(config.TMP_DIR)
    await bot.session.close()
    logger.info("👋  Bot stopped cleanly.")


# ── Periodic cleanup task (safety net, every 10 minutes) ─────────────────────

async def _periodic_cleanup(tmp_dir: str, interval: int = 600):
    """Wipe any orphaned temp files in case a delivery failed mid-send."""
    while True:
        await asyncio.sleep(interval)
        await cleanup_directory(tmp_dir)
        logger.debug("🧹  Periodic cleanup done.")


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    # Logging must be initialised first so all subsequent imports log correctly
    setup_logging()

    config = load_config()

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # ── Shared services ───────────────────────────────────────────────────────
    db = Database(config.DB_PATH)
    downloader = InstagramDownloader(config.TMP_DIR, config.MAX_FILE_SIZE_MB)

    # ── Middleware  (registration order = outer → inner wrap) ─────────────────
    # ThrottleMiddleware runs first — blocks abusive users before any DB work
    dp.message.middleware(ThrottleMiddleware(rate=3, window=10))
    # DependencyMiddleware injects db/downloader/config into every handler
    dp.update.middleware(DependencyMiddleware(db=db, downloader=downloader, config=config))

    # ── Routers ────────────────────────────────────────────────────────────────
    dp.include_router(setup_routers())

    # ── Lifecycle ──────────────────────────────────────────────────────────────
    await on_startup(bot, db, config)
    asyncio.create_task(_periodic_cleanup(config.TMP_DIR))

    try:
        logger.info("⚡  Polling started. Press Ctrl+C to stop.")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await on_shutdown(bot, config)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
