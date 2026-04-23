"""
bot/services/downloader.py

Ikki mexanizm:
  - instaloader → rasm, story, highlights, karusel (rasm+video)
  - yt-dlp      → fallback (reel, ba'zi videolar)

.env da kerak:
  IG_USERNAME=your_username
  IG_PASSWORD=your_password
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
ALL_EXTS   = VIDEO_EXTS | IMAGE_EXTS


# ── Modellar ──────────────────────────────────────────────────────────────────

@dataclass
class MediaItem:
    path: str
    media_type: str        # 'video' | 'image'
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


# ── Audio ─────────────────────────────────────────────────────────────────────

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
    if not items:
        return "unknown"
    if len(items) == 1:
        return items[0].media_type
    types = {it.media_type for it in items}
    if types == {"image"}:  return "carousel_images"
    if types == {"video"}:  return "carousel_videos"
    return "carousel_mixed"


def _scan_dir(directory: str, before: set) -> list[str]:
    """Yuklanishdan keyin paydo bo'lgan media fayllarni qaytaradi."""
    after = set(os.listdir(directory))
    new = after - before
    files = sorted([
        os.path.join(directory, f) for f in new
        if Path(f).suffix.lower() in ALL_EXTS and "_audio" not in f
    ])
    return files


def _make_items(files: list[str], caption: Optional[str] = None) -> list[MediaItem]:
    items = []
    for f in files:
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
# INSTALOADER — asosiy yuklovchi
# ═════════════════════════════════════════════════════════════════════════════

def _instaloader_session(username: str, password: str, session_file: str):
    """instaloader L obyektini login qilib qaytaradi."""
    import instaloader
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
    # Session fayldan
    if session_file and os.path.exists(session_file) and username:
        try:
            L.load_session_from_file(username, session_file)
            logger.info("instaloader: session fayldan kirdi")
            return L
        except Exception as e:
            logger.warning("Session load xato: %s", e)

    # Login
    if username and password:
        try:
            L.login(username, password)
            logger.info("instaloader: login OK — %s", username)
            if session_file:
                try:
                    L.save_session_to_file(session_file)
                except Exception:
                    pass
            return L
        except Exception as e:
            logger.error("instaloader login xato: %s", e)
            return None

    return None


def _instaloader_download(
    url: str, tmp: str, pfx: str,
    username: Optional[str], password: Optional[str], session_file: Optional[str],
    cookies_file: Optional[str],
) -> DownloadResult:
    try:
        import instaloader
    except ImportError:
        return DownloadResult(success=False, error="instaloader_missing")

    # Login
    L = _instaloader_session(username or "", password or "", session_file or "")
    if not L:
        # Login siz ham urinib ko'r (public post uchun)
        import instaloader as _il
        L = _il.Instaloader(
            download_videos=True,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
            post_metadata_txt_pattern="",
            quiet=True,
        )

    before = set(os.listdir(tmp))

    try:
        # ── URL turini aniqlash ───────────────────────────────────────────────

        # Highlights
        hl_m = re.search(r"/stories/highlights/(\d+)", url)
        if hl_m:
            return _dl_highlight(L, instaloader, int(hl_m.group(1)), tmp, before)

        # Story (username/id yoki faqat username)
        st_m = re.search(r"/stories/([\w.]+)(?:/(\d+))?", url)
        if st_m:
            return _dl_story(L, instaloader, st_m.group(1), st_m.group(2), tmp, before)

        # Post / Reel  (/p/ yoki /reel/)
        post_m = re.search(r"instagram\.com/(?:p|reel|tv)/([\w-]+)", url)
        if post_m:
            return _dl_post(L, instaloader, post_m.group(1), tmp, before)

        return DownloadResult(success=False, error="URL turi aniqlanmadi")

    except Exception as exc:
        msg = str(exc)
        logger.error("instaloader umumiy xato: %s", msg[:300])
        if "private" in msg.lower() or "login" in msg.lower():
            return DownloadResult(success=False, error="private")
        return DownloadResult(success=False, error=msg[:300])


def _dl_post(L, il, shortcode: str, tmp: str, before: set) -> DownloadResult:
    """Post yoki Reel yuklab olish."""
    logger.info("Post yuklanmoqda: %s", shortcode)
    try:
        post = il.Post.from_shortcode(L.context, shortcode)
    except Exception as e:
        return DownloadResult(success=False, error=f"Post topilmadi: {e}")

    caption = (post.caption or "")[:800] or None

    try:
        L.download_post(post, target=Path(tmp))
    except Exception as e:
        logger.warning("download_post xato: %s", e)

    files = _scan_dir(tmp, before)
    if not files:
        return DownloadResult(success=False, error="Post fayllar topilmadi")

    items = _make_items(files, caption)
    if not items:
        return DownloadResult(success=False, error="Post fayllar yaroqsiz")

    logger.info("✅ Post: %d ta media", len(items))
    return DownloadResult(success=True, items=items, media_type=_detect_type(items))


