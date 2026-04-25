from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from rezeror.config import PROGRESS_DB_PATH, ensure_data_dirs


def _connect() -> sqlite3.Connection:
    ensure_data_dirs()
    conn = sqlite3.connect(PROGRESS_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_progress_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS progress (
                chapter_path TEXT PRIMARY KEY,
                scroll_y INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )


def save_progress(chapter_path: str, scroll_y: int) -> None:
    now = datetime.now(UTC).isoformat()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO progress(chapter_path, scroll_y, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(chapter_path)
            DO UPDATE SET scroll_y = excluded.scroll_y, updated_at = excluded.updated_at
            """,
            (chapter_path, scroll_y, now),
        )


def get_progress(chapter_path: str) -> int:
    with _connect() as conn:
        row = conn.execute(
            "SELECT scroll_y FROM progress WHERE chapter_path = ?",
            (chapter_path,),
        ).fetchone()
    if row is None:
        return 0
    return int(row["scroll_y"])


def has_progress(chapter_path: str) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM progress WHERE chapter_path = ? LIMIT 1",
            (chapter_path,),
        ).fetchone()
    return row is not None


def count_progress_rows() -> int:
    init_progress_db()
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS count FROM progress").fetchone()
    return int(row["count"])
