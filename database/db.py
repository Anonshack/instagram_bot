"""
database/db.py — Lightweight SQLite layer (async via aiosqlite)

Tables
──────
  users       – first-seen metadata
  downloads   – every successful download (for /history & /stats)
"""

import aiosqlite
import asyncio
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def init(self):
        """Create tables if they don't exist."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id     INTEGER PRIMARY KEY,
                    username    TEXT,
                    first_name  TEXT,
                    joined_at   TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS downloads (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     INTEGER NOT NULL,
                    link        TEXT NOT NULL,
                    media_type  TEXT,            -- 'video' | 'image' | 'carousel'
                    status      TEXT DEFAULT 'ok', -- 'ok' | 'failed'
                    created_at  TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                );
            """)
            await db.commit()
        logger.info("✅  Database ready at %s", self.db_path)

    # ── Users ────────────────────────────────────────────────────────────────

    async def upsert_user(self, user_id: int, username: str | None, first_name: str | None):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO users (user_id, username, first_name, joined_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username   = excluded.username,
                    first_name = excluded.first_name
            """, (user_id, username, first_name, datetime.utcnow().isoformat()))
            await db.commit()

    # ── Downloads ────────────────────────────────────────────────────────────

    async def log_download(
        self,
        user_id: int,
        link: str,
        media_type: str = "unknown",
        status: str = "ok",
    ) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO downloads (user_id, link, media_type, status, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, link, media_type, status, datetime.utcnow().isoformat()))
            await db.commit()
            return cursor.lastrowid

    async def get_user_history(self, user_id: int, limit: int = 5) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT link, media_type, status, created_at
                FROM downloads
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (user_id, limit))
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    # ── Stats ────────────────────────────────────────────────────────────────

    async def get_global_stats(self) -> dict:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            total_cur = await db.execute(
                "SELECT COUNT(*) as cnt FROM downloads WHERE status = 'ok'"
            )
            total_row = await total_cur.fetchone()

            users_cur = await db.execute("SELECT COUNT(*) as cnt FROM users")
            users_row = await users_cur.fetchone()

            today_cur = await db.execute("""
                SELECT COUNT(*) as cnt FROM downloads
                WHERE status = 'ok' AND DATE(created_at) = DATE('now')
            """)
            today_row = await today_cur.fetchone()

            return {
                "total_downloads": total_row["cnt"],
                "total_users": users_row["cnt"],
                "today_downloads": today_row["cnt"],
            }

    async def get_user_stats(self, user_id: int) -> dict:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT COUNT(*) as cnt FROM downloads
                WHERE user_id = ? AND status = 'ok'
            """, (user_id,))
            row = await cursor.fetchone()
            return {"user_downloads": row["cnt"]}
