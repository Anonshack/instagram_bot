"""
bot/handlers/download.py
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

_last: dict[int, float] = defaultdict(float)
COOLDOWN = 5

def _rate_limited(uid: int) -> bool:
    now = time.monotonic()
    if now - _last[uid] < COOLDOWN:
        return True
    _last[uid] = now
    return False

_URL_RE = re.compile(r"https?://(?:www\.)?instagram\.com/\S+")

def _extract_url(text: str) -> str | None:
    m = _URL_RE.search(text)
    return m.group(0).rstrip(".,)>\"'") if m else None


def _extract_url_from_entities(message: Message) -> str | None:
    """message.entities yoki caption_entities dan Instagram URL ni olamiz."""
    text = message.text or message.caption or ""
    entities = message.entities or message.caption_entities or []
    for ent in entities:
        if ent.type == "text_link" and ent.url and "instagram.com" in ent.url:
            return ent.url.rstrip(".,)>\"'")
        if ent.type == "url":
            fragment = text[ent.offset: ent.offset + ent.length]
            if "instagram.com" in fragment:
                return fragment.rstrip(".,)>\"'")
    return None


@router.message()
async def handle_message(
    message: Message, bot: Bot, db: Database, downloader: InstagramDownloader,
):
    text = message.text or message.caption or ""
    raw = _extract_url(text) or _extract_url_from_entities(message)

    if not raw:
        await message.answer(
            "👇 <b>Instagram link yuboring!</b>\n\n"
            "Post, Reel, Story yoki Highlights havolasini yuboring.\n/help",
            parse_mode="HTML",
        )
        return

    if not is_valid_instagram_url(raw):
        await message.answer(error_invalid_url(), parse_mode="HTML", reply_markup=retry_keyboard())
        return

    if _rate_limited(message.from_user.id):
        await message.answer("⏱ <b>Biroz kuting!</b>\n\nHar 5 sekundda bitta link.", parse_mode="HTML")
        return

    url = normalize_url(raw)
    user = message.from_user
    await db.upsert_user(user.id, user.username, user.first_name)
    status = await message.answer(DOWNLOADING, parse_mode="HTML")

    try:
        result = await downloader.download(url)
    except Exception as exc:
        logger.exception("download xatosi")
        await db.log_download(user.id, url, status="failed")
        await status.edit_text(
            error_download_failed(str(exc)[:200]),
            parse_mode="HTML", reply_markup=retry_keyboard()
        )
        return

    if not result.success:
        err = result.error or ""
        await db.log_download(user.id, url, status="failed")

        if "private" in err.lower():
            msg = error_private_content()
        elif err in ("need_cookie", "story_no_auth") or "cookie" in err.lower():
            msg = (
                "🔐 <b>Kirish kerak</b>\n\n"
                "Story yuklab olish uchun <b>.env</b> faylida:\n\n"
                "<code>IG_USERNAME=instagram_login\n"
                "IG_PASSWORD=instagram_parol</code>\n\n"
                "yoki cookie fayl:\n"
                "<code>COOKIES_FILE=cookies.txt</code>"
            )
        elif "no_login" in err or "login kerak" in err.lower():
            msg = (
                "🔐 <b>Instagram login kerak</b>\n\n"
                "<b>.env</b> ga qo'shing:\n"
                "<code>IG_USERNAME=login\nIG_PASSWORD=parol</code>"
            )
        elif "no_stories" in err:
            msg = (
                "📭 <b>Story topilmadi</b>\n\n"
                "Bu foydalanuvchining faol story si yo'q\n"
                "yoki story ko'rinmayapti."
            )
        elif "file_too_large" in err:
            msg = error_file_too_large(0)
        elif err == "timeout":
            msg = "⏱ <b>Vaqt tugadi</b>\n\nQayta urinib ko'ring 🔄"
        elif "topilmadi" in err.lower() or "not found" in err.lower():
            msg = "🔍 <b>Kontent topilmadi</b>\n\nPost o'chirilgan yoki mavjud emas."
        elif err:
            msg = error_download_failed(err)
        else:
            msg = error_generic()

        await status.edit_text(msg, parse_mode="HTML", reply_markup=retry_keyboard())
        return

    await status.edit_text(UPLOADING, parse_mode="HTML")

    try:
        cap = (result.items[0].caption or "")[:1024] if result.items else None
        sent = await send_media_items(bot, message.chat.id, result.items, cap)
    except Exception as exc:
        logger.exception("send xatosi")
        sent = False

    if sent:
        await db.log_download(user.id, url, media_type=result.media_type, status="ok")
        await status.edit_text(DONE, parse_mode="HTML", reply_markup=after_download_keyboard())
    else:
        await db.log_download(user.id, url, status="failed")
        await status.edit_text(error_generic(), parse_mode="HTML", reply_markup=retry_keyboard())