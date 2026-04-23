"""
middlewares/throttle.py — Per-user request throttling

Prevents abuse by limiting how fast a single user can send requests.
Uses a simple token-bucket approach stored in memory (per-process).

Configuration:
  RATE    — max requests per window
  WINDOW  — sliding window in seconds
"""

import time
import logging
from collections import defaultdict, deque
from typing import Any, Callable, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
RATE = 3       # max messages allowed…
WINDOW = 10    # …within this many seconds


class ThrottleMiddleware(BaseMiddleware):
    """
    Sliding-window rate limiter.
    Allows RATE messages per user within WINDOW seconds.
    Ignores command messages from the count (commands should always work).
    """

    def __init__(self, rate: int = RATE, window: int = WINDOW):
        self.rate = rate
        self.window = window
        # user_id → deque of timestamps (oldest first)
        self._history: dict[int, deque] = defaultdict(deque)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # Only throttle Message events (not callbacks/inline)
        if not isinstance(event, Message):
            return await handler(event, data)

        # Never throttle commands — they should always be responsive
        if event.text and event.text.startswith("/"):
            return await handler(event, data)

        user_id = event.from_user.id
        now = time.monotonic()
        history = self._history[user_id]

        # Evict timestamps outside the window
        while history and now - history[0] > self.window:
            history.popleft()

        if len(history) >= self.rate:
            # User is sending too fast
            wait = int(self.window - (now - history[0])) + 1
            logger.info("🛑  Throttling user %s (%d reqs in %ds)", user_id, len(history), self.window)
            await event.answer(
                f"⏱ <b>Slow down a bit!</b>\n\n"
                f"You're sending links too quickly.\n"
                f"Please wait <b>{wait} second{'s' if wait != 1 else ''}</b> and try again.",
                parse_mode="HTML",
            )
            return  # Drop this update

        history.append(now)
        return await handler(event, data)
