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


BOT_COMMANDS = [
    BotCommand(command="start",   description="👋 Welcome screen"),
    BotCommand(command="help",    description="📖 Usage guide"),
    BotCommand(command="history", description="📋 Last 5 downloads"),
    BotCommand(command="stats",   description="📊 Usage statistics"),
]


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


async def _periodic_cleanup(tmp_dir: str, interval: int = 600):
    while True:
        await asyncio.sleep(interval)
        await cleanup_directory(tmp_dir)
        logger.debug("🧹  Periodic cleanup done.")


async def main():
    setup_logging()
    config = load_config()

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    db = Database(config.DB_PATH)

    # ── InstagramDownloader — cookies_file qo'shildi ─────────────────────────
    downloader = InstagramDownloader(
        tmp_dir=config.TMP_DIR,
        max_file_size_mb=config.MAX_FILE_SIZE_MB,
        cookies_file=config.COOKIES_FILE,   # <-- yangi parametr
    )

    dp.message.middleware(ThrottleMiddleware(rate=3, window=10))
    dp.update.middleware(DependencyMiddleware(db=db, downloader=downloader, config=config))

    dp.include_router(setup_routers())

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