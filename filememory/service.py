"""Application service layer for local-first file memory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from .actions import open_file, open_folder
from .db import Database
from .embeddings import EmbeddingProvider, cosine, decode_embedding, searchable_text
from .indexer import FileIndexer, IndexResult
from .suggestions import GroqSuggestionProvider, OfflineSuggestionProvider, SmolLM2SuggestionProvider

AI_MODES = ("no_ai", "local_ai", "groq")


class ConfirmationRequired(ValueError):
    """Raised before a destructive operation unless the user confirmed it."""


class FileMemoryService:
    def __init__(
        self,
        database: Database | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        on_new_file: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.database = database or Database()
        self.indexer = FileIndexer(self.database)
        self.embedding_provider = embedding_provider or EmbeddingProvider()
        self.offline_suggestions = OfflineSuggestionProvider()
        self.local_suggestions = SmolLM2SuggestionProvider()
        self.groq_suggestions = GroqSuggestionProvider()
        self._watcher = None
        self.tracking_error: str | None = None
        # Watcher callbacks run on a watchdog timer thread. Consumers must
        # marshal UI work back to their own event loop.
        self.on_new_file = on_new_file

    def add_folder(self, path: str) -> dict[str, Any]:
        candidate = Path(path).expanduser().resolve(strict=False)
        if not candidate.is_dir():
            raise ValueError("watched folder must exist and be a directory")
        folder = self.database.add_folder(path)
        indexing = self._index_folder(folder["path"])
        folder["indexing"] = indexing
        # If event tracking is already running, include newly selected folders
        # without requiring the caller to restart the process.
        if self.tracking_active():
            self.start_tracking()
        return folder

    def list_folders(self) -> list[dict[str, Any]]:
        return self.database.list_folders()

    def remove_folder(self, path: str, confirmed: bool = False) -> bool:
        if not confirmed:
            raise ConfirmationRequired("Removing a watched folder requires confirmation")
        was_active = self.tracking_active()
        removed = self.database.remove_folder(path)
        if removed and was_active:
            self.start_tracking()
        return removed

    def get_settings(self) -> dict[str, Any]:
        return self.database.get_settings()

    def update_settings(self, **updates: Any) -> dict[str, Any]:
        current = self.get_settings()
        was_paused = bool(current.get("tracking_paused"))
        if "tracking_paused" in updates:
            if not isinstance(updates["tracking_paused"], bool):
                raise ValueError("tracking_paused must be a boolean")
            current["tracking_paused"] = updates["tracking_paused"]
        if "ai_mode" in updates:
            if updates["ai_mode"] not in AI_MODES:
                raise ValueError(f"ai_mode must be one of: {', '.join(AI_MODES)}")
            current["ai_mode"] = updates["ai_mode"]
        if "setup_complete" in updates:
            if not isinstance(updates["setup_complete"], bool):
                raise ValueError("setup_complete must be a boolean")
            current["setup_complete"] = updates["setup_complete"]
        if "ignored_extensions" in updates:
            values = updates["ignored_extensions"]
            if isinstance(values, str):
                values = values.replace(",", " ").split()
            if not isinstance(values, (list, tuple, set)):
                raise ValueError("ignored_extensions must be a list or string")
            normalized = set()
            for value in values:
                extension = str(value).strip().lower()
                if not extension:
                    continue
                if not extension.startswith("."):
                    extension = "." + extension
                normalized.add(extension)
            current["ignored_extensions"] = sorted(normalized)
        for key, value in current.items():
            self.database.set_setting(key, value)
        if current["tracking_paused"]:
            self.stop_tracking()
        elif was_paused and not self.tracking_active():
            self.start_tracking()
        return current

    def is_tracking_paused(self) -> bool:
        return bool(self.get_settings()["tracking_paused"])

    def index_path(self, path: str, note: str | None = None) -> IndexResult:
        return self._index_path(path, note, respect_pause=True)

    def _index_path(self, path: str, note: str | None, respect_pause: bool) -> IndexResult:
        if respect_pause and self.is_tracking_paused():
            return IndexResult("skipped-paused", str(Path(path).expanduser().resolve()))
        candidate = Path(path).expanduser()
        database_path = Path(self.database.path).expanduser()
        if database_path.name != ":memory:" and candidate.resolve() == database_path.resolve():
            return IndexResult("skipped-internal", str(candidate.resolve()))
        ignored = self.get_settings().get("ignored_extensions", [])
        if any(candidate.name.lower().endswith(extension) for extension in ignored):
            return IndexResult("skipped-ignored-type", str(candidate.resolve()))
        previous = self.database.get_file(candidate)
        result = self.indexer.index_path(path, note)
        if result.status != "indexed" or result.record is None:
            return result
        if note is not None:
            # An explicit note supersedes a suggestion that may still be open.
            self.database.clear_pending_suggestion(candidate)
        elif previous is None and not result.record.get("note"):
            suggested_note, provider = self._suggest_note_details(
                result.record["filename"], result.record.get("snippet", "")
            )
            if suggested_note.strip():
                self.database.add_pending_suggestion(
                    result.record["id"], candidate, suggested_note.strip(), provider
                )
        if previous is None and respect_pause and self.on_new_file is not None:
            self.on_new_file(self._without_embedding(result.record))
        return result

    def _index_folder(self, path: str) -> dict[str, Any]:
        """Index files present during explicit onboarding, without polling."""
        summary: dict[str, Any] = {"indexed": 0, "skipped": 0, "total": 0}
        root = Path(path)
        if not root.is_dir():
            summary["status"] = "folder-not-found"
            return summary
        for candidate in root.rglob("*"):
            if not candidate.is_file():
                continue
            database_path = Path(self.database.path)
            if database_path.name != ":memory:" and candidate.resolve() == database_path.resolve():
                continue
            summary["total"] += 1
            result = self._index_path(candidate, None, respect_pause=False)
            if result.status == "indexed":
                summary["indexed"] += 1
            else:
                summary["skipped"] += 1
        return summary

    def suggest_note(self, filename: str, snippet: str = "") -> str:
        return self._suggest_note_details(filename, snippet)[0]

    def _suggest_note_details(self, filename: str, snippet: str = "") -> tuple[str, str]:
        mode = self.get_settings().get("ai_mode", "no_ai")
        if mode == "local_ai":
            suggestion = self.local_suggestions.suggest(filename, snippet)
            if suggestion and suggestion.strip():
                return suggestion.strip(), "local_ai"
            return self.offline_suggestions.suggest(filename, snippet), "offline"
        if mode == "groq":
            suggestion = self.groq_suggestions.suggest(filename, snippet)
            if suggestion and suggestion.strip():
                return suggestion.strip(), "groq"
            return self.offline_suggestions.suggest(filename, snippet), "offline"
        return self.offline_suggestions.suggest(filename, snippet), "offline"

    def list_pending_suggestions(self) -> list[dict[str, Any]]:
        return self.database.list_pending_suggestions()

    def confirm_suggestion(self, suggestion_id: int, note: str | None = None) -> dict[str, Any]:
        suggestion = self.database.get_pending_suggestion(int(suggestion_id))
        if suggestion is None:
            raise ValueError("Pending suggestion not found")
        final_note = suggestion["suggested_note"] if note is None else str(note).strip()
        if not final_note:
            raise ValueError("note must not be empty")
        record = self.database.confirm_pending_suggestion(int(suggestion_id), final_note)
        if record is None:
            raise ValueError("Pending suggestion not found")
        return self._without_embedding(record)

    def list_files(self) -> list[dict[str, Any]]:
        """Return inbox-safe records without embedding payloads."""
        return [self._without_embedding(record) for record in self.database.list_files()]

    @staticmethod
    def _without_embedding(record: dict[str, Any]) -> dict[str, Any]:
        public_record = dict(record)
        public_record.pop("embedding_json", None)
        if public_record.get("path"):
            public_record["parent_path"] = str(Path(public_record["path"]).parent)
        return public_record

    def forget_file(self, path: str, confirmed: bool = False) -> bool:
        if not confirmed:
            raise ConfirmationRequired("Forgetting a file requires confirmation")
        return self.database.delete_file(path)

    def rebuild_search_index(self) -> dict[str, Any]:
        """Explicitly rescan selected folders and rebuild the FTS index.

        This is user-triggered work, not a polling loop. Existing records remain
        available if a file has been moved or deleted; the operation only adds
        files currently present in watched folders and rebuilds FTS.
        """
        indexed = 0
        skipped = 0
        for folder in self.list_folders():
            root = Path(folder["path"])
            if not root.is_dir():
                continue
            for candidate in root.rglob("*"):
                if candidate.is_file():
                    result = self._index_path(candidate, None, respect_pause=False)
                    if result.status == "indexed":
                        indexed += 1
                    else:
                        skipped += 1
        total = self.database.rebuild_search_index()
        return {"indexed": indexed, "skipped": skipped, "total": total}

    def start_tracking(self) -> None:
        if self.is_tracking_paused():
            return
        from .watcher import FolderWatcher

        self.stop_tracking()
        folders = [folder["path"] for folder in self.list_folders() if Path(folder["path"]).is_dir()]
        if not folders:
            return
        watcher = FolderWatcher(folders, self.index_path)
        try:
            watcher.start()
        except Exception as error:
            watcher.stop()
            self.tracking_error = str(error)
            raise
        self._watcher = watcher
        self.tracking_error = None

    def stop_tracking(self) -> None:
        if self._watcher is not None:
            self._watcher.stop()
            self._watcher = None

    def tracking_active(self) -> bool:
        return self._watcher is not None

    def _semantic_results(self, query: str, limit: int) -> list[dict[str, Any]] | None:
        query_embedding = self.embedding_provider.encode(query)
        if query_embedding is None:
            return None
        scored = []
        for record in self.database.list_files():
            embedding = decode_embedding(record.get("embedding_json"))
            if embedding is None:
                embedding = self.embedding_provider.encode(searchable_text(record))
                if embedding is not None:
                    # Cache the document embedding while preserving metadata.
                    record["embedding_json"] = json.dumps(embedding)
                    record["embedding_model"] = self.embedding_provider.model_name
                    values = dict(record)
                    self.database.upsert_file(values)
            if embedding is not None:
                result = dict(record)
                result["score"] = cosine(query_embedding, embedding)
                scored.append(result)
        scored.sort(key=lambda item: item["score"], reverse=True)
        return scored[:limit]

    def search(self, query: str, semantic: bool = True, limit: int = 20) -> list[dict[str, Any]]:
        query = query.strip()
        mode = "semantic" if semantic else "keyword"
        cache_key = hashlib.sha256(f"{mode}\0{query}\0{limit}".encode()).hexdigest()
        cached = self.database.cache_get(cache_key)
        if cached is not None:
            return cached
        results: list[dict[str, Any]]
        if semantic:
            results = self._semantic_results(query, limit) or self.database.keyword_search(query, limit)
        else:
            results = self.database.keyword_search(query, limit)
        results = [self._without_embedding(result) for result in results]
        self.database.cache_put(cache_key, query, mode, results)
        return results

    @staticmethod
    def open_file(path: str) -> str:
        return open_file(path)

    @staticmethod
    def open_folder(path: str) -> str:
        return open_folder(path)
