# 📸 InstaFetch — Telegram Instagram Downloader Bot

A production-quality Telegram bot that downloads Instagram posts, reels,
carousels, and public stories — then sends them directly to users.

Built with **aiogram 3**, **yt-dlp**, and **aiosqlite**.

---

## ✨ Features

| Feature | Details |
|---|---|
| 📸 Posts | Single image or video |
| 🖼 Carousels | All slides, sent as an album |
| 🎬 Reels | HD video with audio |
| 📖 Stories | Public accounts only |
| 📦 Zero storage | Files deleted immediately after sending |
| 📋 History | `/history` — last 5 downloads per user |
| 📊 Stats | `/stats` — global and personal counters |
| ⚡ Async | Multiple users handled simultaneously |
| 🧹 Auto-cleanup | Periodic sweep of the `/tmp` directory |
| 🔒 Error handling | Friendly messages for private/invalid content |

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- `ffmpeg` installed on the system
- A Telegram bot token from [@BotFather](https://t.me/BotFather)

### 1. Clone & Install

```bash
git clone https://github.com/youruser/instagram-bot.git
cd instagram-bot

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt

# Install ffmpeg
# Ubuntu/Debian:
sudo apt install ffmpeg
# macOS:
brew install ffmpeg
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env and set your BOT_TOKEN
export BOT_TOKEN="your_token_here"
```

### 3. Run

```bash
python main.py
```

---

## 🐳 Docker (Recommended for Production)

```bash
# Build and start
BOT_TOKEN=your_token docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

---

## 📁 Project Structure

```
instagram_bot/
├── main.py              # Entry point — bot startup & polling
├── config.py            # Configuration from env vars
├── middleware.py        # Dependency injection middleware
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
│
├── bot/
│   ├── handlers/
│   │   ├── __init__.py  # Router registry
│   │   ├── commands.py  # /start /help /history /stats
│   │   └── download.py  # Main Instagram link handler
│   │
│   ├── services/
│   │   ├── downloader.py # yt-dlp wrapper (async)
│   │   └── sender.py     # Telegram media delivery
│   │
│   ├── utils/
│   │   ├── validators.py  # URL parsing & validation
│   │   ├── cleanup.py     # File deletion helpers
│   │   └── formatters.py  # All user-facing message text
│   │
│   └── keyboards/
│       └── inline.py      # Inline keyboard builders
│
└── database/
    ├── __init__.py
    └── db.py              # SQLite layer (aiosqlite)
```

---

## ⚙️ Configuration

| Variable | Default | Description |
|---|---|---|
| `BOT_TOKEN` | *(required)* | Telegram bot token |
| `TMP_DIR` | `/tmp/instabot` | Temp download directory |
| `MAX_FILE_SIZE_MB` | `50` | Telegram file size limit |
| `DB_PATH` | `database/bot.db` | SQLite database path |
| `DOWNLOAD_TIMEOUT` | `120` | Seconds before timeout |
| `COOLDOWN_SECONDS` | `5` | Per-user rate limit |

---

## 🏗 Architecture

```
User sends link
      │
      ▼
  validators.py       ← Reject invalid URLs early
      │
      ▼
  downloader.py       ← yt-dlp in thread-pool executor (non-blocking)
      │
      ▼
  sender.py           ← send_video / send_photo / send_media_group
      │
      ▼
  cleanup.py          ← Delete temp files immediately
      │
      ▼
  db.py               ← Log download to SQLite
```

---

## 🔒 Privacy & Safety

- No media is stored permanently — files are deleted as soon as they're sent
- Only public Instagram content can be downloaded
- User data stored: `user_id`, `username`, `download history`
- No passwords or session cookies required

---

## 📝 Commands

| Command | Description |
|---|---|
| `/start` | Welcome screen |
| `/help` | Usage guide with examples |
| `/history` | Your last 5 downloads |
| `/stats` | Global and personal statistics |

---

## 🤝 Contributing

PRs welcome! Please keep code clean, typed, and commented.

---

## ⚠️ Legal Notice

This bot is for **personal/educational use only**.
Respect Instagram's [Terms of Service](https://help.instagram.com/581066165581870).
Only download content you have the right to save.
