"""
main.py — Bot ishga tushirish nuqtasi
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
    BotCommand(command="start",   description="👋 Boshlash"),
    BotCommand(command="help",    description="📖 Yordam"),
    BotCommand(command="history", description="📋 So'nggi yuklamalar"),
    BotCommand(command="stats",   description="📊 Statistika"),
]


async def on_startup(bot: Bot, db: Database, config):
    await db.init()
    ensure_tmp_dir(config.TMP_DIR)
    await bot.set_my_commands(BOT_COMMANDS)
    me = await bot.get_me()
    logger.info("🚀  Bot ishga tushdi: @%s", me.username)

    # Instagram login holati
    if config.IG_USERNAME:
        logger.info("📸  Instagram: %s hisobi bilan ulandi", config.IG_USERNAME)
    else:
        logger.warning(
            "⚠️  IG_USERNAME/IG_PASSWORD .env da yo'q — "
            "Story/Highlights yuklanmaydi!"
        )


async def on_shutdown(bot: Bot, config):
    await cleanup_directory(config.TMP_DIR)
    await bot.session.close()
    logger.info("👋  Bot to'xtatildi")


async def _periodic_cleanup(tmp_dir: str, interval: int = 600):
    while True:
        await asyncio.sleep(interval)
        await cleanup_directory(tmp_dir)


async def main():
    setup_logging()
    config = load_config()

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    db = Database(config.DB_PATH)

    # InstagramDownloader — IG credentials bilan
    downloader = InstagramDownloader(
        tmp_dir=config.TMP_DIR,
        max_file_size_mb=config.MAX_FILE_SIZE_MB,
        cookies_file=config.COOKIES_FILE,
        ig_username=config.IG_USERNAME,
        ig_password=config.IG_PASSWORD,
        session_file=config.IG_SESSION_FILE,
    )

    dp.message.middleware(ThrottleMiddleware(rate=3, window=10))
    dp.update.middleware(DependencyMiddleware(db=db, downloader=downloader, config=config))
    dp.include_router(setup_routers())

    await on_startup(bot, db, config)
    asyncio.create_task(_periodic_cleanup(config.TMP_DIR))

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await on_shutdown(bot, config)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass