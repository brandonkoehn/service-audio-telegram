"""SQLite-backed state for tracking uploads and scheduled deletions."""
import sqlite3
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


class State:
    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self):
        with self._conn() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS uploaded_files (
                    source_path TEXT PRIMARY KEY,
                    file_size INTEGER NOT NULL,
                    file_mtime REAL NOT NULL,
                    message_id INTEGER NOT NULL,
                    uploaded_at TEXT NOT NULL,
                    delete_after TEXT NOT NULL,
                    deleted INTEGER NOT NULL DEFAULT 0
                )
            """)

    def has_been_uploaded(self, source_path: str, file_size: int, file_mtime: float) -> bool:
        with self._conn() as c:
            row = c.execute(
                "SELECT file_size, file_mtime FROM uploaded_files WHERE source_path = ?",
                (source_path,),
            ).fetchone()
            if row is None:
                return False
            # Same path AND same size/mtime = already handled.
            # If size or mtime changed, it's a new recording overwriting the old name.
            return row["file_size"] == file_size and abs(row["file_mtime"] - file_mtime) < 1.0

    def record_upload(
        self,
        source_path: str,
        file_size: int,
        file_mtime: float,
        message_id: int,
        delete_after: datetime,
    ):
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as c:
            c.execute(
                """INSERT OR REPLACE INTO uploaded_files
                   (source_path, file_size, file_mtime, message_id, uploaded_at, delete_after, deleted)
                   VALUES (?, ?, ?, ?, ?, ?, 0)""",
                (source_path, file_size, file_mtime, message_id, now, delete_after.isoformat()),
            )

    def pending_deletions(self) -> list:
        """Return list of (source_path, message_id) for messages past their delete_after time."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as c:
            rows = c.execute(
                """SELECT source_path, message_id FROM uploaded_files
                   WHERE deleted = 0 AND delete_after <= ?""",
                (now,),
            ).fetchall()
            return [(r["source_path"], r["message_id"]) for r in rows]

    def mark_deleted(self, source_path: str):
        with self._conn() as c:
            c.execute(
                "UPDATE uploaded_files SET deleted = 1 WHERE source_path = ?",
                (source_path,),
            )
