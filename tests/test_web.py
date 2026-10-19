from pathlib import Path

from filememory.web import WEB_ROOT


def test_local_ui_contains_inbox_settings_and_confirmation_controls():
    page = (Path(WEB_ROOT) / "index.html").read_text(encoding="utf-8")
    script = (Path(WEB_ROOT) / "app.js").read_text(encoding="utf-8")
    assert "Inbox" in page
    assert "Settings" in page
    assert "No AI (default)" in page
    assert "confirm(" in script
