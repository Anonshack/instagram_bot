"""
tests/test_db.py — Database layer unit tests (uses a real in-memory SQLite)
"""

import asyncio
import pytest
import pytest_asyncio

from database import Database


@pytest_asyncio.fixture
async def db(tmp_path):
    """Fresh in-memory database for each test."""
    d = Database(str(tmp_path / "test.db"))
    await d.init()
    return d


# ── User upsert ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upsert_user_creates_record(db):
    await db.upsert_user(1001, "alice", "Alice")
    stats = await db.get_global_stats()
    assert stats["total_users"] == 1


@pytest.mark.asyncio
async def test_upsert_user_idempotent(db):
    await db.upsert_user(1001, "alice", "Alice")
    await db.upsert_user(1001, "alice_new", "Alice New")
    stats = await db.get_global_stats()
    assert stats["total_users"] == 1  # still 1, not 2


# ── Download logging ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_log_download_increments_count(db):
    await db.upsert_user(1001, "alice", "Alice")
    await db.log_download(1001, "https://instagram.com/p/A/", "video", "ok")
    await db.log_download(1001, "https://instagram.com/p/B/", "image", "ok")
    stats = await db.get_global_stats()
    assert stats["total_downloads"] == 2


@pytest.mark.asyncio
async def test_failed_downloads_excluded_from_stats(db):
    await db.upsert_user(1001, "alice", "Alice")
    await db.log_download(1001, "https://instagram.com/p/A/", "video", "ok")
    await db.log_download(1001, "https://instagram.com/p/B/", "video", "failed")
    stats = await db.get_global_stats()
    assert stats["total_downloads"] == 1  # only ok


# ── History ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_user_history_limit(db):
    await db.upsert_user(1001, "alice", "Alice")
    for i in range(10):
        await db.log_download(1001, f"https://instagram.com/p/{i}/", "video", "ok")
    history = await db.get_user_history(1001, limit=5)
    assert len(history) == 5


@pytest.mark.asyncio
async def test_get_user_history_most_recent_first(db):
    await db.upsert_user(1001, "alice", "Alice")
    await db.log_download(1001, "https://instagram.com/p/FIRST/", "video", "ok")
    await db.log_download(1001, "https://instagram.com/p/LAST/", "video", "ok")
    history = await db.get_user_history(1001, limit=5)
    assert "LAST" in history[0]["link"]


@pytest.mark.asyncio
async def test_get_user_history_empty_for_new_user(db):
    history = await db.get_user_history(9999, limit=5)
    assert history == []


# ── Per-user stats ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_user_stats_counts_only_own_downloads(db):
    await db.upsert_user(1001, "alice", "Alice")
    await db.upsert_user(1002, "bob", "Bob")
    await db.log_download(1001, "https://instagram.com/p/A/", "video", "ok")
    await db.log_download(1001, "https://instagram.com/p/B/", "video", "ok")
    await db.log_download(1002, "https://instagram.com/p/C/", "video", "ok")

    alice_stats = await db.get_user_stats(1001)
    bob_stats = await db.get_user_stats(1002)

    assert alice_stats["user_downloads"] == 2
    assert bob_stats["user_downloads"] == 1
