"""SQLite persistence for watched folders, indexed files, and search caches."""

from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


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
CREATE INDEX IF NOT EXISTS idx_files_folder ON files(folder_id);
CREATE INDEX IF NOT EXISTS idx_files_modified ON files(modified_at DESC);
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
"""


class Database:
    """Small transaction-oriented SQLite wrapper.

    A connection is opened per operation, making the service safe to use from
    a watcher thread and straightforward to embed in a future HTTP server.
    """

    def __init__(self, path: str | Path = "filememory.sqlite3") -> None:
        self.path = str(path)
        self._memory_connection: sqlite3.Connection | None = None
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        else:
            self._memory_connection = sqlite3.connect(":memory:", timeout=30)
            self._memory_connection.row_factory = sqlite3.Row
        self.initialize()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
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
        normalized = str(Path(path).expanduser().resolve())
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
        normalized = str(Path(path).expanduser().resolve())
        with self.connection() as connection:
            result = connection.execute(
                "DELETE FROM watched_folders WHERE path = ?", (normalized,)
            )
        return result.rowcount > 0

    def folder_for_path(self, path: str | Path) -> int | None:
        normalized = str(Path(path).expanduser().resolve())
        with self.connection() as connection:
            row = connection.execute(
                """SELECT id FROM watched_folders
                   WHERE ? = path OR ? LIKE path || ?
                   ORDER BY length(path) DESC LIMIT 1""",
                (normalized, normalized, "/%" if "/" in normalized else "\\%"),
            ).fetchone()
        return int(row[0]) if row else None

    def get_file(self, path: str | Path) -> dict[str, Any] | None:
        normalized = str(Path(path).expanduser().resolve())
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
