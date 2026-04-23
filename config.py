"""
config.py — Barcha sozlamalar .env dan o'qiladi
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

    # ── Instagram autentifikatsiya ────────────────────────────────────────────
    # Story/Highlights yuklab olish uchun KERAK
    IG_USERNAME: Optional[str] = None
    IG_PASSWORD: Optional[str] = None
    IG_SESSION_FILE: str = "/tmp/instabot/ig_session"

    # yt-dlp uchun cookies (ixtiyoriy, post/reel da ishlash uchun yordam beradi)
    COOKIES_FILE: Optional[str] = None

    # ── Saqlash ───────────────────────────────────────────────────────────────
    TMP_DIR: str = "/tmp/instabot"
    MAX_FILE_SIZE_MB: int = 50

    # ── Ma'lumotlar bazasi ────────────────────────────────────────────────────
    DB_PATH: str = "database/bot.db"

    # ── Yuklab olish ──────────────────────────────────────────────────────────
    DOWNLOAD_TIMEOUT: int = 300
    MAX_CAROUSEL_ITEMS: int = 50

    # ── Rate limiting ─────────────────────────────────────────────────────────
    COOLDOWN_SECONDS: int = 5


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise EnvironmentError(
            "❌  BOT_TOKEN topilmadi!\n"
            "    .env faylida BOT_TOKEN=your_token borligini tekshiring"
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