"""
bot/handlers/errors.py — Global error handler

Catches any unhandled exception that bubbles up through handlers.
Logs the full traceback and sends a friendly message to the user.
Never lets the bot crash silently.
"""

import logging
import traceback

from aiogram import Router
from aiogram.types import Update, ErrorEvent
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
    TelegramNetworkError,
)

logger = logging.getLogger(__name__)
router = Router(name="errors")


@router.errors()
async def global_error_handler(event: ErrorEvent):
    exc = event.exception
    update: Update | None = event.update

    # ── Known Telegram API errors ──────────────────────────────────────────────

    if isinstance(exc, TelegramRetryAfter):
        logger.warning(
            "⏱  Rate limited by Telegram. Retry after %s seconds.", exc.retry_after
        )
        return True  # Suppress — aiogram will retry automatically

    if isinstance(exc, TelegramForbiddenError):
        # User blocked the bot — nothing we can do
        user_id = _extract_user_id(update)
        logger.info("🚫  User %s blocked the bot.", user_id)
        return True

    if isinstance(exc, TelegramBadRequest):
        logger.warning("📛  Telegram bad request: %s", exc)
        await _try_notify_user(update, "⚠️ Telegram rejected this request. Please try again.")
        return True

    if isinstance(exc, TelegramNetworkError):
        logger.error("🌐  Telegram network error: %s", exc)
        return True  # Will retry on next poll

    # ── Unknown / unexpected errors ────────────────────────────────────────────

    logger.error(
        "💥  Unhandled exception in update %s:\n%s",
        update.update_id if update else "?",
        traceback.format_exc(),
    )

    await _try_notify_user(
        update,
        "😓 <b>Something went wrong</b>\n\n"
        "An unexpected error occurred. Please try again.\n"
        "If this keeps happening, the issue will be fixed soon.",
    )
    return True  # Mark as handled so aiogram doesn't re-raise


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_user_id(update: Update | None) -> int | None:
    if not update:
        return None
    if update.message:
        return update.message.from_user.id
    if update.callback_query:
        return update.callback_query.from_user.id
    return None


async def _try_notify_user(update: Update | None, text: str):
    """Best-effort: send an error message back to the user."""
    if not update:
        return
    try:
        if update.message:
            await update.message.answer(text, parse_mode="HTML")
        elif update.callback_query:
            await update.callback_query.answer(
                "⚠️ An error occurred. Please try again.", show_alert=True
            )
    except Exception as notify_exc:
        logger.debug("Could not notify user of error: %s", notify_exc)
