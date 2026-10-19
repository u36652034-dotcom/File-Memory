"""Application service layer for local-first file memory."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .actions import open_file, open_folder
from .db import Database
from .embeddings import EmbeddingProvider, cosine, decode_embedding, searchable_text
from .indexer import FileIndexer, IndexResult
from .suggestions import OfflineSuggestionProvider


class FileMemoryService:
    def __init__(self, database: Database | None = None, embedding_provider: EmbeddingProvider | None = None) -> None:
        self.database = database or Database()
        self.indexer = FileIndexer(self.database)
        self.embedding_provider = embedding_provider or EmbeddingProvider()
        self.offline_suggestions = OfflineSuggestionProvider()

    def add_folder(self, path: str) -> dict[str, Any]:
        return self.database.add_folder(path)

    def list_folders(self) -> list[dict[str, Any]]:
        return self.database.list_folders()

    def remove_folder(self, path: str) -> bool:
        return self.database.remove_folder(path)

    def index_path(self, path: str, note: str | None = None) -> IndexResult:
        return self.indexer.index_path(path, note)

    def suggest_note(self, filename: str, snippet: str = "") -> str:
        return self.offline_suggestions.suggest(filename, snippet)

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
        self.database.cache_put(cache_key, query, mode, results)
        return results

    @staticmethod
    def open_file(path: str) -> str:
        return open_file(path)

    @staticmethod
    def open_folder(path: str) -> str:
        return open_folder(path)
