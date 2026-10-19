from filememory.db import Database
from filememory.indexer import FileIndexer


def test_indexer_skips_downloads_and_duplicate_content(tmp_path):
    database = Database(tmp_path / "memory.sqlite3")
    indexer = FileIndexer(database, stability_wait=0)
    partial = tmp_path / "report.pdf.part"
    partial.write_text("still downloading", encoding="utf-8")
    assert indexer.index_path(partial).status == "skipped-incomplete"

    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("same content", encoding="utf-8")
    second.write_text("same content", encoding="utf-8")
    assert indexer.index_path(first).status == "indexed"
    duplicate = indexer.index_path(second)
    assert duplicate.status == "skipped-duplicate"
    assert len(database.list_files()) == 1


def test_indexer_preserves_note_on_reindex(tmp_path):
    database = Database(tmp_path / "memory.sqlite3")
    indexer = FileIndexer(database, stability_wait=0)
    path = tmp_path / "notes.txt"
    path.write_text("first", encoding="utf-8")
    assert indexer.index_path(path, "important note").status == "indexed"
    path.write_text("changed", encoding="utf-8")
    result = indexer.index_path(path)
    assert result.record["note"] == "important note"
