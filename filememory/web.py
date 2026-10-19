"""Local-only HTTP adapter for the inbox and settings screen.

It intentionally binds to loopback by default and uses only the Python
standard library so the same surface can later be hosted by a desktop shell.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .db import Database
from .paths import load_dotenv
from .service import ConfirmationRequired, FileMemoryService

WEB_ROOT = Path(__file__).resolve().parent.parent / "web"


def _body(request: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(request.headers.get("Content-Length", "0"))
    raw = request.rfile.read(length) if length else b"{}"
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON body must be an object")
    return value


def create_server(service: FileMemoryService, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        server_version = "FileMemory/1"

        def _send(self, status: int, value: Any, content_type: str = "application/json") -> None:
            payload = value if isinstance(value, bytes) else json.dumps(value).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def _error(self, status: int, message: str) -> None:
            self._send(status, {"error": message})

        def log_message(self, format: str, *args: Any) -> None:
            # Keep the desktop console quiet; callers can add their own logger.
            return

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            try:
                if parsed.path in ("/", "/index.html", "/styles.css", "/app.js"):
                    filename = "index.html" if parsed.path in ("/", "/index.html") else parsed.path.lstrip("/")
                    content_type = "text/html; charset=utf-8" if filename.endswith(".html") else "text/javascript; charset=utf-8" if filename.endswith(".js") else "text/css; charset=utf-8"
                    self._send(200, (WEB_ROOT / filename).read_bytes(), content_type)
                elif parsed.path == "/api/state":
                    self._send(200, {
                        "settings": service.get_settings(),
                        "folders": service.list_folders(),
                        "files": service.list_files(),
                        "suggestions": service.list_pending_suggestions(),
                        "tracking_active": service.tracking_active(),
                        "tracking_error": service.tracking_error,
                    })
                elif parsed.path == "/api/folders":
                    self._send(200, {"folders": service.list_folders()})
                elif parsed.path == "/api/settings":
                    self._send(200, service.get_settings())
                elif parsed.path == "/api/suggestions":
                    self._send(200, {"suggestions": service.list_pending_suggestions()})
                elif parsed.path == "/api/search":
                    query = parse_qs(parsed.query).get("q", [""])[0]
                    semantic = parse_qs(parsed.query).get("semantic", ["true"])[0].lower() not in ("false", "0", "no")
                    self._send(200, {"results": service.search(query, semantic=semantic) if query else service.list_files()})
                else:
                    self._error(404, "not found")
            except Exception as error:
                self._error(500, str(error))

        def do_POST(self) -> None:  # noqa: N802
            try:
                payload = _body(self)
                if self.path == "/api/folders":
                    result = service.add_folder(str(payload["path"]))
                elif self.path == "/api/folders/remove":
                    result = {"removed": service.remove_folder(str(payload["path"]), bool(payload.get("confirmed")))}
                elif self.path == "/api/settings":
                    result = service.update_settings(**payload)
                elif self.path == "/api/suggestions/confirm":
                    suggestion_id = payload.get("id", payload.get("suggestion_id"))
                    if suggestion_id is None:
                        raise ValueError("suggestion id is required")
                    result = {"file": service.confirm_suggestion(suggestion_id, payload.get("note"))}
                elif self.path.startswith("/api/suggestions/") and self.path.endswith("/confirm"):
                    suggestion_id = self.path[len("/api/suggestions/") : -len("/confirm")].strip("/")
                    if not suggestion_id.isdigit():
                        raise ValueError("suggestion id must be an integer")
                    result = {"file": service.confirm_suggestion(suggestion_id, payload.get("note"))}
                elif self.path == "/api/rebuild":
                    result = service.rebuild_search_index()
                elif self.path == "/api/files/forget":
                    result = {"forgotten": service.forget_file(str(payload["path"]), bool(payload.get("confirmed")))}
                elif self.path == "/api/tracking/start":
                    service.start_tracking()
                    result = {"tracking_active": service.tracking_active()}
                elif self.path == "/api/tracking/stop":
                    service.stop_tracking()
                    result = {"tracking_active": service.tracking_active()}
                elif self.path in ("/api/open-file", "/api/actions/open-file"):
                    result = {"path": service.open_file(str(payload["path"]))}
                elif self.path in ("/api/open-folder", "/api/actions/open-folder"):
                    result = {"path": service.open_folder(str(payload["path"]))}
                else:
                    self._error(404, "not found")
                    return
                self._send(200, result)
            except ConfirmationRequired as error:
                self._error(409, str(error))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                self._error(400, str(error))
            except Exception as error:
                self._error(500, str(error))

        def do_DELETE(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            try:
                if parsed.path != "/api/folders":
                    self._error(404, "not found")
                    return
                params = parse_qs(parsed.query)
                path = params.get("path", [""])[0]
                confirmed = params.get("confirmed", ["false"])[0].lower() in ("true", "1", "yes")
                self._send(200, {"removed": service.remove_folder(path, confirmed=confirmed)})
            except ConfirmationRequired as error:
                self._error(409, str(error))
            except Exception as error:
                self._error(400, str(error))

    return ThreadingHTTPServer((host, port), Handler)


def serve(database: str | None = None, host: str | None = None, port: int | None = None) -> None:
    load_dotenv()
    database = database or os.getenv("FILE_MEMORY_DATABASE")
    host = host or os.getenv("FILE_MEMORY_HOST", "127.0.0.1")
    port = port or int(os.getenv("FILE_MEMORY_PORT", "8765"))
    service = FileMemoryService(database=Database(database))
    server = create_server(service, host, port)
    # The desktop entry point owns the event watcher lifecycle. Direct service
    # users can opt into the same behavior with start_tracking().
    try:
        service.start_tracking()
    except Exception as error:
        # The UI remains usable for keyword search and manual indexing when a
        # project-local optional dependency has not been installed yet.
        print(f"Warning: filesystem tracking is unavailable: {error}")
    print(f"File Memory running locally at http://{host}:{port}")
    try:
        server.serve_forever()
    finally:
        service.stop_tracking()
        server.server_close()


if __name__ == "__main__":
    serve()
