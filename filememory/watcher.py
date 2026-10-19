"""Watchdog event adapter; no polling is used."""

from __future__ import annotations

import threading
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
    def __init__(
        self,
        folders: list[str | Path],
        on_path: Callable[[str], object],
        ready_delay: float = 0.35,
    ) -> None:
        self.folders = [str(Path(folder).expanduser().resolve()) for folder in folders]
        self.on_path = on_path
        self.ready_delay = ready_delay
        self._observer = None
        self._timers: dict[str, threading.Timer] = {}
        self._timer_lock = threading.Lock()

    def _schedule_ready_check(self, path: str) -> None:
        """Debounce bursts and retry once after a write settles.

        This is deliberately timer-after-event behavior, not a polling loop:
        downloads that emit several modify events get one final readiness check
        after the last event.
        """
        with self._timer_lock:
            previous = self._timers.pop(path, None)
            if previous is not None:
                previous.cancel()

            def run() -> None:
                try:
                    self.on_path(path)
                finally:
                    with self._timer_lock:
                        self._timers.pop(path, None)

            timer = threading.Timer(self.ready_delay, run)
            timer.daemon = True
            self._timers[path] = timer
            timer.start()

    def start(self) -> None:
        FileSystemEventHandler, Observer = _watchdog_types()

        class Handler(FileSystemEventHandler):
            def on_created(self, event):
                if not event.is_directory:
                    watcher._schedule_ready_check(event.src_path)

            def on_modified(self, event):
                if not event.is_directory:
                    watcher._schedule_ready_check(event.src_path)

            def on_moved(self, event):
                if not event.is_directory:
                    watcher._schedule_ready_check(event.dest_path)

        self._observer = Observer()
        watcher = self
        handler = Handler()
        for folder in self.folders:
            self._observer.schedule(handler, folder, recursive=True)
        self._observer.start()

    def stop(self) -> None:
        with self._timer_lock:
            timers = list(self._timers.values())
            self._timers.clear()
        for timer in timers:
            timer.cancel()
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
