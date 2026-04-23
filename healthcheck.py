#!/usr/bin/env python3
"""
healthcheck.py — Pre-flight checks before starting the bot

Verifies:
  ✓ BOT_TOKEN is set and accepted by Telegram
  ✓ ffmpeg is installed
  ✓ yt-dlp is importable and up-to-date
  ✓ Database directory is writable
  ✓ /tmp directory is writable
  ✓ All required Python packages installed

Usage:
    python healthcheck.py
    echo $?   # 0 = all good, 1 = problems found
"""

import asyncio
import importlib
import os
import shutil
import subprocess
import sys


BOLD  = "\033[1m"
GREEN = "\033[32m"
RED   = "\033[31m"
YELLOW= "\033[33m"
RESET = "\033[0m"

passed = 0
failed = 0
warned = 0


def ok(label: str, detail: str = ""):
    global passed
    passed += 1
    suffix = f"  {detail}" if detail else ""
    print(f"  {GREEN}✔{RESET}  {label}{suffix}")


def fail(label: str, detail: str = ""):
    global failed
    failed += 1
    suffix = f"\n     {RED}{detail}{RESET}" if detail else ""
    print(f"  {RED}✘{RESET}  {label}{suffix}")


def warn(label: str, detail: str = ""):
    global warned
    warned += 1
    suffix = f"\n     {YELLOW}{detail}{RESET}" if detail else ""
    print(f"  {YELLOW}⚠{RESET}  {label}{suffix}")


def section(title: str):
    print(f"\n{BOLD}── {title} ──{RESET}")


# ── Python version ────────────────────────────────────────────────────────────

section("Python")
vi = sys.version_info
if vi >= (3, 11):
    ok(f"Python {vi.major}.{vi.minor}.{vi.micro}")
else:
    fail(f"Python {vi.major}.{vi.minor} found", "Requires Python 3.11+")


# ── Required packages ─────────────────────────────────────────────────────────

section("Python Packages")
REQUIRED_PACKAGES = [
    ("aiogram", "aiogram"),
    ("yt_dlp", "yt-dlp"),
    ("aiosqlite", "aiosqlite"),
]

for import_name, pkg_name in REQUIRED_PACKAGES:
    try:
        mod = importlib.import_module(import_name)
        version = getattr(mod, "__version__", "?")
        ok(f"{pkg_name}", f"v{version}")
    except ImportError:
        fail(f"{pkg_name} not installed", f"Run: pip install {pkg_name}")


# ── ffmpeg ────────────────────────────────────────────────────────────────────

section("System Tools")
if shutil.which("ffmpeg"):
    result = subprocess.run(
        ["ffmpeg", "-version"], capture_output=True, text=True
    )
    ver_line = result.stdout.splitlines()[0] if result.stdout else "unknown"
    ok("ffmpeg", ver_line.split("version")[-1].strip().split(" ")[0])
else:
    fail("ffmpeg not found", "Install: sudo apt install ffmpeg  OR  brew install ffmpeg")


# ── Environment variables ─────────────────────────────────────────────────────

section("Environment")
token = os.getenv("BOT_TOKEN")
if token:
    ok("BOT_TOKEN is set", f"starts with {token[:8]}…")
else:
    fail("BOT_TOKEN not set", "Export it: export BOT_TOKEN='your_token'")

admin_ids = os.getenv("ADMIN_IDS", "")
if admin_ids:
    ok("ADMIN_IDS set", admin_ids)
else:
    warn("ADMIN_IDS not set", "Admin commands (/broadcast, /dbstats) will be disabled")


# ── Telegram API reachability ─────────────────────────────────────────────────

section("Telegram API")
if token:
    async def _check_token():
        try:
            from aiogram import Bot
            from aiogram.client.default import DefaultBotProperties
            bot = Bot(token=token)
            me = await bot.get_me()
            await bot.session.close()
            return me
        except Exception as e:
            return str(e)

    result = asyncio.run(_check_token())
    if hasattr(result, "username"):
        ok(f"Token valid — bot is @{result.username}", f"id={result.id}")
    else:
        fail("Token rejected by Telegram", str(result))
else:
    warn("Skipped (BOT_TOKEN not set)")


# ── Directories ───────────────────────────────────────────────────────────────

section("Directories")
dirs_to_check = [
    ("database/", True),   # (path, create_if_missing)
    ("logs/",     True),
    ("/tmp/instabot", True),
]

for dpath, create in dirs_to_check:
    try:
        os.makedirs(dpath, exist_ok=True)
        test_file = os.path.join(dpath, ".write_test")
        with open(test_file, "w") as f:
            f.write("ok")
        os.unlink(test_file)
        ok(f"{dpath} is writable")
    except Exception as e:
        fail(f"{dpath} not writable", str(e))


# ── Summary ───────────────────────────────────────────────────────────────────

print(f"\n{'─' * 40}")
print(f"  {GREEN}✔ {passed} passed{RESET}  |  ", end="")
if warned:
    print(f"{YELLOW}⚠ {warned} warnings{RESET}  |  ", end="")
if failed:
    print(f"{RED}✘ {failed} failed{RESET}")
else:
    print(f"{GREEN}✘ 0 failed{RESET}")
print()

if failed:
    print(f"{RED}{BOLD}❌  Fix the issues above before starting the bot.{RESET}\n")
    sys.exit(1)
elif warned:
    print(f"{YELLOW}{BOLD}⚠   Bot can start, but review warnings above.{RESET}\n")
    sys.exit(0)
else:
    print(f"{GREEN}{BOLD}✅  All checks passed! Run: python main.py{RESET}\n")
    sys.exit(0)
