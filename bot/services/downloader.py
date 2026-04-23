"""
bot/services/downloader.py

URL turiga qarab:
  /reel/ /reels/ → yt-dlp (cookie bilan)
  /p/            → instaloader → yt-dlp fallback
  /stories/      → yt-dlp (cookie) → instaloader (login) fallback
  /highlights/   → instaloader (login)
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
# YT-DLP — Reel va Story uchun asosiy
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
        logger.info("🍪 yt-dlp cookie: %s", cookies)

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.extract_info(url, download=True)
    except yt_dlp.utils.DownloadError as exc:
        msg = str(exc)
        logger.warning("yt-dlp DownloadError: %s", msg[:200])
        if any(k in msg.lower() for k in ("private", "login", "unreachable", "cookie", "authentication", "rate")):
            return DownloadResult(success=False, error="need_cookie")
        return DownloadResult(success=False, error=msg[:200])
    except Exception as exc:
        logger.warning("yt-dlp xato: %s", exc)
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
# INSTALOADER — Post va Highlights uchun
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

    # 1. Session fayldan (login xatosi bo'lmaydi)
    if session_file and os.path.exists(session_file) and username:
        try:
            L.load_session_from_file(username, session_file)
            logger.info("instaloader: session yuklandi (%s)", username)
            return L
        except Exception as e:
            logger.warning("session load xato: %s", e)

    # 2. Username/password
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
            # Login xato bo'lsa need_login=True da None qaytaramiz
            if need_login:
                return None

    if need_login:
        return None

    # Loginsiz (public content)
    return L


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
    logger.info("✅ instaloader post: %d ta media", len(items))
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
    logger.info("✅ instaloader story: %d ta media", len(items))
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
    logger.info("✅ instaloader highlight: %d ta media", len(items))
    return DownloadResult(success=bool(items), items=items, media_type=_detect_type(items))


# ═════════════════════════════════════════════════════════════════════════════
# ASOSIY KLASS
# ═════════════════════════════════════════════════════════════════════════════

# MUHIM: /reels/ ham /reel/ ham qoplanadi
_HIGHLIGHT_RE = re.compile(r"instagram\.com/stories/highlights/(\d+)")
_STORY_RE     = re.compile(r"instagram\.com/stories/([\w.]+)(?:/(\d+))?")
_REEL_RE      = re.compile(r"instagram\.com/reels?/([\w-]+)")   # reel VA reels
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
        self.cookies      = cookies_file
        self.ig_username  = ig_username or ""
        self.ig_password  = ig_password or ""
        self.session_file = session_file or os.path.join(tmp_dir, "ig_session")
        Path(tmp_dir).mkdir(parents=True, exist_ok=True)

    def _run(self, url: str, pfx: str) -> DownloadResult:
        tmp    = self.tmp_dir
        before = set(os.listdir(tmp))
        u, p, sf, ck = self.ig_username, self.ig_password, self.session_file, self.cookies

        # ── 1. Highlights ─────────────────────────────────────────────────────
        hl_m = _HIGHLIGHT_RE.search(url)
        if hl_m:
            logger.info("→ Highlights %s", hl_m.group(1))
            return _dl_highlight(int(hl_m.group(1)), tmp, before, u, p, sf)

        # ── 2. Story ──────────────────────────────────────────────────────────
        st_m = _STORY_RE.search(url)
        if st_m:
            ig_user  = st_m.group(1)
            story_id = st_m.group(2)
            logger.info("→ Story @%s id=%s", ig_user, story_id or "all")

            # Avval yt-dlp (cookie bilan)
            r = _ytdlp_download(url, tmp, pfx, ck)
            if r.success:
                return r
            logger.info("yt-dlp story yuklamadi (%s) → instaloader", r.error)

            # Keyin instaloader
            r2 = _dl_story_instaloader(ig_user, story_id, tmp, before, u, p, sf)
            if r2.success:
                return r2

            if not ck and not u:
                return DownloadResult(success=False, error="story_no_auth")
            return DownloadResult(success=False, error=r2.error or r.error)

        # ── 3. Reel / Reels → yt-dlp (cookie bilan tez va ishonchli) ─────────
        rl_m = _REEL_RE.search(url)
        if rl_m:
            logger.info("→ Reel/Reels %s", rl_m.group(1))
            # Avval yt-dlp
            r = _ytdlp_download(url, tmp, pfx, ck)
            if r.success:
                return r
            logger.info("yt-dlp reel yuklamadi (%s) → instaloader", r.error)
            # Fallback: instaloader
            r2 = _dl_post(rl_m.group(1), tmp, before, u, p, sf)
            return r2 if r2.success else r

        # ── 4. Post → instaloader (rasm+video+karusel) ────────────────────────
        post_m = _POST_RE.search(url)
        if post_m:
            logger.info("→ Post %s", post_m.group(1))
            r = _dl_post(post_m.group(1), tmp, before, u, p, sf)
            if r.success:
                return r
            logger.info("instaloader post yuklamadi (%s) → yt-dlp", r.error)
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
                logger.warning("skip katta fayl: %.1fMB", item.size_bytes / 1_048_576)
                _del(item.path)
                _del(item.audio_path or "")
                continue
            valid.append(item)

        if not valid and result.items:
            return DownloadResult(success=False, error="file_too_large:all")
        result.items = valid
        return result