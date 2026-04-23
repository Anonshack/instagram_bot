"""
middleware.py — Dependency injection via aiogram middleware

Injects shared objects (db, downloader, config) into every handler
without using globals.  Handlers declare them as regular function params.
"""

from typing import Any, Callable, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from database import Database
from bot.services import InstagramDownloader
from config import Config


class DependencyMiddleware(BaseMiddleware):
    """
    Attaches shared service instances to handler data dict.

    Usage in handlers:
        async def my_handler(message: Message, db: Database, downloader: InstagramDownloader):
            ...
    """

    def __init__(self, db: Database, downloader: InstagramDownloader, config: Config):
        self.db = db
        self.downloader = downloader
        self.config = config

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["db"] = self.db
        data["downloader"] = self.downloader
        data["config"] = self.config
        return await handler(event, data)
