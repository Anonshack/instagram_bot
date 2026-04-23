"""
config.py — Centralized configuration for the Instagram Downloader Bot
Loads settings from environment variables OR a .env file automatically.
"""

import os
from dataclasses import dataclass
from pathlib import Path


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
    # ── Telegram ────────────────────────────────────────────────────────────
    BOT_TOKEN: str

    # ── Storage ─────────────────────────────────────────────────────────────
    TMP_DIR: str = "/tmp/instabot"
    MAX_FILE_SIZE_MB: int = 50

    # ── Database ────────────────────────────────────────────────────────────
    DB_PATH: str = "database/bot.db"

    # ── Download ─────────────────────────────────────────────────────────────
    DOWNLOAD_TIMEOUT: int = 300
    MAX_CAROUSEL_ITEMS: int = 10

    # ── Rate limiting ────────────────────────────────────────────────────────
    COOLDOWN_SECONDS: int = 5

    # ── Instagram Cookie ────────────────────────────────────────────────────
    # cookies.txt fayli yo'li (Netscape format)
    # Bo'sh qoldirilsa — cookie siz ishlaydi (ba'zi postlar yuklanmasligi mumkin)
    COOKIES_FILE: str = "cookies.txt"


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise EnvironmentError(
            "❌  BOT_TOKEN topilmadi!\n"
            "    .env faylida BOT_TOKEN=your_token borligini tekshiring\n"
            "    yoki: export BOT_TOKEN='your_token'"
        )
    cookies_file = os.getenv("COOKIES_FILE", "cookies.txt")
    return Config(BOT_TOKEN=token, COOKIES_FILE=cookies_file)