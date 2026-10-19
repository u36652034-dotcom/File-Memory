"""Freeze the WebView2 desktop shell and provide a non-GUI package check."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
import sqlite3
import sys


def package_check(destination: str) -> None:
    """Verify bundled Python modules/resources without opening a dashboard."""

    import webview
    from watchdog.observers import Observer

    modules = [
        path.stem
        for path in (Path(__file__).resolve().parent / "tools" / "filememory").glob("*.py")
        if path.stem != "__init__"
    ]
    for name in modules:
        importlib.import_module(f"filememory.{name}")
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("CREATE VIRTUAL TABLE package_check USING fts5(text)")
    finally:
        connection.close()
    bundle = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    required = [
        "assets/filememory.ico",
        "web/index.html",
        "web/styles.css",
        "web/app.js",
        "tools/scripts/prepare_models.py",
        "tools/scripts/prepare_models_windows.ps1",
    ]
    missing = [name for name in required if not (bundle / name).is_file()]
    if missing:
        raise RuntimeError(f"Missing bundled resources: {missing}")
    Path(destination).write_text(
        json.dumps(
            {
                "ok": True,
                "modules": modules,
                "observer": Observer.__name__,
                "webview": getattr(webview, "__version__", "unknown"),
                "frozen": bool(getattr(sys, "frozen", False)),
            }
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--package-check":
        package_check(sys.argv[2])
    else:
        from filememory.desktop import main

        main()
