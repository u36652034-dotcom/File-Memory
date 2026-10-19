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
APP_USER_MODEL_ID = "FileMemory.Desktop"
TRAY_ICON_NAME = "filememory"


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


def should_start_hidden(start_minimized: bool, setup_complete: bool) -> bool:
    """Return whether startup may hide the dashboard in the notification area.

    A startup shortcut can request ``--minimized``, but a new installation must
    remain visible so the user can select a watched folder and finish setup.
    """

    return bool(start_minimized and setup_complete)


def is_setup_complete(service: FileMemoryService) -> bool:
    """Read the persisted setup marker, with a legacy-folder fallback.

    Older databases predate the optional ``setup_complete`` setting.  A
    selected folder is enough to recognize those installs as configured while
    still allowing an explicit ``False`` marker to force the dashboard open.
    """

    settings = service.get_settings()
    if "setup_complete" in settings:
        return bool(settings["setup_complete"])
    return bool(service.list_folders())


def tray_menu_labels(tracking_paused: bool) -> tuple[str, str, str, str]:
    """Return the user-visible tray actions without importing a GUI backend."""

    return (
        "Show dashboard",
        "Hide dashboard",
        "Resume tracking" if tracking_paused else "Pause tracking",
        "Exit",
    )


def set_windows_app_user_model_id(app_id: str = APP_USER_MODEL_ID) -> bool:
    """Set the process identity used by Windows taskbar grouping and shortcuts."""

    try:
        import ctypes

        result = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            ctypes.c_wchar_p(app_id)
        )
        # HRESULT S_OK is zero.  Keep this helper harmless on unsupported hosts.
        return int(result) == 0
    except (AttributeError, OSError):
        return False


def apply_windows_icon(title: str = WEBVIEW_TITLE, hwnd: int | None = None) -> bool:
    """Apply the bundled ICO to the WebView2 window and its class icons.

    ``WM_SETICON`` covers the visible window.  Setting both class icon slots is
    important for WebView2/taskbar surfaces that derive their image from the
    native window class rather than the current window instance.
    """

    try:
        import ctypes

        user32 = ctypes.windll.user32
        hwnd = hwnd or user32.FindWindowW(None, title)
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
        set_class_icon = getattr(user32, "SetClassLongPtrW", None)
        if set_class_icon is None:
            set_class_icon = user32.SetClassLongW
        set_class_icon(hwnd, -14, image_icon)  # GCLP_HICON
        set_class_icon(hwnd, -34, image_icon)  # GCLP_HICONSM
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
        self._dashboard_hidden = False
        self._tray_icon: Any | None = None
        self._tray_thread: threading.Thread | None = None
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

    def _show_dashboard(self, *_args: Any) -> None:
        if self.window is None or self._closed:
            return
        try:
            self.window.show()
            self._dashboard_hidden = False
        except Exception:
            return

    def _hide_dashboard(self, *_args: Any) -> None:
        if self.window is None or self._closed:
            return
        try:
            self.window.hide()
            self._dashboard_hidden = True
        except Exception:
            return

    def _toggle_tracking(self, *_args: Any) -> None:
        try:
            self.service.update_settings(
                tracking_paused=not self.service.is_tracking_paused()
            )
            if self._tray_icon is not None:
                self._tray_icon.update_menu()
        except Exception as error:
            print(f"Warning: could not change tracking state: {error}")

    def _create_tray_icon(self) -> Any:
        """Create the pystray icon while keeping all imports display-lazy."""

        try:
            import pystray
            from PIL import Image
        except ImportError as error:
            raise RuntimeError(
                "The Windows desktop shell requires pystray and Pillow. Install "
                "requirements-packaging.lock in the project environment."
            ) from error

        icon_path = resource_path("assets/filememory.ico")
        if not icon_path.is_file():
            raise RuntimeError(f"Missing tray icon: {icon_path}")
        image = Image.open(icon_path)
        show_label, hide_label, _, exit_label = tray_menu_labels(
            self.service.is_tracking_paused()
        )
        menu = pystray.Menu(
            pystray.MenuItem(show_label, self._show_dashboard),
            pystray.MenuItem(hide_label, self._hide_dashboard),
            pystray.MenuItem(
                lambda _item: tray_menu_labels(self.service.is_tracking_paused())[2],
                self._toggle_tracking,
            ),
            pystray.MenuItem(exit_label, self._exit_from_tray),
        )
        return pystray.Icon(TRAY_ICON_NAME, image, WEBVIEW_TITLE, menu)

    def _start_tray(self) -> None:
        if self._tray_icon is not None:
            return
        self._tray_icon = self._create_tray_icon()
        self._tray_thread = threading.Thread(
            target=self._tray_icon.run,
            name="filememory-tray",
            daemon=True,
        )
        self._tray_thread.start()

    def _stop_tray(self) -> None:
        if self._tray_icon is not None:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
            self._tray_icon = None

    def _exit_from_tray(self, *_args: Any) -> None:
        self._stop_tray()
        if self.window is not None:
            try:
                self.window.destroy()
                return
            except Exception:
                pass
        self._close()

    def _close(self, *_args: Any) -> None:
        if self._closed:
            return
        self._closed = True
        self._stop_tray()
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
        # This must run before WebView2 creates its HWND so Windows associates
        # the native window and taskbar entry with File Memory's identity.
        set_windows_app_user_model_id()
        hide_on_ready = should_start_hidden(
            start_minimized, is_setup_complete(self.service)
        )
        try:
            self._start_tray()
            self.window = webview.create_window(
                url=self.url,
                # Tray minimization is a hide operation, not a minimized
                # taskbar button.  This keeps the dashboard out of the taskbar
                # while preserving the running watcher/service process.
                **window_options(False),
            )
            self.window.events.loaded += self._on_page_loaded
            self.window.events.closed += self._close
            # pywebview does not expose an icon argument. Apply the ICO after
            # the native window exists; the delayed retry handles WebView2's
            # asynchronous HWND creation.
            def on_gui_ready() -> None:
                apply_windows_icon()
                if hide_on_ready:
                    self._hide_dashboard()

            threading.Timer(0.8, apply_windows_icon).start()
            # edgechromium is pywebview's Microsoft Edge WebView2 backend on
            # Windows.  The runtime is intentionally supplied by Windows and
            # is not bundled into the PyInstaller artifact.
            webview.start(gui="edgechromium", debug=False, func=on_gui_ready)
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
