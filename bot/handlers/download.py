"""
bot/handlers/download.py — Instagram link handler (the main logic)

Flow
────
  1. User sends a message with an Instagram URL
  2. Validate URL → reject with friendly error if invalid
  3. Send "Downloading…" status message
  4. Run async download via InstagramDownloader
  5. Edit status → "Uploading…"
  6. Send media to user
  7. Edit status → "Done!" or error
  8. Log to DB, delete temp files
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
    DOWNLOADING,
    UPLOADING,
    DONE,
    error_invalid_url,
    error_private_content,
    error_file_too_large,
    error_download_failed,
    error_generic,
)
from bot.utils.validators import is_valid_instagram_url, normalize_url
from database import Database

logger = logging.getLogger(__name__)
router = Router(name="download")

# ── Simple in-memory rate-limiter (per user, per bot instance) ────────────────
_last_request: dict[int, float] = defaultdict(float)
COOLDOWN = 5  # seconds


def _is_rate_limited(user_id: int) -> bool:
    now = time.monotonic()
    if now - _last_request[user_id] < COOLDOWN:
        return True
    _last_request[user_id] = now
    return False


# ── URL extractor ─────────────────────────────────────────────────────────────

_URL_RE = re.compile(r"https?://(?:www\.)?instagram\.com/\S+")


def _extract_url(text: str) -> str | None:
    match = _URL_RE.search(text)
    return match.group(0) if match else None


# ── Handler ───────────────────────────────────────────────────────────────────

@router.message()
async def handle_message(
    message: Message,
    bot: Bot,
    db: Database,
    downloader: InstagramDownloader,
):
    user = message.from_user
    text = message.text or message.caption or ""

    # ── Extract URL ──────────────────────────────────────────────────────────
    raw_url = _extract_url(text)
    if not raw_url:
        await message.answer(
            "👋 <b>Send me an Instagram link!</b>\n\n"
            "Paste a public post, reel, or story URL and I'll download it for you.\n\n"
            "Need help? Use /help",
            parse_mode="HTML",
        )
        return

    # ── Validate ─────────────────────────────────────────────────────────────
    if not is_valid_instagram_url(raw_url):
        await message.answer(
            error_invalid_url(),
            parse_mode="HTML",
            reply_markup=retry_keyboard(),
        )
        return

    # ── Rate limit ────────────────────────────────────────────────────────────
    if _is_rate_limited(user.id):
        await message.answer(
            f"⏱ <b>Slow down!</b>\n\nPlease wait a few seconds before sending another link.",
            parse_mode="HTML",
        )
        return

    url = normalize_url(raw_url)

    # ── Ensure user is registered ─────────────────────────────────────────────
    await db.upsert_user(user.id, user.username, user.first_name)

    # ── Show progress message ─────────────────────────────────────────────────
    status_msg = await message.answer(DOWNLOADING, parse_mode="HTML")

    # ── Download ──────────────────────────────────────────────────────────────
    result = await downloader.download(url)

    if not result.success:
        err = result.error or ""

        # Log the failed attempt
        await db.log_download(user.id, url, status="failed")

        # Dispatch to the right friendly error
        if "private" in err.lower() or "login" in err.lower():
            text_reply = error_private_content()
        elif err.startswith("file_too_large:"):
            size_mb = float(err.split(":")[1])
            text_reply = error_file_too_large(size_mb)
        elif err:
            text_reply = error_download_failed(err)
        else:
            text_reply = error_generic()

        await status_msg.edit_text(
            text_reply,
            parse_mode="HTML",
            reply_markup=retry_keyboard(),
        )
        return

    # ── Update status → uploading ─────────────────────────────────────────────
    await status_msg.edit_text(UPLOADING, parse_mode="HTML")

    # ── Send media ────────────────────────────────────────────────────────────
    caption = (result.items[0].caption or "")[:1024] if result.items else None
    sent = await send_media_items(bot, message.chat.id, result.items, caption)

    if sent:
        await db.log_download(user.id, url, media_type=result.media_type, status="ok")
        await status_msg.edit_text(
            DONE,
            parse_mode="HTML",
            reply_markup=after_download_keyboard(),
        )
    else:
        await db.log_download(user.id, url, status="failed")
        await status_msg.edit_text(
            error_generic(),
            parse_mode="HTML",
            reply_markup=retry_keyboard(),
        )
