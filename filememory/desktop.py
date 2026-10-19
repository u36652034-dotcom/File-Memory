"""Windows desktop shell for the existing File Memory web application.

The desktop build starts the same loopback HTTP API used by the browser
version, then displays its existing ``web/`` files in pywebview's native
WebView2 window.  pywebview is imported lazily so the API and test suite stay
usable on machines without a graphical desktop or WebView2 runtime.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import threading
from pathlib import Path
from typing import Any

from .db import Database
from .paths import load_dotenv, resource_path
from .service import FileMemoryService
from .web import create_server


WEBVIEW_TITLE = "File Memory"
TOAST_DURATION_MS = 8000


def create_local_server(
    service: FileMemoryService,
    host: str = "127.0.0.1",
    port: int = 0,
) -> tuple[Any, str]:
    """Create the in-process API server and return it with its browser URL.

    Port ``0`` is intentional for desktop startup: Windows chooses an unused
    loopback port, avoiding collisions with a separately running web server.
    The returned server is not started until :meth:`DesktopApp.start_server`.
    """

    server = create_server(service, host=host, port=port)
    bound_host, bound_port = server.server_address[:2]
    return server, f"http://{bound_host}:{bound_port}/"


def window_options(start_minimized: bool = False) -> dict[str, Any]:
    """Return the native window settings used by the packaged entrypoint."""

    return {
        "title": WEBVIEW_TITLE,
        "width": 1200,
        "height": 820,
        "min_size": (900, 620),
        "resizable": True,
        "minimized": start_minimized,
    }


def apply_windows_icon(title: str = WEBVIEW_TITLE) -> bool:
    """Apply the bundled ICO to the native WebView2 title bar/taskbar window."""
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, title)
        if not hwnd:
            return False
        icon_path = resource_path("assets/filememory.ico")
        if not icon_path.is_file():
            return False
        image_icon = user32.LoadImageW(
            None,
            str(icon_path),
            1,  # IMAGE_ICON
            0,
            0,
            0x00000010 | 0x00000040,  # LR_LOADFROMFILE | LR_DEFAULTSIZE
        )
        if not image_icon:
            return False
        user32.SendMessageW(hwnd, 0x0080, 1, image_icon)  # WM_SETICON / ICON_BIG
        user32.SendMessageW(hwnd, 0x0080, 0, image_icon)  # WM_SETICON / ICON_SMALL
        return True
    except (AttributeError, OSError):
        return False


def notification_script(filename: str, note: str = "", suggestion_id: int | None = None, path: str = "") -> str:
    """Build a non-blocking script for the existing web UI toast element."""

    payload = json.dumps({
        "filename": filename,
        "note": note,
        "suggestion_id": suggestion_id,
        "path": path,
    })
    return f"""
