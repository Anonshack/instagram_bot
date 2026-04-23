"""
bot/services/downloader.py

Cookie ni COOKIE_PART_1 + COOKIE_PART_2 + ... qismlarga bo'lib saqlaydi.
Railway 32KB limit muammosini hal qiladi.
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


# ── Cookie tayyorlash ─────────────────────────────────────────────────────────

def _prepare_cookie_file(cookies_file: Optional[str]) -> Optional[str]:
    """
    Cookie faylni quyidagi usullar bilan topadi (tartibda):
    1. COOKIE_PART_1 + COOKIE_PART_2 + ... (Railway 32KB limit uchun)
    2. COOKIES_B64 (yaxlit base64)
    3. COOKIES_FILE (fayl yo'li)
    """

    # 1. Ko'p qismli cookie (COOKIE_PART_1, COOKIE_PART_2, ...)
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
            combined = "".join(parts)
            data = base64.b64decode(combined)
            tmp_f = os.path.join(tempfile.gettempdir(), "ig_cookies.txt")
            with open(tmp_f, "wb") as f:
                f.write(data)
            logger.info("🍪 Cookie %d qismdan yuklandi (%d bytes)", len(parts), len(data))
            return tmp_f
        except Exception as e:
            logger.error("COOKIE_PART_* decode xato: %s", e)

    # 2. Yaxlit COOKIES_B64
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

    # 3. Fayl yo'li
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


def _scan_dir(directory: str, before: set) -> list[str]:
    after = set(os.listdir(directory))
    new = after - before
    return sorted([
        os.path.join(directory, f) for f in new
        if Path(f).suffix.lower() in ALL_EXTS and "_audio" not in f
    ])


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
# YT-DLP
# ═════════════════════════════════════════════════════════════════════════════

def _ytdlp_download(url: str, tmp: str, pfx: str, cookies: Optional[str]) -> DownloadResult:
    import yt_dlp

    before = set(os.listdir(tmp))
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
        "postprocessors": [{"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}],
    }
    if cookies and os.path.exists(cookies):
        opts["cookiefile"] = cookies

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.extract_info(url, download=True)
    except yt_dlp.utils.DownloadError as exc:
        msg = str(exc)
        logger.warning("yt-dlp: %s", msg[:150])
        if any(k in msg.lower() for k in ("private", "login", "unreachable", "cookie", "rate", "401", "403")):
            return DownloadResult(success=False, error="need_cookie")
        return DownloadResult(success=False, error=msg[:200])
    except Exception as exc:
        return DownloadResult(success=False, error=str(exc)[:200])

    files = _scan_dir(tmp, before)
    if not files:
        return DownloadResult(success=False, error="yt-dlp: fayl topilmadi")
    items = _make_items(files)
    if not items:
        return DownloadResult(success=False, error="yt-dlp: fayllar yaroqsiz")
    logger.info("✅ yt-dlp: %d ta media", len(items))
    return DownloadResult(success=True, items=items, media_type=_detect_type(items))


# ═════════════════════════════════════════════════════════════════════════════
# INSTALOADER
# ═════════════════════════════════════════════════════════════════════════════

def _get_loader(username: str, password: str, session_file: str, need_login: bool = False):
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

    if session_file and os.path.exists(session_file) and username:
        try:
            L.load_session_from_file(username, session_file)
            logger.info("instaloader: session (%s)", username)
            return L
        except Exception as e:
            logger.warning("session load xato: %s", e)

    if username and password:
        try:
            L.login(username, password)
            logger.info("instaloader: login OK (%s)", username)
            if session_file:
                try:
                    L.save_session_to_file(session_file)
                except Exception:
                    pass
            return L
        except Exception as e:
            logger.error("instaloader login xato: %s", e)
            if need_login:
                return None

    return None if need_login else L


def _dl_post(shortcode: str, tmp: str, before: set,
             username: str, password: str, session_file: str) -> DownloadResult:
    import instaloader
    L = _get_loader(username, password, session_file, need_login=False)
    try:
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        caption = (post.caption or "")[:800] or None
        L.download_post(post, target=Path(tmp))
    except Exception as e:
        logger.error("download_post xato: %s", e)
        return DownloadResult(success=False, error=str(e)[:200])

    files = _scan_dir(tmp, before)
    if not files:
        return DownloadResult(success=False, error="Post: fayl topilmadi")
    items = _make_items(files, caption)
    logger.info("✅ instaloader post: %d ta", len(items))
    return DownloadResult(success=bool(items), items=items, media_type=_detect_type(items))


def _dl_story_instaloader(ig_user: str, story_id: Optional[str],
                           tmp: str, before: set,
                           username: str, password: str, session_file: str) -> DownloadResult:
    import instaloader
    L = _get_loader(username, password, session_file, need_login=True)
    if not L:
        return DownloadResult(success=False, error="no_login")

    try:
        profile = instaloader.Profile.from_username(L.context, ig_user)
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
        return DownloadResult(success=False, error=str(e)[:200])

    if count == 0:
        return DownloadResult(success=False, error="no_stories")

    files = _scan_dir(tmp, before)
    items = _make_items(files)
    logger.info("✅ instaloader story: %d ta", len(items))
    return DownloadResult(success=bool(items), items=items, media_type=_detect_type(items))


def _dl_highlight(highlight_id: int, tmp: str, before: set,
                  username: str, password: str, session_file: str) -> DownloadResult:
    import instaloader
    L = _get_loader(username, password, session_file, need_login=True)
    if not L:
        return DownloadResult(success=False, error="Highlights uchun login kerak")

    count = 0
    try:
        hl = instaloader.Highlight(L.context, highlight_id)
        for item in hl.get_items():
            try:
                L.download_storyitem(item, target=Path(tmp))
                count += 1
            except Exception as e:
                logger.warning("highlight item xato: %s", e)
    except Exception as e:
        logger.error("Highlight xato: %s", e)
        return DownloadResult(success=False, error=f"Highlight yuklanmadi: {e}")

    if count == 0:
        return DownloadResult(success=False, error="Highlight bo'sh yoki login kerak")

    files = _scan_dir(tmp, before)
    items = _make_items(files)
    logger.info("✅ instaloader highlight: %d ta", len(items))
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
        self.ig_username  = ig_username or ""
        self.ig_password  = ig_password or ""
        self.session_file = session_file or os.path.join(tmp_dir, "ig_session")
        Path(tmp_dir).mkdir(parents=True, exist_ok=True)

    def _run(self, url: str, pfx: str) -> DownloadResult:
        tmp    = self.tmp_dir
        before = set(os.listdir(tmp))
        u, p, sf = self.ig_username, self.ig_password, self.session_file
        ck = _prepare_cookie_file(self.cookies_file)

        hl_m = _HIGHLIGHT_RE.search(url)
        if hl_m:
            logger.info("→ Highlights %s", hl_m.group(1))
            return _dl_highlight(int(hl_m.group(1)), tmp, before, u, p, sf)

        st_m = _STORY_RE.search(url)
        if st_m:
            ig_user  = st_m.group(1)
            story_id = st_m.group(2)
            logger.info("→ Story @%s id=%s", ig_user, story_id or "all")
            r = _ytdlp_download(url, tmp, pfx, ck)
            if r.success:
                return r
            r2 = _dl_story_instaloader(ig_user, story_id, tmp, before, u, p, sf)
            if r2.success:
                return r2
            return DownloadResult(success=False,
                error="story_no_auth" if not ck and not u else (r2.error or r.error))

        rl_m = _REEL_RE.search(url)
        if rl_m:
            logger.info("→ Reel %s", rl_m.group(1))
            r = _ytdlp_download(url, tmp, pfx, ck)
            if r.success:
                return r
            r2 = _dl_post(rl_m.group(1), tmp, before, u, p, sf)
            return r2 if r2.success else r

        post_m = _POST_RE.search(url)
        if post_m:
            logger.info("→ Post %s", post_m.group(1))
            r = _dl_post(post_m.group(1), tmp, before, u, p, sf)
            if r.success:
                return r
            r2 = _ytdlp_download(url, tmp, pfx, ck)
            return r2 if r2.success else r

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