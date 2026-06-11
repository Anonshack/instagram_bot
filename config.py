"""
config.py — All settings are loaded from .env
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def _load_dotenv(env_path: str = ".env") -> None:
    p = Path(env_path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()


@dataclass
class Config:
    # ── Telegram ──────────────────────────────────────────────────────────────
    BOT_TOKEN: str

    # ── Instagram authentication ──────────────────────────────────────────────
    # Required for Story/Highlights downloads
    IG_USERNAME: Optional[str] = None
    IG_PASSWORD: Optional[str] = None
    IG_SESSION_FILE: str = "/tmp/instabot/ig_session"

    # yt-dlp cookies (optional, helps with post/reel downloads)
    COOKIES_FILE: Optional[str] = None

    # ── Storage ───────────────────────────────────────────────────────────────
    TMP_DIR: str = "/tmp/instabot"
    MAX_FILE_SIZE_MB: int = 50

    # ── Database ──────────────────────────────────────────────────────────────
    DB_PATH: str = "database/bot.db"

    # ── Download ──────────────────────────────────────────────────────────────
    DOWNLOAD_TIMEOUT: int = 300
    MAX_CAROUSEL_ITEMS: int = 50

    # ── Rate limiting ─────────────────────────────────────────────────────────
    COOLDOWN_SECONDS: int = 5

    # ── Required subscription channel ────────────────────────────────────────
    REQUIRED_CHANNEL_ID: int = -1003602435754
    REQUIRED_CHANNEL_USERNAME: str = "pythondjangodev3"
    REQUIRED_CHANNEL_TITLE: str = "Python Django Backend Development"


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise EnvironmentError(
            "❌  BOT_TOKEN not found!\n"
            "    Make sure BOT_TOKEN=your_token is set in .env"
        )

    cookies = os.getenv("COOKIES_FILE")
    if cookies and not os.path.exists(cookies):
        cookies = None

    return Config(
        BOT_TOKEN=token,
        IG_USERNAME=os.getenv("IG_USERNAME") or None,
        IG_PASSWORD=os.getenv("IG_PASSWORD") or None,
        IG_SESSION_FILE=os.getenv("IG_SESSION_FILE", "/tmp/instabot/ig_session"),
        COOKIES_FILE=cookies,
        TMP_DIR=os.getenv("TMP_DIR", "/tmp/instabot"),
        MAX_FILE_SIZE_MB=int(os.getenv("MAX_FILE_SIZE_MB", "50")),
        DB_PATH=os.getenv("DB_PATH", "database/bot.db"),
    )