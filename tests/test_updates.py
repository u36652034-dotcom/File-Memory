import json
from datetime import date

import pytest

from filememory.db import Database
from filememory.desktop import DesktopApp, notification_popup_html
from filememory.service import FileMemoryService
from filememory.updates import (
    DEFAULT_UPDATE_MANIFEST_URL,
    UpdateManifest,
    check_for_update,
    fetch_manifest,
    is_newer_version,
    parse_manifest,
)


def test_manifest_parsing_normalizes_release_details_and_requires_https():
    manifest = parse_manifest(
        {
            "version": "1.2.0",
            "release_url": "https://updates.example.test/file-memory-1.2.0.exe",
            "features": ["Faster search"],
            "fixes": "Tray startup is more reliable",
            "release_notes": ["Model loading is quieter.", "Windows fixes."],
        }
    )

    assert manifest == UpdateManifest(
        version="1.2.0",
        release_url="https://updates.example.test/file-memory-1.2.0.exe",
        features=("Faster search",),
        fixes=("Tray startup is more reliable",),
        release_notes="Model loading is quieter.\nWindows fixes.",
    )
    with pytest.raises(ValueError):
        parse_manifest({"version": "1.2.0", "release_url": "http://example.test/update"})


def test_manifest_parsing_accepts_structured_release_notes():
    manifest = parse_manifest(
        {
            "version": "1.2.0",
            "release_url": "https://example.test/update",
            "release_notes": {"summary": "Safer startup", "fixes": ["Tray fix"]},
        }
    )
    assert manifest.release_notes == "Summary:\n- Safer startup\n\nFixes:\n- Tray fix"


def test_semantic_comparison_handles_patch_prerelease_and_build_metadata():
    assert is_newer_version("1.0.1", "1.0.0")
    assert is_newer_version("1.0.0", "1.0.0-rc.2")
    assert not is_newer_version("1.0.0-rc.2", "1.0.0-rc.10")
    assert not is_newer_version("1.0.0+build.2", "1.0.0+build.1")


def test_manifest_fetch_is_https_bounded_and_silent_on_invalid_json():
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit):
            return json.dumps(
                {"version": "1.1.0", "release_url": "https://example.test/download"}
            ).encode()

    calls = []

    def opener(request, timeout):
        calls.append((request.full_url, timeout))
        return Response()

    manifest = fetch_manifest(DEFAULT_UPDATE_MANIFEST_URL, timeout=1.25, opener=opener)
    assert manifest is not None
    assert calls == [(DEFAULT_UPDATE_MANIFEST_URL, 1.25)]
    assert fetch_manifest("http://example.test/latest.json", opener=opener) is None

    class BrokenResponse(Response):
        def read(self, _limit):
            return b"not json"

    assert fetch_manifest(
        DEFAULT_UPDATE_MANIFEST_URL,
        opener=lambda *_args, **_kwargs: BrokenResponse(),
    ) is None


def test_update_check_runs_once_per_day_even_when_manifest_is_available(tmp_path):
    calls = []
    manifest = UpdateManifest("1.1.0", "https://example.test/download")

    def fetcher(url):
        calls.append(url)
        return manifest

    checked = date(2026, 10, 20)
    state = tmp_path / "update-check.json"
    assert check_for_update(
        manifest_url="https://example.test/latest.json",
        state_path=state,
        now=checked,
        fetcher=fetcher,
    ) == manifest
    assert check_for_update(
        manifest_url="https://example.test/latest.json",
        state_path=state,
        now=checked,
        fetcher=fetcher,
    ) is None
    assert calls == ["https://example.test/latest.json"]
    assert check_for_update(
        manifest_url="https://example.test/latest.json",
        state_path=state,
        now=date(2026, 10, 21),
        fetcher=fetcher,
    ) == manifest


class FakeNotificationWindow:
    def __init__(self):
        self.scripts = []
        self.hidden_count = 0

    def move(self, *_args):
        pass

    def evaluate_js(self, script):
        self.scripts.append(script)

    def show(self):
        pass

    def hide(self):
        self.hidden_count += 1


def test_update_popup_shows_release_details_and_is_cancelable(tmp_path, monkeypatch):
    app = DesktopApp(service=FileMemoryService(Database(tmp_path / "memory.sqlite3")))
    popup = FakeNotificationWindow()
    app._notification_window = popup
    manifest = UpdateManifest(
        "1.1.0",
        "https://example.test/download",
        fixes=("A fix",),
        features=("A feature",),
        release_notes="Read this",
    )
    app._show_update_notification(manifest)
    assert "setUpdateNotification" in popup.scripts[0]
    assert "1.1.0" in popup.scripts[0]
    assert "A fix" in popup.scripts[0]
    assert "A feature" in popup.scripts[0]
    assert "Read this" in popup.scripts[0]

    app._dismiss_update_notification()
    assert app._update_notification is None
    assert popup.hidden_count == 1
    app.server.server_close()


def test_download_update_uses_safe_browser_action_and_dismisses(tmp_path, monkeypatch):
    app = DesktopApp(service=FileMemoryService(Database(tmp_path / "memory.sqlite3")))
    popup = FakeNotificationWindow()
    app._notification_window = popup
    app._update_notification = UpdateManifest("1.1.0", "https://example.test/download")
    opened = []
    monkeypatch.setattr("filememory.desktop.open_url", opened.append)

    app._download_update()

    assert opened == ["https://example.test/download"]
    assert app._update_notification is None
    assert popup.hidden_count == 1
    app.server.server_close()


def test_notification_popup_preserves_file_actions_and_update_actions():
    html = notification_popup_html()
    assert "window.pywebview.api.remember" in html
    assert "window.pywebview.api.dismiss" in html
    assert "window.setUpdateNotification" in html
    assert "window.pywebview.api.later" in html
    assert "window.pywebview.api.download_update" in html
