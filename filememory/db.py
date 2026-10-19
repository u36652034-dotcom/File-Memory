"""SQLite persistence for watched folders, indexed files, and search caches."""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .paths import default_database_path


def canonical_path(path: str | Path) -> Path:
    # Preserve the user's display casing in SQLite records. Windows path
    # comparisons remain safe because callers resolve one canonical absolute
    # path before querying; a future schema migration can add a separate
    # case-folded key without rewriting displayed paths.
    return Path(path).expanduser().resolve(strict=False)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS watched_folders (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1))
);
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY,
    folder_id INTEGER REFERENCES watched_folders(id) ON DELETE SET NULL,
    path TEXT NOT NULL UNIQUE,
    filename TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    modified_at TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    mime_type TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    content_fingerprint TEXT NOT NULL UNIQUE,
    snippet TEXT NOT NULL DEFAULT '',
    embedding_json TEXT,
    embedding_model TEXT,
    indexed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pending_suggestions (
    id INTEGER PRIMARY KEY,
    file_id INTEGER NOT NULL UNIQUE REFERENCES files(id) ON DELETE CASCADE,
    path TEXT NOT NULL UNIQUE,
    suggested_note TEXT NOT NULL,
    provider TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_files_folder ON files(folder_id);
CREATE INDEX IF NOT EXISTS idx_files_modified ON files(modified_at DESC);
CREATE INDEX IF NOT EXISTS idx_pending_suggestions_created ON pending_suggestions(created_at DESC);
CREATE VIRTUAL TABLE IF NOT EXISTS files_fts USING fts5(
    filename, note, snippet, path,
    content='files', content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);
CREATE TRIGGER IF NOT EXISTS files_ai AFTER INSERT ON files BEGIN
    INSERT INTO files_fts(rowid, filename, note, snippet, path)
    VALUES (new.id, new.filename, new.note, new.snippet, new.path);
END;
CREATE TRIGGER IF NOT EXISTS files_ad AFTER DELETE ON files BEGIN
    INSERT INTO files_fts(files_fts, rowid, filename, note, snippet, path)
    VALUES ('delete', old.id, old.filename, old.note, old.snippet, old.path);
END;
CREATE TRIGGER IF NOT EXISTS files_au AFTER UPDATE ON files BEGIN
    INSERT INTO files_fts(files_fts, rowid, filename, note, snippet, path)
    VALUES ('delete', old.id, old.filename, old.note, old.snippet, old.path);
    INSERT INTO files_fts(rowid, filename, note, snippet, path)
    VALUES (new.id, new.filename, new.note, new.snippet, new.path);
END;
CREATE TABLE IF NOT EXISTS search_cache (
    cache_key TEXT PRIMARY KEY,
    query TEXT NOT NULL,
    mode TEXT NOT NULL,
    results_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL
);
INSERT OR IGNORE INTO settings(key, value_json) VALUES
    ('tracking_paused', 'false'),
    ('ai_mode', '"no_ai"'),
    ('ignored_extensions', '[]');
"""


class Database:
    """Small transaction-oriented SQLite wrapper.

    A connection is opened per operation, making the service safe to use from
    a watcher thread and straightforward to embed in a future HTTP server.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = str(default_database_path() if path is None else path)
        self._memory_connection: sqlite3.Connection | None = None
        self._memory_lock = threading.RLock()
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        else:
            self._memory_connection = sqlite3.connect(":memory:", timeout=30, check_same_thread=False)
            self._memory_connection.row_factory = sqlite3.Row
        self.initialize()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        lock = self._memory_lock if self._memory_connection is not None else nullcontext()
        with lock:
            connection = self._memory_connection or sqlite3.connect(self.path, timeout=30)
            if self._memory_connection is None:
                connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            try:
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                if self._memory_connection is None:
                    connection.close()

    def initialize(self) -> None:
        with self.connection() as connection:
            connection.executescript(SCHEMA)

    def add_folder(self, path: str | Path) -> dict[str, Any]:
        normalized = str(canonical_path(path))
        with self.connection() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO watched_folders(path, created_at) VALUES (?, ?)",
                (normalized, utc_now()),
            )
            row = connection.execute(
                "SELECT * FROM watched_folders WHERE path = ?", (normalized,)
            ).fetchone()
        return dict(row)

    def list_folders(self) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM watched_folders ORDER BY path"
            ).fetchall()
        return [dict(row) for row in rows]

    def remove_folder(self, path: str | Path) -> bool:
        normalized = str(canonical_path(path))
        with self.connection() as connection:
            result = connection.execute(
                "DELETE FROM watched_folders WHERE path = ?", (normalized,)
            )
        return result.rowcount > 0

    def get_settings(self) -> dict[str, Any]:
        with self.connection() as connection:
            rows = connection.execute("SELECT key, value_json FROM settings").fetchall()
        return {row["key"]: json.loads(row["value_json"]) for row in rows}

    def set_setting(self, key: str, value: Any) -> None:
        with self.connection() as connection:
            connection.execute(
                """INSERT INTO settings(key, value_json) VALUES (?, ?)
                   ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json""",
                (key, json.dumps(value)),
            )

    def delete_file(self, path: str | Path) -> bool:
        normalized = str(canonical_path(path))
        with self.connection() as connection:
            result = connection.execute("DELETE FROM files WHERE path = ?", (normalized,))
            connection.execute("DELETE FROM search_cache")
        return result.rowcount > 0

    def rebuild_search_index(self) -> int:
        with self.connection() as connection:
            connection.execute("INSERT INTO files_fts(files_fts) VALUES ('rebuild')")
            connection.execute("DELETE FROM search_cache")
            row = connection.execute("SELECT COUNT(*) FROM files").fetchone()
        return int(row[0])

    def folder_for_path(self, path: str | Path) -> int | None:
        candidate = canonical_path(path)
        matches: list[tuple[int, int]] = []
        with self.connection() as connection:
            rows = connection.execute("SELECT id, path FROM watched_folders WHERE enabled = 1").fetchall()
        for row in rows:
            try:
                candidate.relative_to(canonical_path(row["path"]))
            except ValueError:
                continue
            matches.append((int(row["id"]), len(canonical_path(row["path"]).parts)))
        return max(matches, key=lambda item: item[1])[0] if matches else None

    def get_file(self, path: str | Path) -> dict[str, Any] | None:
        normalized = str(canonical_path(path))
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM files WHERE path = ?", (normalized,)).fetchone()
        return dict(row) if row else None

    def get_fingerprint(self, fingerprint: str) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM files WHERE content_fingerprint = ?", (fingerprint,)
            ).fetchone()
        return dict(row) if row else None

    def upsert_file(self, values: dict[str, Any]) -> dict[str, Any]:
        columns = (
            "folder_id", "path", "filename", "note", "created_at", "modified_at",
            "size_bytes", "mime_type", "metadata_json", "content_fingerprint",
            "snippet", "embedding_json", "embedding_model", "indexed_at",
        )
        with self.connection() as connection:
            connection.execute(
                f"""INSERT INTO files ({', '.join(columns)})
                    VALUES ({', '.join('?' for _ in columns)})
                    ON CONFLICT(path) DO UPDATE SET
                    folder_id=excluded.folder_id, filename=excluded.filename,
                    note=excluded.note, modified_at=excluded.modified_at,
                    size_bytes=excluded.size_bytes, mime_type=excluded.mime_type,
                    metadata_json=excluded.metadata_json,
                    content_fingerprint=excluded.content_fingerprint,
                    snippet=excluded.snippet, embedding_json=excluded.embedding_json,
                    embedding_model=excluded.embedding_model, indexed_at=excluded.indexed_at""",
                tuple(values.get(column) for column in columns),
            )
            row = connection.execute("SELECT * FROM files WHERE path = ?", (values["path"],)).fetchone()
        return dict(row)

    def list_files(self) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute("SELECT * FROM files ORDER BY indexed_at DESC").fetchall()
        return [dict(row) for row in rows]

    def add_pending_suggestion(
        self, file_id: int, path: str | Path, suggested_note: str, provider: str
    ) -> dict[str, Any]:
        normalized = str(canonical_path(path))
        with self.connection() as connection:
            connection.execute(
                """INSERT INTO pending_suggestions
                   (file_id, path, suggested_note, provider, created_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(path) DO UPDATE SET
                   file_id=excluded.file_id, suggested_note=excluded.suggested_note,
                   provider=excluded.provider, created_at=excluded.created_at""",
                (file_id, normalized, suggested_note, provider, utc_now()),
            )
            row = connection.execute(
                """SELECT p.*, f.filename, f.snippet, f.modified_at, f.size_bytes,
                          f.mime_type
                   FROM pending_suggestions p JOIN files f ON f.id = p.file_id
                   WHERE p.path = ?""",
                (normalized,),
            ).fetchone()
        return dict(row)

    def list_pending_suggestions(self) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute(
                """SELECT p.*, f.filename, f.snippet, f.modified_at, f.size_bytes,
                          f.mime_type
                   FROM pending_suggestions p JOIN files f ON f.id = p.file_id
                   ORDER BY p.created_at DESC"""
            ).fetchall()
        return [dict(row) for row in rows]

    def get_pending_suggestion(self, suggestion_id: int) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = connection.execute(
                """SELECT p.*, f.filename, f.snippet, f.modified_at, f.size_bytes,
                          f.mime_type
                   FROM pending_suggestions p JOIN files f ON f.id = p.file_id
                   WHERE p.id = ?""",
                (suggestion_id,),
            ).fetchone()
        return dict(row) if row else None

    def clear_pending_suggestion(self, path: str | Path) -> bool:
        normalized = str(canonical_path(path))
        with self.connection() as connection:
            result = connection.execute(
                "DELETE FROM pending_suggestions WHERE path = ?", (normalized,)
            )
        return result.rowcount > 0

    def confirm_pending_suggestion(self, suggestion_id: int, note: str) -> dict[str, Any] | None:
        with self.connection() as connection:
            suggestion = connection.execute(
                "SELECT file_id FROM pending_suggestions WHERE id = ?", (suggestion_id,)
            ).fetchone()
            if not suggestion:
                return None
            connection.execute(
                "UPDATE files SET note = ? WHERE id = ?", (note, suggestion[0])
            )
            connection.execute(
                "DELETE FROM pending_suggestions WHERE id = ?", (suggestion_id,)
            )
            connection.execute("DELETE FROM search_cache")
            row = connection.execute(
                "SELECT * FROM files WHERE id = ?", (suggestion[0],)
            ).fetchone()
        return dict(row)

    def keyword_search(self, query: str, limit: int) -> list[dict[str, Any]]:
        terms = re.findall(r"[\w-]+", query, flags=re.UNICODE)
        if not terms:
            return []
        # OR keeps natural-language questions useful when only some terms are present.
        match = " OR ".join(f'"{term}"' for term in terms)
        with self.connection() as connection:
            rows = connection.execute(
                """SELECT f.*, bm25(files_fts) AS rank
                   FROM files_fts JOIN files f ON f.id = files_fts.rowid
                   WHERE files_fts MATCH ? ORDER BY rank LIMIT ?""",
                (match, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def cache_get(self, cache_key: str) -> list[dict[str, Any]] | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT results_json FROM search_cache WHERE cache_key = ?", (cache_key,)
            ).fetchone()
        if not row:
            return None
        return json.loads(row[0])

    def cache_put(self, cache_key: str, query: str, mode: str, results: list[dict[str, Any]]) -> None:
        with self.connection() as connection:
            connection.execute(
                """INSERT INTO search_cache(cache_key, query, mode, results_json, created_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(cache_key) DO UPDATE SET query=excluded.query,
                   mode=excluded.mode, results_json=excluded.results_json,
                   created_at=excluded.created_at""",
                (cache_key, query, mode, json.dumps(results, default=str), utc_now()),
            )

    def clear_file_cache(self, path: str) -> None:
        # Search caches contain snapshots; clear them when indexed content changes.
        with self.connection() as connection:
            connection.execute("DELETE FROM search_cache")
