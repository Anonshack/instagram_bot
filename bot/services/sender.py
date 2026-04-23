"""
bot/services/sender.py — Telegram media delivery

Wraps aiogram send_video / send_photo calls with:
  • InputFile streaming (no extra memory copies)
  • Per-item error handling
  • Carousel support (media group)
  • Immediate file cleanup after each send
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile, InputMediaPhoto, InputMediaVideo

from bot.services.downloader import MediaItem
from bot.utils.cleanup import cleanup_files

logger = logging.getLogger(__name__)

MAX_MEDIA_GROUP = 10  # Telegram hard limit for albums


async def send_media_items(
    bot: Bot,
    chat_id: int,
    items: list[MediaItem],
    caption: str | None = None,
) -> bool:
    """
    Send one or more MediaItems to a chat.

    • Single item  → send_video / send_photo
    • Multiple     → send_media_group (album)

    Returns True if at least one item was delivered successfully.
    """
    if not items:
        return False

    if len(items) == 1:
        return await _send_single(bot, chat_id, items[0], caption)
    else:
        return await _send_album(bot, chat_id, items, caption)


async def _send_single(
    bot: Bot,
    chat_id: int,
    item: MediaItem,
    caption: str | None,
) -> bool:
    path = Path(item.path)
    if not path.exists():
        logger.error("File missing before send: %s", path)
        return False

    # Truncate caption to Telegram's 1024-char limit
    safe_caption = (caption or "")[:1024] or None

    try:
        file = FSInputFile(str(path))
        if item.media_type == "video":
            await bot.send_video(
                chat_id=chat_id,
                video=file,
                caption=safe_caption,
                width=item.width,
                height=item.height,
                duration=item.duration,
                supports_streaming=True,
                parse_mode="HTML",
            )
        else:
            await bot.send_photo(
                chat_id=chat_id,
                photo=file,
                caption=safe_caption,
                parse_mode="HTML",
            )
        return True

    except Exception as exc:
        logger.error("Failed to send %s: %s", path.name, exc)
        return False

    finally:
        await cleanup_files(path)


async def _send_album(
    bot: Bot,
    chat_id: int,
    items: list[MediaItem],
    caption: str | None,
) -> bool:
    """Send a media group (carousel).  Caption goes on the first item."""
    # Telegram allows max 10 items per album
    chunk = items[:MAX_MEDIA_GROUP]
    paths_to_clean = [item.path for item in chunk]

    media_group: list[InputMediaPhoto | InputMediaVideo] = []

    for i, item in enumerate(chunk):
        if not Path(item.path).exists():
            logger.warning("Missing carousel file: %s", item.path)
            continue

        item_caption = (caption or "")[:1024] if i == 0 else None
        file = FSInputFile(item.path)

        if item.media_type == "video":
            media_group.append(InputMediaVideo(
                media=file,
                caption=item_caption,
                width=item.width,
                height=item.height,
                duration=item.duration,
                supports_streaming=True,
            ))
        else:
            media_group.append(InputMediaPhoto(
                media=file,
                caption=item_caption,
            ))

    success = False
    if media_group:
        try:
            await bot.send_media_group(chat_id=chat_id, media=media_group)
            success = True
        except Exception as exc:
            logger.error("Media group send failed: %s", exc)
            # Fallback: send items one by one
            for item in chunk:
                try:
                    await _send_single(bot, chat_id, item, caption if not success else None)
                    success = True
                except Exception:
                    pass
            paths_to_clean = []  # already cleaned in _send_single

    # Clean up all files
    await cleanup_files(*paths_to_clean)
    return success
