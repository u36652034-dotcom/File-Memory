import sys

import pytest

from filememory.actions import ActionError, open_file
from filememory.suggestions import OfflineSuggestionProvider
from filememory.watcher import WatchdogUnavailableError, _watchdog_types


def test_offline_note_suggestion_is_deterministic():
    assert OfflineSuggestionProvider().suggest("quarterly_report.pdf", "Revenue grew") == "quarterly report: Revenue grew"


def test_open_file_rejects_missing_paths(tmp_path):
    with pytest.raises(ActionError):
        open_file(tmp_path / "missing.txt")


def test_watcher_has_clear_missing_dependency_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "watchdog", None)
    monkeypatch.setitem(sys.modules, "watchdog.events", None)
    monkeypatch.setitem(sys.modules, "watchdog.observers", None)
    with pytest.raises(WatchdogUnavailableError, match="requires watchdog"):
        _watchdog_types()
