"""
bot/services/downloader.py

Hammasi yt-dlp + cookie orqali.
Story/Highlights rasmlari uchun writethumbnail=True ishlatiladi.
instaloader faqat post uchun (login kerak emas, public).
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
import re
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
ALL_EXTS   = VIDEO_EXTS | IMAGE_EXTS


@dataclass
class MediaItem:
    path: str
    media_type: str
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


# ── Cookie ────────────────────────────────────────────────────────────────────

def _prepare_cookie_file(cookies_file: Optional[str]) -> Optional[str]:
    parts = []
    i = 1
    while True:
        part = os.getenv(f"COOKIE_PART_{i}", "").strip()
        if not part:
            break
        parts.append(part)
        i += 1

    if parts:
        try:
            data = base64.b64decode("".join(parts))
            tmp_f = os.path.join(tempfile.gettempdir(), "ig_cookies.txt")
            with open(tmp_f, "wb") as f:
                f.write(data)
            logger.info("🍪 Cookie %d qismdan yuklandi", len(parts))
            return tmp_f
        except Exception as e:
            logger.error("COOKIE_PART decode xato: %s", e)

    b64 = os.getenv("COOKIES_B64", "").strip()
    if b64:
        try:
            data = base64.b64decode(b64)
            tmp_f = os.path.join(tempfile.gettempdir(), "ig_cookies.txt")
            with open(tmp_f, "wb") as f:
                f.write(data)
            logger.info("🍪 Cookie COOKIES_B64 dan yuklandi")
            return tmp_f
        except Exception as e:
            logger.error("COOKIES_B64 decode xato: %s", e)

    for cf in [cookies_file, os.getenv("COOKIES_FILE", "")]:
        if cf and os.path.exists(cf):
            logger.info("🍪 Cookie fayldan: %s", cf)
            return cf

    logger.warning("⚠️ Cookie topilmadi")
    return None


# ── Yordamchilar ──────────────────────────────────────────────────────────────

def _extract_audio(video_path: str) -> Optional[str]:
    out = video_path.rsplit(".", 1)[0] + "_audio.mp3"
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-i", video_path,
             "-vn", "-acodec", "libmp3lame", "-ab", "192k", "-ar", "44100", out],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=60,
        )
        if r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 2048:
            return out
        _del(out)
        return None
    except Exception:
        _del(out)
        return None


def _del(path: str) -> None:
    try:
        if path and os.path.exists(path):
            os.unlink(path)
    except Exception:
        pass


def _detect_type(items: list[MediaItem]) -> str:
    if not items:        return "unknown"
    if len(items) == 1: return items[0].media_type
    types = {it.media_type for it in items}
    if types == {"image"}:  return "carousel_images"
    if types == {"video"}:  return "carousel_videos"
    return "carousel_mixed"


def _make_items(files: list[str], caption: Optional[str] = None) -> list[MediaItem]:
    items = []
    for f in sorted(files):
        if not os.path.isfile(f):
            continue
        size = os.path.getsize(f)
        if size < 512:
            _del(f)
            continue
        ext = Path(f).suffix.lower()
        mtype = "video" if ext in VIDEO_EXTS else "image"
        item = MediaItem(path=f, media_type=mtype, size_bytes=size, caption=caption)
        if mtype == "video":
            item.audio_path = _extract_audio(f)
        items.append(item)
    return items


# ═════════════════════════════════════════════════════════════════════════════
# YT-DLP — umumiy yuklovchi
# ═════════════════════════════════════════════════════════════════════════════

def _base_opts(tmp: str, pfx: str, cookies: Optional[str], write_thumb: bool = False) -> dict:
    opts = {
        "outtmpl": os.path.join(tmp, f"{pfx}_%(autonumber)04d.%(ext)s"),
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "noplaylist": False,
        "ignoreerrors": True,
        "quiet": True,
        "no_warnings": True,
        "writethumbnail": write_thumb,
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
        },
        "postprocessors": [
            {"key": "FFmpegVideoConvertor", "preferedformat": "mp4"},
        ],
    }
    if write_thumb:
        # Thumbnail ni jpg ga convert qilamiz
        opts["postprocessors"].append({
            "key": "FFmpegThumbnailsConvertor",
            "format": "jpg",
        })
    if cookies and os.path.exists(cookies):
        opts["cookiefile"] = cookies
    return opts


def _ytdlp_run(url: str, opts: dict) -> tuple[bool, str, dict]:
    """yt-dlp ni ishga tushiradi. (success, error_msg, info) qaytaradi."""
    import yt_dlp
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True) or {}
        return True, "", info
    except yt_dlp.utils.DownloadError as exc:
        msg = str(exc)
        logger.warning("yt-dlp DownloadError: %s", msg[:200])
        return False, msg[:200], {}
    except Exception as exc:
        logger.warning("yt-dlp xato: %s", exc)
        return False, str(exc)[:200], {}


def _collect_files(tmp: str, before: set) -> tuple[list[str], list[str]]:
    """
    Yangi paydo bo'lgan fayllarni video va rasm ga ajratadi.
    Qaytaradi: (video_files, image_files)
    """
    after = set(os.listdir(tmp))
    new = after - before

    videos = sorted([
        os.path.join(tmp, f) for f in new
        if Path(f).suffix.lower() in VIDEO_EXTS and "_audio" not in f
    ])
    images = sorted([
        os.path.join(tmp, f) for f in new
        if Path(f).suffix.lower() in IMAGE_EXTS and "_audio" not in f
    ])
    return videos, images


def _filter_thumbnails(videos: list[str], images: list[str]) -> tuple[list[str], list[str]]:
    """
    Video uchun yaratilgan thumbnail larni image dan olib tashlaydi.
    Faqat haqiqiy video (>10KB) ga mos kelgan rasmlar thumbnail hisoblanadi.
    """
    # Faqat real videolar (>10KB) ning stemlarini olamiz
    valid_video_stems = {
        Path(v).stem for v in videos
        if os.path.exists(v) and os.path.getsize(v) > 10240
    }
    # Kichik/yaroqsiz videolarni o'chiramiz
    real_videos = []
    for v in videos:
        if os.path.exists(v) and os.path.getsize(v) > 10240:
            real_videos.append(v)
        else:
            _del(v)

    real_images = []
    for img in images:
        stem = Path(img).stem
        if stem in valid_video_stems:
            _del(img)
        else:
            real_images.append(img)
    return real_videos, real_images


# ═════════════════════════════════════════════════════════════════════════════
# POST — instaloader (rasm + video + karusel)
# ═════════════════════════════════════════════════════════════════════════════

def _dl_post_instaloader(shortcode: str, tmp: str, before: set) -> DownloadResult:
    try:
        import instaloader
    except ImportError:
        return DownloadResult(success=False, error="instaloader yo'q")

    L = instaloader.Instaloader(
        download_videos=True,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        post_metadata_txt_pattern="",
        quiet=True,
    )
    def _all_media(directory: str) -> set[str]:
        found = set()
        for root, _, fs in os.walk(directory):
            for f in fs:
                p = os.path.join(root, f)
                if Path(f).suffix.lower() in ALL_EXTS and "_audio" not in f:
                    found.add(p)
        return found

    before_files = _all_media(tmp)
    try:
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        caption = (post.caption or "")[:800] or None
        L.download_post(post, target=Path(tmp))
    except Exception as e:
        logger.error("instaloader post xato: %s", e)
        return DownloadResult(success=False, error=str(e)[:200])

    after_files = _all_media(tmp)
    files = sorted(after_files - before_files)
    if not files:
        return DownloadResult(success=False, error="Post: fayl topilmadi")
    items = _make_items(files, caption)
    logger.info("✅ instaloader post: %d ta", len(items))
    return DownloadResult(success=bool(items), items=items, media_type=_detect_type(items))


# ═════════════════════════════════════════════════════════════════════════════
# STORY — yt-dlp + cookie
# Story rasmlari: writethumbnail=True bilan yuklanadi
# ═════════════════════════════════════════════════════════════════════════════

def _dl_story(url: str, tmp: str, pfx: str, cookies: Optional[str]) -> DownloadResult:
    """
    Story yuklab olish.
    - Video story: bestvideo+bestaudio format bilan yuklanadi
    - Rasm story: yt-dlp thumbnail sifatida saqlaydi (writethumbnail=True)
    """
    before = set(os.listdir(tmp))
    opts = _base_opts(tmp, pfx, cookies, write_thumb=True)

    ok, err, info = _ytdlp_run(url, opts)

    videos, images = _collect_files(tmp, before)
    videos, real_images = _filter_thumbnails(videos, images)

    logger.info("Story: %d video, %d rasm topildi", len(videos), len(real_images))

    all_files = videos + real_images
    if not all_files:
        if not ok:
            if any(k in err.lower() for k in ("private", "login", "403", "401", "cookie")):
                return DownloadResult(success=False, error="need_cookie")
        return DownloadResult(success=False, error="Story: fayl topilmadi")

    items = _make_items(all_files)
    if not items:
        return DownloadResult(success=False, error="Story: fayllar yaroqsiz")

    logger.info("✅ story: %d ta (%d video, %d rasm)",
                len(items),
                sum(1 for i in items if i.media_type == "video"),
                sum(1 for i in items if i.media_type == "image"))
    return DownloadResult(success=True, items=items, media_type=_detect_type(items))


# ═════════════════════════════════════════════════════════════════════════════
# HIGHLIGHTS — yt-dlp + cookie
# ═════════════════════════════════════════════════════════════════════════════

def _dl_highlight(url: str, tmp: str, pfx: str, cookies: Optional[str]) -> DownloadResult:
    """
    Highlights yuklab olish.
    writethumbnail=True — rasm highlights uchun.
    """
    if not cookies:
        return DownloadResult(success=False, error="Highlights uchun cookie kerak (COOKIE_PART_1)")

    before = set(os.listdir(tmp))
    opts = _base_opts(tmp, pfx, cookies, write_thumb=True)

    ok, err, info = _ytdlp_run(url, opts)

    videos, images = _collect_files(tmp, before)
    videos, real_images = _filter_thumbnails(videos, images)

    logger.info("Highlights: %d video, %d rasm topildi", len(videos), len(real_images))

    all_files = videos + real_images
    if not all_files:
        if not ok:
            if any(k in err.lower() for k in ("private", "login", "403", "401", "cookie")):
                return DownloadResult(success=False, error="need_cookie")
        return DownloadResult(success=False, error="Highlights: fayl topilmadi")

    items = _make_items(all_files)
    if not items:
        return DownloadResult(success=False, error="Highlights: fayllar yaroqsiz")

    logger.info("✅ highlights: %d ta (%d video, %d rasm)",
                len(items),
                sum(1 for i in items if i.media_type == "video"),
                sum(1 for i in items if i.media_type == "image"))
    return DownloadResult(success=True, items=items, media_type=_detect_type(items))


# ═════════════════════════════════════════════════════════════════════════════
# REEL — yt-dlp
# ═════════════════════════════════════════════════════════════════════════════

def _dl_reel(url: str, tmp: str, pfx: str, cookies: Optional[str]) -> DownloadResult:
    before = set(os.listdir(tmp))
    opts = _base_opts(tmp, pfx, cookies, write_thumb=False)
    ok, err, _ = _ytdlp_run(url, opts)

    videos, _ = _collect_files(tmp, before)
    if not videos:
        if any(k in err.lower() for k in ("private", "login", "403", "401", "cookie", "rate")):
            return DownloadResult(success=False, error="need_cookie")
        return DownloadResult(success=False, error=err or "Reel: fayl topilmadi")

    items = _make_items(videos)
    logger.info("✅ reel: %d ta", len(items))
    return DownloadResult(success=bool(items), items=items, media_type=_detect_type(items))


# ═════════════════════════════════════════════════════════════════════════════
# ASOSIY KLASS
# ═════════════════════════════════════════════════════════════════════════════

_HIGHLIGHT_RE = re.compile(r"instagram\.com/stories/highlights/(\d+)")
_STORY_RE     = re.compile(r"instagram\.com/stories/([\w.]+)(?:/(\d+))?")
_REEL_RE      = re.compile(r"instagram\.com/reels?/([\w-]+)")
_POST_RE      = re.compile(r"instagram\.com/(?:p|tv)/([\w-]+)")


class InstagramDownloader:
    def __init__(
        self,
        tmp_dir: str,
        max_file_size_mb: int = 50,
        cookies_file: Optional[str] = None,
        ig_username: Optional[str] = None,
        ig_password: Optional[str] = None,
        session_file: Optional[str] = None,
    ):
        self.tmp_dir      = tmp_dir
        self.max_bytes    = max_file_size_mb * 1024 * 1024
        self.cookies_file = cookies_file
        # ig_username/password/session_file — saqlanadi lekin ishlatilmaydi
        # (Railway IP bloklashi sababli login ishlamaydi)
        Path(tmp_dir).mkdir(parents=True, exist_ok=True)

    def _run(self, url: str, pfx: str) -> DownloadResult:
        tmp    = self.tmp_dir
        before = set(os.listdir(tmp))
        ck     = _prepare_cookie_file(self.cookies_file)

        # ── Highlights ────────────────────────────────────────────────────────
        if _HIGHLIGHT_RE.search(url):
            logger.info("→ Highlights")
            return _dl_highlight(url, tmp, pfx, ck)

        # ── Story ─────────────────────────────────────────────────────────────
        if _STORY_RE.search(url):
            logger.info("→ Story")
            return _dl_story(url, tmp, pfx, ck)

        # ── Reel ──────────────────────────────────────────────────────────────
        if _REEL_RE.search(url):
            logger.info("→ Reel")
            r = _dl_reel(url, tmp, pfx, ck)
            if r.success:
                return r
            # Fallback: instaloader
            logger.info("yt-dlp reel yuklamadi → instaloader")
            shortcode = _REEL_RE.search(url).group(1)
            return _dl_post_instaloader(shortcode, tmp, before)

        # ── Post ──────────────────────────────────────────────────────────────
        if _POST_RE.search(url):
            shortcode = _POST_RE.search(url).group(1)
            logger.info("→ Post %s", shortcode)

            # Primary: yt-dlp (instaloader ko'pincha 401/403 qaytaradi)
            before2 = set(os.listdir(tmp))
            opts = _base_opts(tmp, pfx, ck, write_thumb=True)
            ok, err, _ = _ytdlp_run(url, opts)
            videos2, images2 = _collect_files(tmp, before2)
            videos2, images2 = _filter_thumbnails(videos2, images2)
            all_files2 = videos2 + images2
            if all_files2:
                items2 = _make_items(all_files2)
                if items2:
                    logger.info("✅ yt-dlp post: %d ta", len(items2))
                    return DownloadResult(success=True, items=items2,
                                         media_type=_detect_type(items2))

            # Fallback: instaloader
            logger.info("yt-dlp post yuklamadi → instaloader")
            r = _dl_post_instaloader(shortcode, tmp, before)
            if r.success:
                return r

            if any(k in (err or "").lower() for k in ("private", "login", "403", "401")):
                return DownloadResult(success=False, error="need_cookie")
            return DownloadResult(success=False, error=err or r.error or "Post yuklanmadi")

        return DownloadResult(success=False, error="URL turi aniqlanmadi")

    async def download(self, url: str) -> DownloadResult:
        pfx  = uuid.uuid4().hex[:10]
        loop = asyncio.get_running_loop()
        logger.info("⬇️  %s", url)

        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, self._run, url, pfx),
                timeout=300,
            )
        except asyncio.TimeoutError:
            return DownloadResult(success=False, error="timeout")
        except Exception as exc:
            logger.exception("executor xatosi")
            return DownloadResult(success=False, error=str(exc)[:200])

        valid = []
        for item in result.items:
            if item.size_bytes > self.max_bytes:
                _del(item.path)
                _del(item.audio_path or "")
                continue
            valid.append(item)

        if not valid and result.items:
            return DownloadResult(success=False, error="file_too_large:all")
        result.items = valid
        return result