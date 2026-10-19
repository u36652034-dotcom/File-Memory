import json

from filememory.db import Database
from filememory.embeddings import EmbeddingProvider
from filememory.service import FileMemoryService


class FakeModel:
    def encode(self, text, normalize_embeddings=True):
        text = text.lower()
        return [1.0 if "recipe" in text else 0.0, 1.0 if "meeting" in text else 0.0]


def test_service_keyword_search_and_semantic_fallback_are_offline(tmp_path):
    service = FileMemoryService(Database(tmp_path / "memory.sqlite3"))
    path = tmp_path / "recipe.txt"
    path.write_text("pasta recipe with tomatoes", encoding="utf-8")
    service.index_path(path, "dinner ideas")
    assert service.search("tomatoes", semantic=False)[0]["filename"] == "recipe.txt"
    # No sentence-transformers installed/model loaded: semantic mode falls back to FTS.
    assert service.search("pasta recipe", semantic=True)[0]["filename"] == "recipe.txt"


def test_semantic_embeddings_and_search_results_are_cached(tmp_path):
    provider = EmbeddingProvider(loader=lambda _: FakeModel())
    service = FileMemoryService(Database(tmp_path / "memory.sqlite3"), provider)
    path = tmp_path / "meeting.txt"
    path.write_text("weekly meeting", encoding="utf-8")
    service.index_path(path)
    results = service.search("meeting", semantic=True)
    assert results[0]["filename"] == "meeting.txt"
    stored = service.database.get_file(path)
    assert json.loads(stored["embedding_json"]) == [0.0, 1.0]
    assert service.search("meeting", semantic=True) == results
