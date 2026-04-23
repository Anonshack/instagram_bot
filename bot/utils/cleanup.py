"""
bot/utils/cleanup.py — Temporary file management

Every downloaded file is tracked here.  After delivery, call cleanup_files()
to wipe them immediately — keeping disk usage near zero.
"""

import asyncio
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


async def cleanup_files(*paths: str | Path) -> None:
    """
    Asynchronously delete one or more files.
    Silently ignores files that don't exist (already cleaned up).
    """
    loop = asyncio.get_running_loop()
    for path in paths:
        p = Path(path)
        try:
            await loop.run_in_executor(None, _safe_delete, p)
        except Exception as exc:
            logger.warning("Could not delete %s: %s", p, exc)


def _safe_delete(path: Path) -> None:
    if path.exists():
        path.unlink()
        logger.debug("🗑  Deleted temp file: %s", path)


async def cleanup_directory(directory: str | Path) -> None:
    """Remove all files in a directory (not subdirs). Used for periodic sweeps."""
    loop = asyncio.get_running_loop()
    d = Path(directory)
    if not d.is_dir():
        return
    files = list(d.iterdir())
    for f in files:
        if f.is_file():
            try:
                await loop.run_in_executor(None, _safe_delete, f)
            except Exception as exc:
                logger.warning("Sweep: could not delete %s: %s", f, exc)


def ensure_tmp_dir(tmp_dir: str) -> Path:
    """Create the temp directory if it doesn't exist."""
    path = Path(tmp_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path
