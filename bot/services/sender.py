"""
bot/services/sender.py

Image → send_photo        (NEVER send_document!)
Video → send_video
Multi → send_media_group  (chunked into groups of 10)
Audio → send_audio for each video
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile, InputMediaPhoto, InputMediaVideo

from bot.services.downloader import MediaItem

logger = logging.getLogger(__name__)
MAX_ALBUM = 10


async def send_media_items(
    bot: Bot,
    chat_id: int,
    items: list[MediaItem],
    caption: str | None = None,
) -> bool:
    if not items:
        return False

    valid = [it for it in items if it.path and os.path.exists(it.path)]
    if not valid:
        logger.error("No files to send")
        return False

    chunks = [valid[i:i+MAX_ALBUM] for i in range(0, len(valid), MAX_ALBUM)]
    success = False
    for idx, chunk in enumerate(chunks):
        ok = await _send_chunk(bot, chat_id, chunk, caption if idx == 0 else None, idx)
        if ok:
            success = True
    return success


async def _send_chunk(
    bot: Bot,
    chat_id: int,
    chunk: list[MediaItem],
    caption: str | None,
    chunk_idx: int,
) -> bool:
    # ── Album yasash ──────────────────────────────────────────────────────────
    album = []
    for i, item in enumerate(chunk):
        if not os.path.exists(item.path):
            continue
        item_cap = caption if (chunk_idx == 0 and i == 0) else None
        file = FSInputFile(item.path)

        if item.media_type == "video":
            album.append(InputMediaVideo(
                media=file,
                caption=item_cap,
                parse_mode="HTML",
                width=item.width,
                height=item.height,
                duration=item.duration,
                supports_streaming=True,
            ))
        else:
            # InputMediaPhoto — Telegram always sends this as a photo
            album.append(InputMediaPhoto(
                media=file,
                caption=item_cap,
                parse_mode="HTML",
            ))

    if not album:
        _cleanup(chunk)
        return False

    sent = False

    if len(album) == 1:
        # Single item — use send_photo / send_video
        sent = await _send_one(bot, chat_id, chunk[0], caption if chunk_idx == 0 else None)
    else:
        try:
            await bot.send_media_group(chat_id=chat_id, media=album)
            sent = True
            logger.info("album sent: %d items", len(album))
        except Exception as exc:
            logger.error("album error: %s — falling back to individual sends", exc)
            for item in chunk:
                try:
                    if await _send_one(bot, chat_id, item, None):
                        sent = True
                except Exception as e:
                    logger.error("single send error: %s", e)

    # ── Audio ─────────────────────────────────────────────────────────────────
    if sent:
        for item in chunk:
            if item.media_type == "video" and item.audio_path and os.path.exists(item.audio_path):
                await _send_audio(bot, chat_id, item)

    _cleanup(chunk)
    return sent


async def _send_one(bot: Bot, chat_id: int, item: MediaItem, caption: str | None) -> bool:
    if not os.path.exists(item.path):
        return False
    cap = (caption or "")[:1024] or None
    file = FSInputFile(item.path)
    try:
        if item.media_type == "video":
            await bot.send_video(
                chat_id=chat_id, video=file, caption=cap, parse_mode="HTML",
                width=item.width, height=item.height, duration=item.duration,
                supports_streaming=True,
            )
        else:
            # send_photo — NOT document
            await bot.send_photo(
                chat_id=chat_id, photo=file, caption=cap, parse_mode="HTML",
            )
        return True
    except Exception as exc:
        logger.error("send_one error [%s %s]: %s", item.media_type, Path(item.path).name, exc)
        return False


async def _send_audio(bot: Bot, chat_id: int, item: MediaItem) -> None:
    try:
        await bot.send_audio(
            chat_id=chat_id,
            audio=FSInputFile(item.audio_path),
            caption="🎵 <b>Audio track</b>",
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.warning("audio send error: %s", exc)


def _cleanup(chunk: list[MediaItem]) -> None:
    for item in chunk:
        _del(item.path)
        if item.audio_path:
            _del(item.audio_path)


def _del(path: str | None) -> None:
    if not path:
        return
    try:
        if os.path.exists(path):
            os.unlink(path)
            logger.debug("🗑 %s", Path(path).name)
    except Exception as e:
        logger.warning("delete error: %s", e)