def _dl_story(L, il, username: str, story_id: Optional[str], tmp: str, before: set) -> DownloadResult:
    """Story yuklab olish."""
    logger.info("Story yuklanmoqda: @%s id=%s", username, story_id or "all")
    try:
        profile = il.Profile.from_username(L.context, username)
    except Exception as e:
        return DownloadResult(success=False, error=f"Profil topilmadi: {e}")

    count = 0
    try:
        for story in L.get_stories(userids=[profile.userid]):
            for item in story.get_items():
                if story_id and str(item.mediaid) != story_id:
                    continue
                try:
                    L.download_storyitem(item, target=Path(tmp))
                    count += 1
                except Exception as e:
                    logger.warning("story item xato: %s", e)
    except Exception as e:
        logger.warning("get_stories xato: %s", e)

    if count == 0:
        return DownloadResult(success=False, error=f"@{username} ning faol story si topilmadi")

    files = _scan_dir(tmp, before)
    items = _make_items(files)
    if not items:
        return DownloadResult(success=False, error="Story fayllar topilmadi")

    logger.info("✅ Story: %d ta media", len(items))
    return DownloadResult(success=True, items=items, media_type=_detect_type(items))


def _dl_highlight(L, il, highlight_id: int, tmp: str, before: set) -> DownloadResult:
    """Highlights yuklab olish."""
    logger.info("Highlight yuklanmoqda: %d", highlight_id)
    count = 0
    try:
        highlight = il.Highlight(L.context, highlight_id)
        for item in highlight.get_items():
            try:
                L.download_storyitem(item, target=Path(tmp))
                count += 1
                logger.debug("highlight item %d yuklandi", count)
            except Exception as e:
                logger.warning("highlight item xato: %s", e)
    except Exception as e:
        logger.error("Highlight xato: %s", e)
        return DownloadResult(success=False, error=f"Highlight yuklanmadi: {e}")

    if count == 0:
        return DownloadResult(success=False, error="Highlight bo'sh yoki kirish imkoni yo'q")

    files = _scan_dir(tmp, before)
    items = _make_items(files)
    if not items:
        return DownloadResult(success=False, error="Highlight fayllar topilmadi")

    logger.info("✅ Highlight: %d ta media", len(items))
    return DownloadResult(success=True, items=items, media_type=_detect_type(items))


# ═════════════════════════════════════════════════════════════════════════════
# YT-DLP — fallback (reel uchun)
# ═════════════════════════════════════════════════════════════════════════════

def _ytdlp_download(url: str, tmp: str, pfx: str, cookies: Optional[str]) -> DownloadResult:
    import yt_dlp
    opts = {
        "outtmpl": os.path.join(tmp, f"{pfx}_%(autonumber)04d.%(ext)s"),
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "noplaylist": False,
        "ignoreerrors": True,
        "quiet": True,
        "no_warnings": True,
        "writethumbnail": False,
        "writeinfojson": False,
        "retries": 8,
        "fragment_retries": 8,
        "socket_timeout": 30,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
                "Mobile/15E148 Safari/604.1"
            ),
        },
        "postprocessors": [{"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}],
    }
    if cookies and os.path.exists(cookies):
        opts["cookiefile"] = cookies

    before = set(os.listdir(tmp))
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.extract_info(url, download=True)
    except Exception as exc:
        msg = str(exc)
        logger.error("yt-dlp xato: %s", msg[:200])
        if any(k in msg.lower() for k in ("private", "login", "unreachable")):
            return DownloadResult(success=False, error="need_cookie")
        return DownloadResult(success=False, error=msg[:200])

    files = _scan_dir(tmp, before)
    if not files:
        return DownloadResult(success=False, error="yt-dlp: fayl topilmadi")

    items = _make_items(files)
    if not items:
        return DownloadResult(success=False, error="yt-dlp: fayllar yaroqsiz")

    logger.info("✅ yt-dlp: %d ta media", len(items))
    return DownloadResult(success=True, items=items, media_type=_detect_type(items))


# ═════════════════════════════════════════════════════════════════════════════
# ASOSIY KLASS
# ═════════════════════════════════════════════════════════════════════════════

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
        self.tmp_dir = tmp_dir
        self.max_bytes = max_file_size_mb * 1024 * 1024
        self.cookies = cookies_file
        self.ig_username = ig_username
        self.ig_password = ig_password
        self.session_file = session_file or os.path.join(tmp_dir, "ig_session")
        Path(tmp_dir).mkdir(parents=True, exist_ok=True)

    async def download(self, url: str) -> DownloadResult:
        pfx = uuid.uuid4().hex[:10]
        loop = asyncio.get_running_loop()
        logger.info("⬇️  %s", url)

        def _run():
            # 1. instaloader bilan urinib ko'r
            result = _instaloader_download(
                url, self.tmp_dir, pfx,
                self.ig_username, self.ig_password, self.session_file,
                self.cookies,
            )
            # 2. Agar instaloader ishlamasa — yt-dlp bilan urinib ko'r
            if not result.success and result.error != "private":
                logger.info("instaloader ishlamadi (%s), yt-dlp urinib ko'ramiz", result.error)
                result2 = _ytdlp_download(url, self.tmp_dir, pfx, self.cookies)
                if result2.success:
                    return result2
            return result

        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, _run),
                timeout=300,
            )
        except asyncio.TimeoutError:
            return DownloadResult(success=False, error="timeout")
        except Exception as exc:
            logger.exception("executor xatosi")
            return DownloadResult(success=False, error=str(exc)[:200])

        # Hajm filtri
        valid = []
        for item in result.items:
            if item.size_bytes > self.max_bytes:
                logger.warning("skip katta fayl: %.1fMB", item.size_bytes / 1_048_576)
                _del(item.path)
                _del(item.audio_path or "")
                continue
            valid.append(item)

        if not valid and result.items:
            return DownloadResult(success=False, error="file_too_large:all")
        result.items = valid
        return result