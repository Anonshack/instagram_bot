"""
bot/services/downloader.py — Instagram media downloader

Strategiya:
  1. yt-dlp + cookies.txt fayli orqali urinish
  2. Ishlamasa — yt-dlp + har xil User-Agent bilan 3 ta urinish
  3. Barcha urinishlar muvaffaqiyatsiz bo'lsa — aniq xato qaytarish
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


def _next_user_agent() -> str:
    global _ua_index
    ua = USER_AGENTS[_ua_index % len(USER_AGENTS)]
    _ua_index += 1
    return ua


@dataclass
class MediaItem:
    path: str
    media_type: str          # 'video' | 'image'
    size_bytes: int = 0
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[int] = None
    caption: Optional[str] = None


@dataclass
class DownloadResult:
    success: bool
    items: list[MediaItem] = field(default_factory=list)
    media_type: str = "unknown"
    error: str = ""


def _build_ydl_opts(
    output_dir: str,
    unique_prefix: str,
    user_agent: str,
    cookies_file: Optional[str] = None,
) -> dict:
    opts: dict = {
        "outtmpl": os.path.join(output_dir, f"{unique_prefix}_%(autonumber)s.%(ext)s"),
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "noplaylist": False,
        "quiet": True,
        "no_warnings": True,
        "writethumbnail": False,
        "writeinfojson": False,
        "writedescription": False,
        "retries": 10,
        "fragment_retries": 10,
        "skip_unavailable_fragments": True,
        "ignoreerrors": True,
        "socket_timeout": 30,
        "geo_bypass": True,
        "http_headers": {
            "User-Agent": user_agent,
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        },
        "postprocessors": [
            {"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}
        ],
        "noprogress": True,
    }

    if cookies_file and os.path.exists(cookies_file):
        opts["cookiefile"] = cookies_file
        logger.debug("Cookie fayl ishlatilmoqda: %s", cookies_file)

    return opts


def _sync_download(
    url: str,
    output_dir: str,
    unique_prefix: str,
    cookies_file: Optional[str] = None,
) -> DownloadResult:
    attempts = []

    # Agar cookie fayli mavjud bo'lsa — birinchi urinishda ishlatamiz
    if cookies_file and os.path.exists(cookies_file):
        attempts.append((_next_user_agent(), cookies_file))

    # Cookie siz urinishlar
    for _ in range(3):
        attempts.append((_next_user_agent(), None))

    last_error = "Noma'lum xato"

    for attempt_num, (ua, cfile) in enumerate(attempts, 1):
        logger.info(
            "Urinish %d/%d — cookie: %s",
            attempt_num, len(attempts),
            "ha" if cfile else "yo'q",
        )

        opts = _build_ydl_opts(output_dir, unique_prefix, ua, cfile)
        collected_files: list[str] = []

        def _progress_hook(d: dict):
            if d["status"] == "finished":
                fpath = d.get("filename") or d.get("info_dict", {}).get("filepath", "")
                if fpath and os.path.exists(str(fpath)) and fpath not in collected_files:
                    collected_files.append(fpath)

        opts["progress_hooks"] = [_progress_hook]

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)

            if not info:
                last_error = "yt-dlp ma'lumot qaytarmadi"
                continue

            entries = info.get("entries") or [info]
            entries = [e for e in entries if e]

            items: list[MediaItem] = []
            for entry in entries:
                fpath = _resolve_filepath(entry, output_dir, unique_prefix, collected_files, items)
                if not fpath or not os.path.exists(str(fpath)):
                    logger.warning("Fayl topilmadi: %s", entry.get("id", "?"))
                    continue

                ext = Path(str(fpath)).suffix.lower()
                mtype = (
                    "video"
                    if ext in (".mp4", ".mov", ".avi", ".webm", ".mkv", ".m4v")
                    else "image"
                )
                items.append(MediaItem(
                    path=str(fpath),
                    media_type=mtype,
                    size_bytes=os.path.getsize(str(fpath)),
                    width=entry.get("width"),
                    height=entry.get("height"),
                    duration=entry.get("duration"),
                    caption=_clean_caption(entry.get("description") or entry.get("title")),
                ))

            if not items:
                items = _scan_all_new_files(output_dir, unique_prefix)

            if not items:
                last_error = "Yuklab olinadigan fayl topilmadi"
                continue

            overall_type = "carousel" if len(items) > 1 else items[0].media_type
            logger.info("✅ Muvaffaqiyatli: %d ta fayl (urinish #%d)", len(items), attempt_num)
            return DownloadResult(success=True, items=items, media_type=overall_type)

        except yt_dlp.utils.DownloadError as exc:
            msg = str(exc)
            last_error = msg
            logger.error("Urinish %d DownloadError: %s", attempt_num, msg[:300])

            if any(k in msg.lower() for k in ("private", "login required", "requires authentication", "checkpoint")):
                return DownloadResult(success=False, error="private")
            if any(k in msg.lower() for k in ("not available", "does not exist", "sorry, this page")):
                return DownloadResult(success=False, error="not_found")

            continue

        except Exception as exc:
            last_error = str(exc)[:300]
            logger.exception("Urinish %d kutilmagan xato", attempt_num)
            continue

    return DownloadResult(success=False, error=last_error[:300])


def _resolve_filepath(
    entry: dict,
    output_dir: str,
    unique_prefix: str,
    collected_files: list[str],
    already_added: list[MediaItem],
) -> Optional[str]:
    for rd in (entry.get("requested_downloads") or []):
        for key in ("filepath", "filename"):
            fp = rd.get(key)
            if fp and os.path.exists(str(fp)):
                return str(fp)

    for key in ("filepath", "filename"):
        fp = entry.get(key)
        if fp and os.path.exists(str(fp)):
            return str(fp)

    if collected_files:
        fp = collected_files.pop(0)
        if os.path.exists(str(fp)):
            return str(fp)

    return _find_file_by_prefix(output_dir, unique_prefix, already_added)


def _find_file_by_prefix(
    output_dir: str,
    prefix: str,
    already_added: list[MediaItem],
) -> Optional[str]:
    existing = {item.path for item in already_added}
    try:
        for fname in sorted(os.listdir(output_dir)):
            if fname.startswith(prefix):
                full = os.path.join(output_dir, fname)
                if full not in existing and os.path.isfile(full):
                    return full
    except Exception:
        pass
    return None


def _scan_all_new_files(output_dir: str, prefix: str) -> list[MediaItem]:
    results = []
    try:
        for fname in sorted(os.listdir(output_dir)):
            if not fname.startswith(prefix):
                continue
            fpath = os.path.join(output_dir, fname)
            if not os.path.isfile(fpath):
                continue
            ext = Path(fpath).suffix.lower()
            mtype = "video" if ext in (".mp4", ".mov", ".avi", ".webm", ".mkv", ".m4v") else "image"
            results.append(MediaItem(
                path=fpath,
                media_type=mtype,
                size_bytes=os.path.getsize(fpath),
            ))
    except Exception as e:
        logger.error("Scan xatosi: %s", e)
    return results


def _clean_caption(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    return text[:800] if len(text) > 800 else text


class InstagramDownloader:
    def __init__(
        self,
        tmp_dir: str,
        max_file_size_mb: int = 50,
        cookies_file: Optional[str] = None,
    ):
        self.tmp_dir = tmp_dir
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024
        self.cookies_file = cookies_file
        Path(tmp_dir).mkdir(parents=True, exist_ok=True)

        if cookies_file and os.path.exists(cookies_file):
            logger.info("✅ Cookie fayl topildi: %s", cookies_file)
        elif cookies_file:
            logger.warning("⚠️ Cookie fayl yo'q: %s", cookies_file)

    async def download(self, url: str) -> DownloadResult:
        unique_prefix = uuid.uuid4().hex[:12]
        loop = asyncio.get_running_loop()

        try:
            result: DownloadResult = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    _sync_download,
                    url,
                    self.tmp_dir,
                    unique_prefix,
                    self.cookies_file,
                ),
                timeout=300,
            )
        except asyncio.TimeoutError:
            return DownloadResult(success=False, error="timeout")
        except Exception as exc:
            logger.exception("Executor xatosi")
            return DownloadResult(success=False, error=str(exc)[:200])

        valid_items = []
        for item in result.items:
            if item.size_bytes > self.max_file_size_bytes:
                size_mb = item.size_bytes / 1_048_576
                try:
                    os.unlink(item.path)
                except OSError:
                    pass
                return DownloadResult(success=False, error=f"file_too_large:{size_mb:.1f}")
            valid_items.append(item)

        result.items = valid_items
        if not valid_items and result.success:
            result.success = False
            result.error = "Barcha fayllar hajm chegarasidan oshdi"

        return result