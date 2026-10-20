import json
from urllib.request import urlopen

from filememory.db import Database
from filememory.desktop import (
    APP_USER_MODEL_ID,
    DesktopApp,
    is_setup_complete,
    notification_script,
    notification_popup_html,
    set_windows_app_user_model_id,
    should_start_hidden,
    tray_menu_labels,
    window_options,
)
from filememory.embeddings import EmbeddingProvider
from filememory.service import FileMemoryService


def test_desktop_server_serves_the_existing_web_ui_without_a_display(tmp_path):
    service = FileMemoryService(Database(tmp_path / "memory.sqlite3"))
    app = DesktopApp(service=service)
    app.start_server()
    try:
        with urlopen(app.server_url, timeout=2) as response:
            html = response.read().decode("utf-8")
        assert response.status == 200
        assert '<script src="app.js" defer></script>' in html
        assert '<link rel="stylesheet" href="styles.css" />' in html
    finally:
        app.server.shutdown()
        app.server.server_close()


def test_desktop_server_uses_the_current_service_api(tmp_path):
    service = FileMemoryService(Database(tmp_path / "memory.sqlite3"))
    app = DesktopApp(service=service)
    app.start_server()
    try:
        with urlopen(app.server_url + "api/settings", timeout=2) as response:
            payload = json.loads(response.read())
        assert response.status == 200
        assert payload["ai_mode"] == "no_ai"
        assert payload["tracking_paused"] is False
    finally:
        app.server.shutdown()
        app.server.server_close()


def test_desktop_window_configuration_preserves_minimized_startup():
    options = window_options(start_minimized=True)
    assert options["minimized"] is True
    assert options["title"] == "File Memory"
    assert options["min_size"] == (900, 620)


def test_completed_startup_can_create_the_window_hidden_from_the_taskbar():
    assert window_options(hidden=True)["hidden"] is True


def test_startup_identity_and_tray_minimized_decision_are_display_free(tmp_path):
    service = FileMemoryService(Database(tmp_path / "memory.sqlite3"))
    assert APP_USER_MODEL_ID == "FileMemory.Desktop"
    assert isinstance(set_windows_app_user_model_id(), bool)
    assert is_setup_complete(service) is False
    assert should_start_hidden(True, False) is False
    assert should_start_hidden(False, True) is False
    assert should_start_hidden(True, True) is True

    watched = tmp_path / "watched"
    watched.mkdir()
    service.database.add_folder(watched)
    assert is_setup_complete(service) is True


def test_tray_menu_exposes_dashboard_tracking_and_exit_actions():
    assert tray_menu_labels(False) == (
        "Show dashboard",
        "Hide dashboard",
        "Pause tracking",
        "Exit",
    )
    assert tray_menu_labels(True)[2] == "Resume tracking"


def test_native_notification_uses_existing_non_blocking_toast_for_eight_seconds():
    script = notification_script("new report.txt")
    assert "New file remembered: new report.txt" in script
    assert "__fileMemoryNativeToastTimer" in script
    assert "8000" in script


def test_background_notification_is_editable_and_has_remember_dismiss_actions():
    html = notification_popup_html()
    assert "window.pywebview.api.remember" in html
    assert "window.pywebview.api.dismiss" in html
    assert "NEW FILE" in html


def test_new_file_callback_is_for_watcher_style_indexing_only(tmp_path):
    events = []
    service = FileMemoryService(Database(tmp_path / "memory.sqlite3"), on_new_file=events.append)
    service.indexer.stability_wait = 0
    watched = tmp_path / "watched"
    watched.mkdir()
    (watched / "existing.txt").write_text("existing", encoding="utf-8")

    service.add_folder(str(watched))
    assert events == []

    new_file = watched / "new.txt"
    new_file.write_text("new content", encoding="utf-8")
    service.index_path(new_file)
    assert events[0]["filename"] == "new.txt"
    assert events[0]["path"] == str(new_file.resolve())


def test_embedding_readiness_surfaces_missing_optional_model():
    ready, message = EmbeddingProvider(loader=lambda _name: None).readiness()
    assert ready is False
    assert "all-MiniLM-L6-v2" in message
