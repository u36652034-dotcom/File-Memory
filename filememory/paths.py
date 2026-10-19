"""Portable application paths and environment helpers."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def app_data_dir() -> Path:
    override = os.getenv("FILE_MEMORY_DATA_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        return Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "FileMemory"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "FileMemory"
    return Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "filememory"


def default_database_path() -> Path:
    configured = os.getenv("FILE_MEMORY_DATABASE")
    if configured:
        return Path(configured).expanduser()
    return app_data_dir() / "filememory.sqlite3"


def model_cache_dir() -> Path:
    configured = os.getenv("FILE_MEMORY_MODEL_DIR")
    path = Path(configured).expanduser() if configured else app_data_dir() / "models"
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_dotenv(path: str | Path = ".env") -> None:
    """Load simple KEY=VALUE pairs without adding a dotenv dependency."""
    dotenv = Path(path)
    if not dotenv.is_absolute() and not dotenv.is_file():
        dotenv = Path(__file__).resolve().parent.parent / dotenv
    if not dotenv.is_file():
        return
    for line in dotenv.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip("\"'")
        os.environ.setdefault(key, value)
