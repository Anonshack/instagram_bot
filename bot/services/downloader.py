"""
bot/services/downloader.py — Instagram media downloader

Video yuklananda audio (mp3) ham ajratib olinadi.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yt_dlp  # type: ignore

logger = logging.getLogger(__name__)

USER_AGENTS = [
    (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 "
        "Mobile/15E148 Safari/604.1"
    ),
    (
        "Mozilla/5.0 (Linux; Android 14; Pixel 8) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Mobile Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
]

_ua_index = 0


def _next_ua() -> str:
    global _ua_index
    ua = USER_AGENTS[_ua_index % len(USER_AGENTS)]
    _ua_index += 1
    return ua


@dataclass
class MediaItem:
    path: str
    media_type: str          # 'video' | 'image' | 'audio'
    size_bytes: int = 0
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[int] = None
    caption: Optional[str] = None
    audio_path: Optional[str] = None   # video uchun ajratilgan mp3 yo'li


@dataclass
class DownloadResult:
    success: bool
    items: list[MediaItem] = field(default_factory=list)
    media_type: str = "unknown"
    error: str = ""


def _build_video_opts(output_dir: str, prefix: str, ua: str, cookies_file: Optional[str]) -> dict:
    """Video yuklab olish uchun opts."""
    opts: dict = {
        "outtmpl": os.path.join(output_dir, f"{prefix}_%(autonumber)s.%(ext)s"),
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best/bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "noplaylist": False,
        "quiet": True,
        "no_warnings": True,
        "writethumbnail": False,
        "writeinfojson": False,
        "retries": 8,
        "fragment_retries": 8,
        "skip_unavailable_fragments": True,
        "ignoreerrors": True,
        "socket_timeout": 30,
        "geo_bypass": True,
        "http_headers": {
            "User-Agent": ua,
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
        },
        "postprocessors": [],
        "noprogress": True,
    }
    if cookies_file and os.path.exists(cookies_file):
        opts["cookiefile"] = cookies_file
    return opts


def _build_audio_opts(audio_path: str, ua: str, cookies_file: Optional[str]) -> dict:
    """Faqat audio (mp3) yuklab olish uchun opts."""
    opts: dict = {
        "outtmpl": audio_path,
        "format": "bestaudio/best",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 30,
        "geo_bypass": True,
        "http_headers": {
            "User-Agent": ua,
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
        },
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
        "noprogress": True,
    }
    if cookies_file and os.path.exists(cookies_file):
        opts["cookiefile"] = cookies_file
    return opts


def _extract_audio(url: str, audio_output: str, ua: str, cookies_file: Optional[str]) -> Optional[str]:
    """
    URL dan faqat audioni mp3 sifatida yuklab oladi.
    Muvaffaqiyatli bo'lsa fayl yo'lini, bo'lmasa None qaytaradi.
    """
    # yt-dlp .mp3 kengaytmasini o'zi qo'shadi, shuning uchun
    # outtmpl ga kengaymasiz yo'l beramiz
    base = audio_output  # masalan: /tmp/instabot/abc123_audio
    opts = _build_audio_opts(base, ua, cookies_file)

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.extract_info(url, download=True)

        # yt-dlp .mp3 qo'shadi
        mp3_path = base + ".mp3"
        if os.path.exists(mp3_path) and os.path.getsize(mp3_path) > 0:
            logger.info("🎵 Audio ajratildi: %s (%.1f MB)",
                        os.path.basename(mp3_path),
                        os.path.getsize(mp3_path) / 1_048_576)
            return mp3_path
    except Exception as exc:
        logger.warning("Audio ajratishda xato: %s", str(exc)[:200])

    return None


def _sync_download(
    url: str,
    output_dir: str,
    prefix: str,
    cookies_file: Optional[str] = None,
) -> DownloadResult:
    attempts = []
    if cookies_file and os.path.exists(cookies_file):
        attempts.append((_next_ua(), cookies_file))
    for _ in range(3):
        attempts.append((_next_ua(), None))

    last_error = "Noma'lum xato"

    for num, (ua, cfile) in enumerate(attempts, 1):
        logger.info("Urinish %d/%d — cookie: %s", num, len(attempts), "ha" if cfile else "yo'q")

        opts = _build_video_opts(output_dir, prefix, ua, cfile)
        collected: list[str] = []

        def _hook(d: dict):
            if d["status"] == "finished":
                fp = d.get("filename") or d.get("info_dict", {}).get("filepath", "")
                if fp and os.path.exists(str(fp)) and fp not in collected:
                    collected.append(fp)

        opts["progress_hooks"] = [_hook]

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)

            if not info:
                last_error = "yt-dlp ma'lumot qaytarmadi"
                continue

            entries = [e for e in (info.get("entries") or [info]) if e]
            items: list[MediaItem] = []

            for entry in entries:
                fpath = _resolve(entry, output_dir, prefix, collected, items)
                if not fpath or not os.path.exists(str(fpath)):
                    logger.warning("Fayl topilmadi: %s", entry.get("id", "?"))
                    continue

                ext = Path(str(fpath)).suffix.lower()
                mtype = "video" if ext in (".mp4", ".mov", ".avi", ".webm", ".mkv", ".m4v") else "image"
                dur = entry.get("duration")

                media_item = MediaItem(
                    path=str(fpath),
                    media_type=mtype,
                    size_bytes=os.path.getsize(str(fpath)),
                    width=entry.get("width"),
                    height=entry.get("height"),
                    duration=int(dur) if dur is not None else None,
                    caption=_clean(entry.get("description") or entry.get("title")),
                )

                # Video bo'lsa — audioni ham ajratib olamiz
                if mtype == "video":
                    audio_base = os.path.join(output_dir, f"{prefix}_{len(items)}_audio")
                    audio_path = _extract_audio(url, audio_base, ua, cfile or cookies_file)
                    media_item.audio_path = audio_path

                items.append(media_item)

            if not items:
                items = _scan(output_dir, prefix)

            if not items:
                last_error = "Yuklab olinadigan fayl topilmadi"
                logger.warning("Attempt %d: no files found", num)
                continue

            mtype_overall = "carousel" if len(items) > 1 else items[0].media_type
            logger.info("✅ Muvaffaqiyatli: %d ta fayl (urinish #%d)", len(items), num)
            return DownloadResult(success=True, items=items, media_type=mtype_overall)

        except yt_dlp.utils.DownloadError as exc:
            msg = str(exc)
            last_error = msg
            logger.error("Urinish %d DownloadError: %s", num, msg[:200])
            if any(k in msg.lower() for k in ("private", "login required", "requires authentication", "checkpoint")):
                return DownloadResult(success=False, error="private")
            if any(k in msg.lower() for k in ("not available", "does not exist", "sorry, this page")):
                return DownloadResult(success=False, error="not_found")
            continue

        except Exception as exc:
            last_error = str(exc)[:300]
            logger.exception("Urinish %d kutilmagan xato", num)
            continue

    return DownloadResult(success=False, error=last_error[:300])


# ── Yordamchi funksiyalar ─────────────────────────────────────────────────────

def _resolve(entry, output_dir, prefix, collected, already):
    for rd in (entry.get("requested_downloads") or []):
        for k in ("filepath", "filename"):
            fp = rd.get(k)
            if fp and os.path.exists(str(fp)):
                return str(fp)
    for k in ("filepath", "filename"):
        fp = entry.get(k)
        if fp and os.path.exists(str(fp)):
            return str(fp)
    if collected:
        fp = collected.pop(0)
        if os.path.exists(str(fp)):
            return str(fp)
    return _find(output_dir, prefix, already)


def _find(output_dir, prefix, already):
    existing = {i.path for i in already}
    try:
        for fname in sorted(os.listdir(output_dir)):
            if fname.startswith(prefix) and "_audio" not in fname:
                full = os.path.join(output_dir, fname)
                if full not in existing and os.path.isfile(full):
                    return full
    except Exception:
        pass
    return None


def _scan(output_dir, prefix):
    results = []
    try:
        for fname in sorted(os.listdir(output_dir)):
            if not fname.startswith(prefix) or "_audio" in fname:
                continue
            fp = os.path.join(output_dir, fname)
            if not os.path.isfile(fp):
                continue
            ext = Path(fp).suffix.lower()
            mtype = "video" if ext in (".mp4", ".mov", ".avi", ".webm", ".mkv", ".m4v") else "image"
            results.append(MediaItem(path=fp, media_type=mtype, size_bytes=os.path.getsize(fp)))
    except Exception as e:
        logger.error("Scan xatosi: %s", e)
    return results


def _clean(text):
    if not text:
        return None
    return text[:800] if len(text) > 800 else text


# ── Asosiy sinf ───────────────────────────────────────────────────────────────

class InstagramDownloader:
    def __init__(self, tmp_dir: str, max_file_size_mb: int = 50, cookies_file: Optional[str] = None):
        self.tmp_dir = tmp_dir
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024
        self.cookies_file = cookies_file
        Path(tmp_dir).mkdir(parents=True, exist_ok=True)

        if cookies_file and os.path.exists(cookies_file):
            logger.info("✅ Cookie fayl topildi: %s", cookies_file)
        elif cookies_file:
            logger.warning("⚠️ Cookie fayl yo'q: %s", cookies_file)

    async def download(self, url: str) -> DownloadResult:
        prefix = uuid.uuid4().hex[:12]
        loop = asyncio.get_running_loop()

        try:
            result: DownloadResult = await asyncio.wait_for(
                loop.run_in_executor(None, _sync_download, url, self.tmp_dir, prefix, self.cookies_file),
                timeout=360,  # audio ajratish uchun vaqt ko'proq
            )
        except asyncio.TimeoutError:
            return DownloadResult(success=False, error="timeout")
        except Exception as exc:
            logger.exception("Executor xatosi")
            return DownloadResult(success=False, error=str(exc)[:200])

        valid = []
        for item in result.items:
            if item.size_bytes > self.max_file_size_bytes:
                size_mb = item.size_bytes / 1_048_576
                try:
                    os.unlink(item.path)
                except OSError:
                    pass
                # Audio faylini ham o'chiramiz
                if item.audio_path and os.path.exists(item.audio_path):
                    try:
                        os.unlink(item.audio_path)
                    except OSError:
                        pass
                return DownloadResult(success=False, error=f"file_too_large:{size_mb:.1f}")
            valid.append(item)

        result.items = valid
        if not valid and result.success:
            result.success = False
            result.error = "Barcha fayllar hajm chegarasidan oshdi"

        return result