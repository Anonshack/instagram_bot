"""
bot/services/downloader.py

Hammasi yt-dlp orqali — rasm, video, story, highlights, karusel.
Cookie fayl bo'lsa story ham ishlaydi.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import uuid
import re as _re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yt_dlp

logger = logging.getLogger(__name__)


# ── Modellar ──────────────────────────────────────────────────────────────────

@dataclass
class MediaItem:
    path: str
    media_type: str           # 'video' | 'image'
    size_bytes: int = 0
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[int] = None
    caption: Optional[str] = None
    audio_path: Optional[str] = None


@dataclass
class DownloadResult:
    success: bool
    items: list[MediaItem] = field(default_factory=list)
    media_type: str = "unknown"
    error: str = ""


# ── Audio ajratish ────────────────────────────────────────────────────────────

def _extract_audio(video_path: str) -> Optional[str]:
    audio_path = video_path.rsplit(".", 1)[0] + "_audio.mp3"
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-i", video_path,
             "-vn", "-acodec", "libmp3lame", "-ab", "192k", "-ar", "44100",
             audio_path],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=60,
        )
        if r.returncode == 0 and os.path.exists(audio_path) and os.path.getsize(audio_path) > 2048:
            return audio_path
        _safe_del(audio_path)
        return None
    except Exception:
        _safe_del(audio_path)
        return None


# ── yt-dlp yuklovchi ──────────────────────────────────────────────────────────

MEDIA_EXTS = {".mp4", ".mov", ".webm", ".mkv", ".jpg", ".jpeg", ".png", ".gif", ".webp"}


def _build_opts(output_dir: str, prefix: str, cookies_file: Optional[str]) -> dict:
    opts = {
        "outtmpl": os.path.join(output_dir, f"{prefix}_%(autonumber)04d.%(ext)s"),

        # MUHIM: har ikkala format ham ishlashi uchun
        # Avval video+audio merge, bo'lmasa best, bo'lmasa image
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",

        "merge_output_format": "mp4",
        "noplaylist": False,
        "ignoreerrors": True,
        "quiet": True,
        "no_warnings": True,
        "writethumbnail": False,
        "writeinfojson": False,
        "retries": 10,
        "fragment_retries": 10,
        "socket_timeout": 30,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
                "Mobile/15E148 Safari/604.1"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "*/*",
            "X-IG-App-ID": "936619743392459",
        },
        # Rasmlar uchun post-processor yo'q — ular jpg sifatida keladi
        "postprocessors": [
            {"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}
        ],
    }

    if cookies_file and os.path.exists(cookies_file):
        opts["cookiefile"] = cookies_file
        logger.info("🍪 Cookie ishlatilmoqda: %s", cookies_file)

    return opts


def _sync_download(url: str, output_dir: str, prefix: str, cookies_file: Optional[str]) -> DownloadResult:
    opts = _build_opts(output_dir, prefix, cookies_file)
    before = set(os.listdir(output_dir))

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except yt_dlp.utils.DownloadError as exc:
        msg = str(exc)
        logger.error("DownloadError: %s", msg[:200])
        if any(k in msg.lower() for k in ("private", "login", "authentication", "unreachable", "cookies")):
            return DownloadResult(success=False, error="need_cookie")
        return DownloadResult(success=False, error=msg[:300])
    except Exception as exc:
        logger.exception("Kutilmagan xato")
        return DownloadResult(success=False, error=str(exc)[:300])

    # ── Yangi fayllarni top ───────────────────────────────────────────────────
    after = set(os.listdir(output_dir))
    new_names = after - before

    # Prefix bilan boshlanadigan media fayllar
    new_files = sorted([
        os.path.join(output_dir, f)
        for f in new_names
        if Path(f).suffix.lower() in MEDIA_EXTS and "_audio" not in f
    ])

    # Fallback: to'liq scan
    if not new_files:
        new_files = sorted([
            os.path.join(output_dir, f)
            for f in os.listdir(output_dir)
            if f.startswith(prefix)
            and Path(f).suffix.lower() in MEDIA_EXTS
            and "_audio" not in f
        ])

    if not new_files:
        logger.warning("Hech qanday media topilmadi: %s", url)
        return DownloadResult(success=False, error="Media topilmadi. Cookie kerak bo'lishi mumkin.")

    # ── entries (karusel / playlist metadata) ─────────────────────────────────
    entries: list[dict] = []
    if info:
        raw = info.get("entries") or [info]
        entries = [e for e in raw if e and isinstance(e, dict)]

    # ── MediaItem lar yasash ──────────────────────────────────────────────────
    items: list[MediaItem] = []
    for i, fpath in enumerate(new_files):
        if not os.path.isfile(fpath):
            continue
        size = os.path.getsize(fpath)
        if size == 0:
            _safe_del(fpath)
            continue

        ext = Path(fpath).suffix.lower()
        mtype = "video" if ext in (".mp4", ".mov", ".webm", ".mkv") else "image"

        entry = entries[i] if i < len(entries) else (entries[0] if entries else {})
        caption = None
        if entry:
            raw_cap = entry.get("description") or entry.get("title") or ""
            caption = raw_cap[:800] or None

        item = MediaItem(
            path=fpath,
            media_type=mtype,
            size_bytes=size,
            width=entry.get("width") if entry else None,
            height=entry.get("height") if entry else None,
            duration=int(entry.get("duration") or 0) or None,
            caption=caption,
        )

        if mtype == "video":
            item.audio_path = _extract_audio(fpath)

        items.append(item)
        logger.debug("  [%d] %s — %s (%.1f KB)", i+1, mtype, Path(fpath).name, size/1024)

    if not items:
        return DownloadResult(success=False, error="Barcha fayllar yaroqsiz")

    overall = _detect_type(items)
    logger.info("✅ Yuklandi: %d ta media (%s) | %s", len(items), overall, url)
    return DownloadResult(success=True, items=items, media_type=overall)


# ── Yordamchilar ──────────────────────────────────────────────────────────────

def _detect_type(items: list[MediaItem]) -> str:
    if len(items) == 1:
        return items[0].media_type
    types = {it.media_type for it in items}
    if types == {"image"}:   return "carousel_images"
    if types == {"video"}:   return "carousel_videos"
    return "carousel_mixed"


def _safe_del(path: str) -> None:
    try:
        if path and os.path.exists(path):
            os.unlink(path)
    except Exception:
        pass


# ── Asosiy klass ──────────────────────────────────────────────────────────────

class InstagramDownloader:
    def __init__(
        self,
        tmp_dir: str,
        max_file_size_mb: int = 50,
        cookies_file: Optional[str] = None,
        # quyidagilar legacy uchun qoldirildi (instaloader o'chirildi)
        ig_username: Optional[str] = None,
        ig_password: Optional[str] = None,
        session_file: Optional[str] = None,
    ):
        self.tmp_dir = tmp_dir
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024
        self.cookies_file = cookies_file
        Path(tmp_dir).mkdir(parents=True, exist_ok=True)

    async def download(self, url: str) -> DownloadResult:
        prefix = uuid.uuid4().hex[:10]
        loop = asyncio.get_running_loop()

        logger.info("⬇️  Yuklanmoqda: %s", url)

        try:
            result: DownloadResult = await asyncio.wait_for(
                loop.run_in_executor(
                    None, _sync_download, url, self.tmp_dir, prefix, self.cookies_file
                ),
                timeout=300,
            )
        except asyncio.TimeoutError:
            return DownloadResult(success=False, error="timeout")
        except Exception as exc:
            logger.exception("Executor xatosi")
            return DownloadResult(success=False, error=str(exc)[:200])

        # Hajm tekshiruvi
        valid: list[MediaItem] = []
        for item in result.items:
            if item.size_bytes > self.max_file_size_bytes:
                logger.warning("Katta fayl skip: %.1f MB", item.size_bytes / 1_048_576)
                _safe_del(item.path)
                _safe_del(item.audio_path or "")
                continue
            valid.append(item)

        if not valid and result.items:
            return DownloadResult(success=False, error="file_too_large:all")

        result.items = valid
        return result