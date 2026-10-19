import pytest

from filememory.db import Database
from filememory.service import ConfirmationRequired, FileMemoryService


def test_no_ai_is_the_persisted_default_and_settings_are_normalized(tmp_path):
    service = FileMemoryService(Database(tmp_path / "memory.sqlite3"))
    assert service.get_settings() == {
        "tracking_paused": False,
        "ai_mode": "no_ai",
        "ignored_extensions": [],
    }
    settings = service.update_settings(ai_mode="groq", ignored_extensions="LOG, .tmp")
    assert settings["ai_mode"] == "groq"
    assert settings["ignored_extensions"] == [".log", ".tmp"]


def test_pause_and_ignored_types_apply_before_indexing(tmp_path):
    service = FileMemoryService(Database(tmp_path / "memory.sqlite3"))
    service.indexer.stability_wait = 0
    ignored = tmp_path / "debug.log"
    ignored.write_text("ignore me", encoding="utf-8")
    service.update_settings(ignored_extensions=[".log"])
    assert service.index_path(ignored).status == "skipped-ignored-type"

    path = tmp_path / "keep.txt"
    path.write_text("keep me", encoding="utf-8")
    service.update_settings(tracking_paused=True)
    assert service.index_path(path).status == "skipped-paused"
    service.update_settings(tracking_paused=False)
    assert service.index_path(path).status == "indexed"


def test_rebuild_is_explicit_and_can_reindex_while_tracking_is_paused(tmp_path):
    service = FileMemoryService(Database(tmp_path / "memory.sqlite3"))
    service.indexer.stability_wait = 0
    service.add_folder(str(tmp_path))
    path = tmp_path / "inbox.txt"
    path.write_text("rebuild me", encoding="utf-8")
    service.update_settings(tracking_paused=True)
    result = service.rebuild_search_index()
    assert result["total"] == 1
    assert service.search("rebuild", semantic=True)[0]["filename"] == "inbox.txt"


def test_destructive_actions_require_confirmation_and_do_not_delete_real_files(tmp_path):
    service = FileMemoryService(Database(tmp_path / "memory.sqlite3"))
    service.indexer.stability_wait = 0
    service.add_folder(str(tmp_path))
    path = tmp_path / "remember.txt"
    path.write_text("still on disk", encoding="utf-8")
    service.index_path(path)

    with pytest.raises(ConfirmationRequired):
        service.forget_file(str(path))
    assert service.forget_file(str(path), confirmed=True)
    assert path.exists()
    assert service.database.get_file(path) is None

    with pytest.raises(ConfirmationRequired):
        service.remove_folder(str(tmp_path))
    assert service.remove_folder(str(tmp_path), confirmed=True)
