"""Watchdog event adapter; no polling is used."""

from __future__ import annotations

from pathlib import Path
from typing import Callable


class WatchdogUnavailableError(RuntimeError):
    """Raised with an actionable message when watchdog is not installed."""


def _watchdog_types():
    try:
        from watchdog.events import FileSystemEventHandler  # type: ignore
        from watchdog.observers import Observer  # type: ignore
    except ImportError as error:
        raise WatchdogUnavailableError(
            "Filesystem watching requires watchdog; install dependencies with "
            "python -m pip install -r requirements.txt"
        ) from error
    return FileSystemEventHandler, Observer


class FolderWatcher:
    def __init__(self, folders: list[str | Path], on_path: Callable[[str], object]) -> None:
        self.folders = [str(Path(folder).expanduser().resolve()) for folder in folders]
        self.on_path = on_path
        self._observer = None

    def start(self) -> None:
        FileSystemEventHandler, Observer = _watchdog_types()
        callback = self.on_path

        class Handler(FileSystemEventHandler):
            def on_created(self, event):
                if not event.is_directory:
                    callback(event.src_path)

            def on_modified(self, event):
                if not event.is_directory:
                    callback(event.src_path)

            def on_moved(self, event):
                if not event.is_directory:
                    callback(event.dest_path)

        self._observer = Observer()
        handler = Handler()
        for folder in self.folders:
            self._observer.schedule(handler, folder, recursive=True)
        self._observer.start()

    def stop(self) -> None:
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
