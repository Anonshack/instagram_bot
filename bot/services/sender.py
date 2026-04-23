"""
bot/services/sender.py — Telegram media yuboruvchi

Rasm  → send_photo  (HECH QACHON document sifatida emas)
Video → send_video
Ko'p  → send_media_group (10 tadan bo'laklanadi)
Audio → har bir video uchun alohida send_audio
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
        logger.error("Yuboriladigan fayl topilmadi")
        return False

    chunks = [valid[i:i + MAX_ALBUM] for i in range(0, len(valid), MAX_ALBUM)]
    overall_success = False

    for idx, chunk in enumerate(chunks):
        chunk_caption = caption if idx == 0 else None
        ok = await _send_chunk(bot, chat_id, chunk, chunk_caption, idx)
        if ok:
            overall_success = True

    return overall_success


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
            logger.warning("Fayl yo'q: %s", item.path)
            continue

        item_caption = caption if (chunk_idx == 0 and i == 0) else None
        file = FSInputFile(item.path)

        if item.media_type == "video":
            album.append(InputMediaVideo(
                media=file,
                caption=item_caption,
                parse_mode="HTML",
                width=item.width,
                height=item.height,
                duration=item.duration,
                supports_streaming=True,
            ))
        else:
            # MUHIM: InputMediaPhoto — hech qachon document emas
            album.append(InputMediaPhoto(
                media=file,
                caption=item_caption,
                parse_mode="HTML",
            ))

    if not album:
        _cleanup(chunk)
        return False

    sent_ok = False

    # ── Bitta element ─────────────────────────────────────────────────────────
    if len(album) == 1:
        sent_ok = await _send_one(bot, chat_id, chunk[0], caption if chunk_idx == 0 else None)

    # ── Album (2-10 ta) ───────────────────────────────────────────────────────
    else:
        try:
            await bot.send_media_group(chat_id=chat_id, media=album)
            sent_ok = True
            logger.info("Album yuborildi: %d ta", len(album))
        except Exception as exc:
            logger.error("Album xatosi: %s — birma-bir urinamiz", exc)
            for item in chunk:
                try:
                    ok = await _send_one(bot, chat_id, item, None)
                    if ok:
                        sent_ok = True
                except Exception as e:
                    logger.error("Yakka yuborish xatosi: %s", e)

    # ── Audio ─────────────────────────────────────────────────────────────────
    if sent_ok:
        for item in chunk:
            if item.media_type == "video" and item.audio_path and os.path.exists(item.audio_path):
                await _send_audio(bot, chat_id, item)

    # ── Tozalash ──────────────────────────────────────────────────────────────
    _cleanup(chunk)
    return sent_ok


async def _send_one(bot: Bot, chat_id: int, item: MediaItem, caption: str | None) -> bool:
    """Bitta media — send_photo yoki send_video."""
    if not os.path.exists(item.path):
        return False

    safe_cap = (caption or "")[:1024] or None
    file = FSInputFile(item.path)

    try:
        if item.media_type == "video":
            await bot.send_video(
                chat_id=chat_id,
                video=file,
                caption=safe_cap,
                parse_mode="HTML",
                width=item.width,
                height=item.height,
                duration=item.duration,
                supports_streaming=True,
            )
        else:
            # MUHIM: send_photo — hech qachon send_document emas
            await bot.send_photo(
                chat_id=chat_id,
                photo=file,
                caption=safe_cap,
                parse_mode="HTML",
            )
        return True
    except Exception as exc:
        logger.error("send_one xatosi [%s %s]: %s", item.media_type, Path(item.path).name, exc)
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
        logger.warning("Audio yuborish xatosi: %s", exc)


def _cleanup(chunk: list[MediaItem]) -> None:
    for item in chunk:
        _safe_del(item.path)
        if item.audio_path:
            _safe_del(item.audio_path)


def _safe_del(path: str | None) -> None:
    if not path:
        return
    try:
        if os.path.exists(path):
            os.unlink(path)
            logger.debug("🗑 O'chirildi: %s", Path(path).name)
    except Exception as e:
        logger.warning("O'chirish xatosi: %s", e)