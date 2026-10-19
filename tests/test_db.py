from filememory.db import Database


def test_schema_folder_crud_and_natural_language_fts(tmp_path):
    database = Database(tmp_path / "memory.sqlite3")
    folder = database.add_folder(tmp_path)
    assert folder["path"] == str(tmp_path.resolve())
    assert database.list_folders()[0]["path"] == folder["path"]

    database.upsert_file({
        "folder_id": folder["id"], "path": str((tmp_path / "travel.txt").resolve()),
        "filename": "travel-plans.txt", "note": "summer trip itinerary",
        "created_at": "2026-01-01", "modified_at": "2026-01-02", "size_bytes": 10,
        "mime_type": "text/plain", "metadata_json": '{"kind":"note"}',
        "content_fingerprint": "fingerprint-1", "snippet": "book a train to Kyoto",
        "embedding_json": None, "embedding_model": None, "indexed_at": "2026-01-02",
    })
    results = database.keyword_search("Where is the Kyoto train itinerary?", 10)
    assert results[0]["filename"] == "travel-plans.txt"
    assert database.remove_folder(tmp_path)


def test_in_memory_database_is_supported():
    database = Database(":memory:")
    assert database.list_folders() == []