(function () {{
  if (window.showNativeFilePrompt) {{
    window.showNativeFilePrompt({payload});
    return;
  }}
  const toast = document.getElementById("toast");
  if (!toast) return;
  if (window.__fileMemoryNativeToastTimer) {{
    clearTimeout(window.__fileMemoryNativeToastTimer);
  }}
   toast.textContent = {json.dumps(f"New file remembered: {filename}" if filename else "New file remembered")};
  toast.classList.remove("error");
  toast.hidden = false;
  window.__fileMemoryNativeToastTimer = setTimeout(function () {{
    toast.hidden = true;
  }}, {TOAST_DURATION_MS});
}})();
"""


class DesktopApp:
    """Own the loopback service and a native pywebview window."""

    def __init__(
        self,
        service: FileMemoryService | None = None,
        host: str = "127.0.0.1",
        port: int = 0,
    ) -> None:
        self.service = service or FileMemoryService()
        self.server, self.url = create_local_server(self.service, host, port)
        self.window: Any | None = None
        self._server_thread: threading.Thread | None = None
        self._closed = False
        self._page_loaded = False
        self._notifications: queue.Queue[dict[str, Any]] = queue.Queue()
        self._notification_lock = threading.Lock()

        # FileMemoryService invokes this from the watchdog worker thread.  The
        # handler never blocks the watcher and only marshals a small toast to
        # the already loaded web page.
        self.service.on_new_file = self._on_new_file

    @property
    def server_url(self) -> str:
        """Compatibility-friendly name for callers that need the local URL."""

        return self.url

    def start_server(self) -> None:
        """Start the API in a daemon thread owned by this desktop process."""

        if self._server_thread is not None:
            return
        self._server_thread = threading.Thread(
            target=self.server.serve_forever,
            name="filememory-api",
            daemon=True,
        )
        self._server_thread.start()

    def _start_tracking(self) -> None:
        try:
            self.service.start_tracking()
        except Exception as error:
            # The web UI remains usable for keyword search and manual folder
            # management when optional watchdog support is unavailable.
            print(f"Warning: filesystem tracking is unavailable: {error}")

    def _on_new_file(self, record: dict[str, Any]) -> None:
        """Queue a watcher event and return immediately to the backend."""

        self._notifications.put(record)
        if self._page_loaded:
            self._schedule_notifications()

    def _on_page_loaded(self, *_args: Any) -> None:
        self._page_loaded = True
        self._schedule_notifications()

    def _schedule_notifications(self) -> None:
        threading.Thread(
            target=self._flush_notifications,
            name="filememory-toast",
            daemon=True,
        ).start()

    def _flush_notifications(self) -> None:
        if self.window is None:
            return
        with self._notification_lock:
            while True:
                try:
                    record = self._notifications.get_nowait()
                except queue.Empty:
                    return
                try:
                    filename = Path(str(record.get("filename", ""))).name
                    pending = next(
                        (item for item in self.service.list_pending_suggestions() if item.get("path") == record.get("path")),
                        None,
                    )
                    self.window.evaluate_js(notification_script(
                        filename,
                        str(pending.get("suggested_note", "")) if pending else "",
                        int(pending["id"]) if pending else None,
                        str(record.get("path", "")),
                    ))
                except Exception:
                    # A page can close between queueing and evaluating.  Keep
                    # the watcher alive; the dashboard remains available on
                    # relaunch.
                    return

    def _close(self, *_args: Any) -> None:
        if self._closed:
            return
        self._closed = True
        self.service.stop_tracking()
        self.server.shutdown()
        self.server.server_close()

    def run(self, start_minimized: bool = False) -> None:
        """Start the local API and block in the pywebview GUI event loop."""

        try:
            import webview
        except ImportError as error:
            raise RuntimeError(
                "The Windows desktop shell requires pywebview. Install "
                "requirements-packaging.lock in the project environment."
            ) from error

        self.start_server()
        self._start_tracking()
        try:
            self.window = webview.create_window(
                url=self.url,
                **window_options(start_minimized),
            )
            self.window.events.loaded += self._on_page_loaded
            self.window.events.closed += self._close
            # pywebview does not expose an icon argument. Apply the ICO after
            # the native window exists; the delayed retry handles WebView2's
            # asynchronous HWND creation.
            threading.Timer(0.8, apply_windows_icon).start()
            # edgechromium is pywebview's Microsoft Edge WebView2 backend on
            # Windows.  The runtime is intentionally supplied by Windows and
            # is not bundled into the PyInstaller artifact.
            webview.start(gui="edgechromium", debug=False)
        finally:
            self._close()


def build_app_from_environment() -> DesktopApp:
    """Build a desktop app using the same environment settings as ``web``."""

    load_dotenv()
    database = os.getenv("FILE_MEMORY_DATABASE")
    configured_host = os.getenv("FILE_MEMORY_HOST", "127.0.0.1")
    host = configured_host if configured_host in {"127.0.0.1", "localhost", "::1"} else "127.0.0.1"
    return DesktopApp(
        service=FileMemoryService(database=Database(database)),
        host=host,
        port=int(os.getenv("FILE_MEMORY_PORT", "0")),
    )


def main(argv: list[str] | None = None) -> None:
    """Launch File Memory in the native Windows WebView2 shell."""

    parser = argparse.ArgumentParser(description="Run File Memory in WebView2")
    parser.add_argument(
        "--minimized",
        action="store_true",
        help="start the native window minimized",
    )
    args = parser.parse_args(argv)
    build_app_from_environment().run(start_minimized=args.minimized)


if __name__ == "__main__":
    main()
