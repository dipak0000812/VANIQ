"""SQLite connection handling and forward-only SQL migrations."""
from __future__ import annotations

import logging
import re
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)
MIGRATIONS_DIR = Path(__file__).parent / "migrations"


class Database:
    """Thin wrapper holding one connection guarded by a lock (adequate for a local single-user app)."""

    def __init__(self, path: str | Path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._lock = threading.RLock()
        self.migrate()

    def migrate(self) -> None:
        with self._lock:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
            applied = {r[0] for r in self._conn.execute("SELECT version FROM schema_migrations")}
            for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
                m = re.match(r"(\d+)_", f.name)
                if not m:
                    continue
                version = int(m.group(1))
                if version in applied:
                    continue
                logger.info("Applying migration %s", f.name)
                self._conn.execute("BEGIN")
                try:
                    for stmt in _split_sql(f.read_text(encoding="utf-8")):
                        self._conn.execute(stmt)
                    self._conn.execute(
                        "INSERT INTO schema_migrations(version, applied_at) VALUES (?, datetime('now'))", (version,))
                    self._conn.execute("COMMIT")
                except Exception:
                    self._conn.execute("ROLLBACK")
                    raise

    @contextmanager
    def tx(self):
        with self._lock:
            self._conn.execute("BEGIN")
            try:
                yield self._conn
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def query(self, sql: str, params: tuple = ()) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def one(self, sql: str, params: tuple = ()) -> dict | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def execute(self, sql: str, params: tuple = ()) -> int:
        with self._lock:
            cur = self._conn.execute(sql, params)
            return cur.lastrowid

    def close(self) -> None:
        self._conn.close()


def _split_sql(script: str) -> list[str]:
    cleaned = re.sub(r"--[^\n]*", "", script)  # strip SQL comments (inline ones may contain ';')
    return [s.strip() for s in cleaned.split(";") if s.strip()]
