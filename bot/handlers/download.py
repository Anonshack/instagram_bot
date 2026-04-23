"""
bot/handlers/download.py — Asosiy Instagram link handler
"""

import logging
import re
import time
from collections import defaultdict

from aiogram import Router, Bot
from aiogram.types import Message

from bot.keyboards.inline import retry_keyboard, after_download_keyboard
from bot.services.downloader import InstagramDownloader
from bot.services.sender import send_media_items
from bot.utils.formatters import (
    DOWNLOADING, UPLOADING, DONE,
    error_invalid_url, error_private_content,
    error_file_too_large, error_download_failed, error_generic,
)
from bot.utils.validators import is_valid_instagram_url, normalize_url
from database import Database

logger = logging.getLogger(__name__)
router = Router(name="download")

_last_request: dict[int, float] = defaultdict(float)
COOLDOWN = 5

def _is_rate_limited(user_id: int) -> bool:
    now = time.monotonic()
    if now - _last_request[user_id] < COOLDOWN:
        return True
    _last_request[user_id] = now
    return False

_URL_RE = re.compile(r"https?://(?:www\.)?instagram\.com/\S+")

def _extract_url(text: str) -> str | None:
    match = _URL_RE.search(text)
    return match.group(0).rstrip(".,)>\"'") if match else None


@router.message()
async def handle_message(
    message: Message,
    bot: Bot,
    db: Database,
    downloader: InstagramDownloader,
):
    user = message.from_user
    text = message.text or message.caption or ""

    raw_url = _extract_url(text)
    if not raw_url:
        await message.answer(
            "👇 <b>Instagram link yuboring!</b>\n\n"
            "Post, Reel, Story yoki Highlights havolasini yuboring.\n\n"
            "Yordam: /help",
            parse_mode="HTML",
        )
        return

    if not is_valid_instagram_url(raw_url):
        await message.answer(error_invalid_url(), parse_mode="HTML", reply_markup=retry_keyboard())
        return

    if _is_rate_limited(user.id):
        await message.answer("⏱ <b>Biroz kuting!</b>\n\nHar 5 sekundda bitta link.", parse_mode="HTML")
        return

    url = normalize_url(raw_url)
    await db.upsert_user(user.id, user.username, user.first_name)

    status_msg = await message.answer(DOWNLOADING, parse_mode="HTML")

    try:
        result = await downloader.download(url)
    except Exception as exc:
        logger.exception("Download xatosi")
        await db.log_download(user.id, url, status="failed")
        await status_msg.edit_text(error_download_failed(str(exc)[:200]), parse_mode="HTML", reply_markup=retry_keyboard())
        return

    if not result.success:
        err = result.error or ""
        await db.log_download(user.id, url, status="failed")

        if "private" in err.lower():
            text_reply = error_private_content()
        elif err.startswith("file_too_large"):
            text_reply = error_file_too_large(0)
        elif err == "timeout":
            text_reply = "⏱ <b>Vaqt tugadi</b>\n\nInstagram javob bermadi. Qayta urinib ko'ring 🔄"
        elif err == "ig_auth":
            text_reply = (
                "🔐 <b>Instagram login kerak</b>\n\n"
                "Story va Highlights yuklab olish uchun bot serverida "
                "<b>IG_USERNAME</b> va <b>IG_PASSWORD</b> sozlanmagan.\n\n"
                "Bot egasiga murojaat qiling."
            )
        elif "instaloader o'rnatilmagan" in err:
            text_reply = (
                "⚙️ <b>Kutubxona yo'q</b>\n\n"
                "<code>pip install instaloader</code> buyrug'ini serverd bajarish kerak."
            )
        elif err == "not_found" or "topilmadi" in err.lower():
            text_reply = "🔍 <b>Kontent topilmadi</b>\n\nBu post o'chirilgan yoki mavjud emas."
        elif err:
            text_reply = error_download_failed(err)
        else:
            text_reply = error_generic()

        await status_msg.edit_text(text_reply, parse_mode="HTML", reply_markup=retry_keyboard())
        return

    await status_msg.edit_text(UPLOADING, parse_mode="HTML")

    try:
        caption = (result.items[0].caption or "")[:1024] if result.items else None
        sent = await send_media_items(bot, message.chat.id, result.items, caption)
    except Exception as exc:
        logger.exception("Send xatosi")
        sent = False

    if sent:
        await db.log_download(user.id, url, media_type=result.media_type, status="ok")
        await status_msg.edit_text(DONE, parse_mode="HTML", reply_markup=after_download_keyboard())
    else:
        await db.log_download(user.id, url, status="failed")
        await status_msg.edit_text(error_generic(), parse_mode="HTML", reply_markup=retry_keyboard())