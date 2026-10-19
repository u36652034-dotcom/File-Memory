import json
import threading
from urllib.request import Request, urlopen

from pathlib import Path

from filememory.db import Database
from filememory.service import FileMemoryService
from filememory.web import WEB_ROOT
from filememory.web import create_server


def test_local_ui_contains_inbox_settings_and_confirmation_controls():
    page = (Path(WEB_ROOT) / "index.html").read_text(encoding="utf-8")
    script = (Path(WEB_ROOT) / "app.js").read_text(encoding="utf-8")
    assert "Inbox" in page
    assert "Settings" in page
    assert "No AI (default)" in page
    assert "confirm(" in script


def test_loopback_api_exposes_and_confirms_pending_suggestions(tmp_path):
    service = FileMemoryService(Database(tmp_path / "memory.sqlite3"))
    service.indexer.stability_wait = 0
    path = tmp_path / "plan.txt"
    path.write_text("Ship the first release", encoding="utf-8")
    service.index_path(path)
    server = create_server(service, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(base + "/api/suggestions") as response:
            suggestions = json.loads(response.read())
        assert suggestions["suggestions"][0]["filename"] == "plan.txt"
        suggestion_id = suggestions["suggestions"][0]["id"]

        request = Request(
            base + "/api/suggestions/confirm",
            data=json.dumps({"id": suggestion_id, "note": "Release plan"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request) as response:
            saved = json.loads(response.read())
        assert saved["file"]["note"] == "Release plan"
        assert service.list_pending_suggestions() == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
