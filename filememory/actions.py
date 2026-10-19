"""Safe, non-shell file and folder actions for a future HTTP API."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


class ActionError(ValueError):
    pass


def open_file(path: str | Path) -> str:
    candidate = Path(path).expanduser().resolve()
    if not candidate.is_file():
        raise ActionError("file does not exist")
    if sys.platform == "win32":
        os.startfile(str(candidate))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(candidate)])
    else:
        subprocess.Popen(["xdg-open", str(candidate)])
    return str(candidate)


def open_folder(path: str | Path) -> str:
    candidate = Path(path).expanduser().resolve()
    if not candidate.is_dir():
        raise ActionError("folder does not exist")
    if sys.platform == "win32":
        os.startfile(str(candidate))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(candidate)])
    else:
        subprocess.Popen(["xdg-open", str(candidate)])
    return str(candidate)
