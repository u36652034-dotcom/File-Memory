"""Filesystem-to-SQLite indexing with stability and duplicate protection."""

from __future__ import annotations

import hashlib
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .db import Database, utc_now

INCOMPLETE_SUFFIXES = (".crdownload", ".part", ".partial", ".download", ".tmp")
MAX_SNIPPET_BYTES = 2048


@dataclass(frozen=True)
class IndexResult:
    status: str
    path: str
    record: dict[str, Any] | None = None


def is_incomplete_download(path: str | Path) -> bool:
    return Path(path).name.lower().endswith(INCOMPLETE_SUFFIXES)


def _text_snippet(path: Path) -> str:
    try:
        data = path.read_bytes()[:MAX_SNIPPET_BYTES]
        return data.decode("utf-8", errors="replace").replace("\x00", " ").strip()
    except (OSError, UnicodeError):
        return ""


class FileIndexer:
    def __init__(self, database: Database, stability_wait: float = 0.15) -> None:
        self.database = database
        self.stability_wait = stability_wait

    def _stable_stat(self, path: Path) -> os.stat_result | None:
        try:
            first = path.stat()
        except OSError:
            return None
        if self.stability_wait:
            import time
            time.sleep(self.stability_wait)
        try:
            second = path.stat()
        except OSError:
            return None
        if (first.st_size, first.st_mtime_ns) != (second.st_size, second.st_mtime_ns):
            return None
        return second

    def index_path(self, path: str | Path, note: str | None = None) -> IndexResult:
        candidate = Path(path).expanduser().resolve()
        if is_incomplete_download(candidate):
            return IndexResult("skipped-incomplete", str(candidate))
        if not candidate.is_file():
            return IndexResult("skipped-missing", str(candidate))
        stat = self._stable_stat(candidate)
        if stat is None:
            return IndexResult("skipped-unstable", str(candidate))
        try:
            fingerprint = hashlib.sha256(candidate.read_bytes()).hexdigest()
        except OSError:
            return IndexResult("skipped-unreadable", str(candidate))
        existing = self.database.get_fingerprint(fingerprint)
        if existing and existing["path"] != str(candidate):
            return IndexResult("skipped-duplicate", str(candidate), existing)
        previous = self.database.get_file(candidate)
        created_at = previous["created_at"] if previous else utc_now()
        record = self.database.upsert_file({
            "folder_id": self.database.folder_for_path(candidate),
            "path": str(candidate),
            "filename": candidate.name,
            "note": note if note is not None else (previous["note"] if previous else ""),
            "created_at": created_at,
            "modified_at": str(stat.st_mtime),
            "size_bytes": stat.st_size,
            "mime_type": mimetypes.guess_type(candidate.name)[0] or "",
            "metadata_json": "{}",
            "content_fingerprint": fingerprint,
            "snippet": _text_snippet(candidate),
            "embedding_json": None,
            "embedding_model": None,
            "indexed_at": utc_now(),
        })
        self.database.clear_file_cache(str(candidate))
        return IndexResult("indexed", str(candidate), record)
