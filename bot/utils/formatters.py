"""
bot/utils/formatters.py — Message template helpers

All user-facing text lives here.  Change text in one place → changes everywhere.
"""

from datetime import datetime


# ── Welcome / Onboarding ─────────────────────────────────────────────────────

def welcome_message(first_name: str) -> str:
    return (
        f"👋 Hey, <b>{first_name}</b>! Welcome to <b>InstaFetch</b>\n\n"
        "The fastest way to save Instagram content — without leaving Telegram.\n\n"
        "╔══════════════════════════╗\n"
        "║  📸  Posts & Carousels   ║\n"
        "║  🎬  Reels & Videos      ║\n"
        "║  📖  Public Stories      ║\n"
        "╚══════════════════════════╝\n\n"
        "⚡ Best quality  •  📦 Zero storage  •  🔒 Private & safe\n\n"
        "Just paste any Instagram link below 👇"
    )


def help_message() -> str:
    return (
        "📖 <b>How to use InstaFetch</b>\n\n"
        "Simply send me any public Instagram link:\n\n"
        "🔗 <b>Supported formats:</b>\n"
        "  • <code>https://instagram.com/p/ABC123/</code>  — Post\n"
        "  • <code>https://instagram.com/reel/XYZ789/</code> — Reel\n"
        "  • <code>https://instagram.com/stories/user/123/</code> — Story\n\n"
        "🤖 <b>Commands:</b>\n"
        "  /start   — Welcome screen\n"
        "  /help    — This guide\n"
        "  /history — Your last 5 downloads\n"
        "  /stats   — Usage statistics\n\n"
        "⚠️ <b>Limitations:</b>\n"
        "  • Only <b>public</b> accounts are supported\n"
        "  • Max file size: <b>50 MB</b>\n\n"
        "💡 Tip: For carousels, all slides are sent automatically!"
    )


# ── Progress messages ─────────────────────────────────────────────────────────

DOWNLOADING = "⏳ <b>Downloading your media…</b>\nHanging tight, this takes a second."
PROCESSING  = "⚡ <b>Processing…</b>\nAlmost there!"
UPLOADING   = "📤 <b>Uploading to Telegram…</b>\nAlmost done!"
DONE        = (
    "✅ <b>Done!</b> Enjoy your media 🎉\n\n"
    "⚡ Fast  •  📦 Zero storage  •  🔒 Safe\n\n"
    "Send another link anytime 👇"
)


# ── Error messages ────────────────────────────────────────────────────────────

def error_invalid_url() -> str:
    return (
        "❌ <b>Invalid Instagram link</b>\n\n"
        "That doesn't look like a valid Instagram URL.\n\n"
        "✅ <b>Expected formats:</b>\n"
        "  • <code>instagram.com/p/…</code>\n"
        "  • <code>instagram.com/reel/…</code>\n"
        "  • <code>instagram.com/stories/…</code>\n\n"
        "Please check the link and try again 👇"
    )


def error_private_content() -> str:
    return (
        "🔒 <b>Private Content</b>\n\n"
        "This account is <b>private</b> or the post has been deleted.\n\n"
        "InstaFetch can only download content from <b>public</b> accounts.\n\n"
        "Try a different link 👇"
    )


def error_file_too_large(size_mb: float) -> str:
    return (
        f"📦 <b>File Too Large ({size_mb:.1f} MB)</b>\n\n"
        "Telegram's bot API limits uploads to <b>50 MB</b>.\n"
        "Unfortunately this file exceeds that limit.\n\n"
        "Try a shorter video or lower-quality source."
    )


def error_download_failed(reason: str = "") -> str:
    detail = f"\n\n<i>Details: {reason[:200]}</i>" if reason else ""
    return (
        "⚠️ <b>Download Failed</b>\n\n"
        "Something went wrong while fetching your media.\n"
        "This can happen when:\n"
        "  • The link has expired\n"
        "  • Instagram rate-limited the request\n"
        "  • The content was removed\n\n"
        "Please try again in a moment 🔄" + detail
    )


def error_generic() -> str:
    return (
        "😓 <b>Something went wrong</b>\n\n"
        "An unexpected error occurred.\n"
        "Please try again or send a different link."
    )


# ── History ───────────────────────────────────────────────────────────────────

def format_history(records: list[dict]) -> str:
    if not records:
        return (
            "📭 <b>No downloads yet</b>\n\n"
            "Your download history is empty.\n"
            "Send an Instagram link to get started! 👇"
        )

    icons = {"video": "🎬", "image": "📸", "carousel": "🖼", "unknown": "📎"}
    lines = ["📋 <b>Your Last Downloads</b>\n"]
    for i, rec in enumerate(records, 1):
        icon = icons.get(rec.get("media_type", "unknown"), "📎")
        dt_raw = rec.get("created_at", "")
        try:
            dt = datetime.fromisoformat(dt_raw).strftime("%d %b, %H:%M")
        except Exception:
            dt = dt_raw[:16]
        short_link = rec["link"][:45] + ("…" if len(rec["link"]) > 45 else "")
        status_mark = "✅" if rec.get("status") == "ok" else "❌"
        lines.append(f"{i}. {icon} {status_mark} <code>{short_link}</code>\n    🕐 {dt}")

    lines.append("\nSend a new link anytime 👇")
    return "\n".join(lines)


# ── Stats ─────────────────────────────────────────────────────────────────────

def format_stats(global_stats: dict, user_stats: dict) -> str:
    return (
        "📊 <b>InstaFetch Statistics</b>\n\n"
        "┌─────────────────────────┐\n"
        f"│  👤 Your downloads:  <b>{user_stats['user_downloads']}</b>\n"
        "├─────────────────────────┤\n"
        f"│  🌍 Total downloads: <b>{global_stats['total_downloads']}</b>\n"
        f"│  👥 Total users:     <b>{global_stats['total_users']}</b>\n"
        f"│  📅 Today:          <b>{global_stats['today_downloads']}</b>\n"
        "└─────────────────────────┘\n\n"
        "Thanks for using <b>InstaFetch</b>! 🚀"
    )
