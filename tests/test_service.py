import json

from filememory.db import Database
from filememory.embeddings import EmbeddingProvider
from filememory.service import FileMemoryService


class FakeModel:
    def encode(self, text, normalize_embeddings=True):
        text = text.lower()
        return [1.0 if "recipe" in text else 0.0, 1.0 if "meeting" in text else 0.0]


def test_service_keyword_search_and_semantic_fallback_are_offline(tmp_path):
    provider = EmbeddingProvider(loader=lambda _: None)
    service = FileMemoryService(Database(tmp_path / "memory.sqlite3"), provider)
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


def test_new_index_creates_pending_offline_suggestion_and_confirmation_persists(tmp_path):
    service = FileMemoryService(Database(tmp_path / "memory.sqlite3"))
    service.indexer.stability_wait = 0
    path = tmp_path / "quarterly_report.txt"
    path.write_text("Revenue grew in Q3", encoding="utf-8")

    result = service.index_path(path)

    assert result.status == "indexed"
    pending = service.list_pending_suggestions()
    assert len(pending) == 1
    assert pending[0]["suggested_note"] == "quarterly report: Revenue grew in Q3"
    assert pending[0]["provider"] == "offline"

    saved = service.confirm_suggestion(pending[0]["id"], "Reviewed Q3 revenue report")

    assert saved["note"] == "Reviewed Q3 revenue report"
    assert service.list_pending_suggestions() == []
    assert service.database.get_file(path)["note"] == "Reviewed Q3 revenue report"


def test_add_folder_indexes_existing_files_and_returns_summary(tmp_path):
    service = FileMemoryService(Database(tmp_path / "memory.sqlite3"))
    service.indexer.stability_wait = 0
    (tmp_path / "one.txt").write_text("first", encoding="utf-8")
    (tmp_path / "two.txt").write_text("second", encoding="utf-8")

    folder = service.add_folder(str(tmp_path))

    assert folder["path"] == str(tmp_path.resolve())
    assert folder["indexing"] == {"indexed": 2, "skipped": 0, "total": 2}
    assert service.tracking_active() is False
    assert {record["filename"] for record in service.list_files()} == {"one.txt", "two.txt"}
    assert len(service.list_pending_suggestions()) == 2


def test_add_folder_rejects_missing_directory(tmp_path):
    service = FileMemoryService(Database(tmp_path / "memory.sqlite3"))
    try:
        service.add_folder(tmp_path / "does-not-exist")
    except ValueError as error:
        assert "must exist" in str(error)
    else:
        raise AssertionError("missing watched folder should be rejected")


def test_pause_then_resume_tracking_restarts_event_watcher(tmp_path):
    service = FileMemoryService(Database(tmp_path / "memory.sqlite3"))
    service.add_folder(str(tmp_path))
    service.start_tracking()
    assert service.tracking_active()
    service.update_settings(tracking_paused=True)
    assert not service.tracking_active()
    service.update_settings(tracking_paused=False)
    assert service.tracking_active()
    service.stop_tracking()
