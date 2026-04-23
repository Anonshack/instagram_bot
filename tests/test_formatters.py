"""
tests/test_formatters.py — Message formatter unit tests
"""

import pytest
from bot.utils.formatters import (
    welcome_message,
    help_message,
    format_history,
    format_stats,
    error_file_too_large,
    error_download_failed,
    DOWNLOADING,
    UPLOADING,
    DONE,
)


def test_welcome_contains_name():
    msg = welcome_message("Alice")
    assert "Alice" in msg


def test_welcome_contains_key_info():
    msg = welcome_message("Bob")
    assert "Instagram" in msg or "Insta" in msg


def test_help_contains_commands():
    msg = help_message()
    for cmd in ["/start", "/help", "/history", "/stats"]:
        assert cmd in msg


def test_format_history_empty():
    msg = format_history([])
    assert "empty" in msg.lower() or "no download" in msg.lower()


def test_format_history_with_records():
    records = [
        {
            "link": "https://instagram.com/p/ABC123/",
            "media_type": "video",
            "status": "ok",
            "created_at": "2024-06-01T14:30:00",
        },
        {
            "link": "https://instagram.com/reel/XYZ/",
            "media_type": "image",
            "status": "failed",
            "created_at": "2024-06-01T13:00:00",
        },
    ]
    msg = format_history(records)
    assert "ABC123" in msg
    assert "✅" in msg   # ok status
    assert "❌" in msg   # failed status


def test_format_stats_shows_numbers():
    msg = format_stats(
        global_stats={"total_downloads": 42, "total_users": 7, "today_downloads": 3},
        user_stats={"user_downloads": 5},
    )
    assert "42" in msg
    assert "7" in msg
    assert "5" in msg


def test_error_file_too_large_shows_size():
    msg = error_file_too_large(73.4)
    assert "73.4" in msg


def test_error_download_failed_shows_reason():
    msg = error_download_failed("Connection timeout")
    assert "Connection timeout" in msg


def test_progress_messages_not_empty():
    for msg in [DOWNLOADING, UPLOADING, DONE]:
        assert len(msg) > 10
