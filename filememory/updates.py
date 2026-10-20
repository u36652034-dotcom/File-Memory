"""Small, failure-tolerant update manifest checker for the desktop app."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
import os
from pathlib import Path
import re
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .paths import app_data_dir
from .version import APP_VERSION


DEFAULT_UPDATE_MANIFEST_URL = "https://updates.usmanautomates.com/file-memory/latest.json"
UPDATE_MANIFEST_ENV = "FILE_MEMORY_UPDATE_MANIFEST_URL"
UPDATE_CHECK_STATE_FILE = "update-check.json"
FETCH_TIMEOUT_SECONDS = 4.0
MAX_MANIFEST_BYTES = 1_000_000

_VERSION_PATTERN = re.compile(
    r"^v?(?P<major>0|[1-9]\d*)\."
    r"(?P<minor>0|[1-9]\d*)\."
    r"(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


@dataclass(frozen=True)
class SemanticVersion:
    """A SemVer value with the precedence rules needed for update checks."""

    major: int
    minor: int
    patch: int
    prerelease: tuple[str, ...] = ()

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, SemanticVersion):
            return NotImplemented
        core = (self.major, self.minor, self.patch)
        other_core = (other.major, other.minor, other.patch)
        if core != other_core:
            return core < other_core
        if not self.prerelease and not other.prerelease:
            return False
        if not self.prerelease:
            return False
        if not other.prerelease:
            return True
        for left, right in zip(self.prerelease, other.prerelease):
            if left == right:
                continue
            left_numeric = left.isdigit()
            right_numeric = right.isdigit()
            if left_numeric and right_numeric:
                return int(left) < int(right)
            if left_numeric != right_numeric:
                return left_numeric
            return left < right
        return len(self.prerelease) < len(other.prerelease)


@dataclass(frozen=True)
class UpdateManifest:
    """Validated data displayed by the native update notification."""

    version: str
    release_url: str
    fixes: tuple[str, ...] = ()
    features: tuple[str, ...] = ()
    release_notes: str = ""


def parse_version(value: str) -> SemanticVersion:
    """Parse a strict three-part semantic version, optionally with metadata."""

    match = _VERSION_PATTERN.fullmatch(str(value).strip())
    if not match:
        raise ValueError(f"invalid semantic version: {value!r}")
    prerelease = tuple((match.group("prerelease") or "").split(".")) if match.group("prerelease") else ()
    return SemanticVersion(
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch")),
        prerelease,
    )


def is_newer_version(latest: str, current: str = APP_VERSION) -> bool:
    """Return whether ``latest`` has higher SemVer precedence than ``current``."""

    return parse_version(current) < parse_version(latest)


def _text_list(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    values = value if isinstance(value, list) else [value]
    return tuple(str(item).strip() for item in values if str(item).strip())


def _release_notes_text(value: Any) -> str:
    """Normalize either plain notes or a structured notes object."""
    if isinstance(value, dict):
        sections: list[str] = []
        for title in ("summary", "fixes", "features", "text"):
            items = _text_list(value.get(title))
            if items:
                sections.append(f"{title.title()}:\n" + "\n".join(f"- {item}" for item in items))
        return "\n\n".join(sections)
    return "\n".join(_text_list(value))


def _valid_https_url(value: Any) -> str:
    url = str(value or "").strip()
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("release_url must be an absolute HTTPS URL")
    return url


def parse_manifest(payload: Any) -> UpdateManifest:
    """Validate the public manifest shape and normalize display fields."""

    if not isinstance(payload, dict):
        raise ValueError("update manifest must be a JSON object")
    version = str(payload.get("version", "")).strip()
    parse_version(version)
    return UpdateManifest(
        version=version,
        release_url=_valid_https_url(payload.get("release_url")),
        fixes=_text_list(payload.get("fixes")),
        features=_text_list(payload.get("features")),
        release_notes=_release_notes_text(payload.get("release_notes")),
    )


def fetch_manifest(
    manifest_url: str,
    timeout: float = FETCH_TIMEOUT_SECONDS,
    opener: Callable[..., Any] = urlopen,
) -> UpdateManifest | None:
    """Fetch and parse a manifest; every transport/format failure is silent."""

    try:
        parsed = urlparse(manifest_url)
        if parsed.scheme != "https" or not parsed.netloc:
            return None
        request = Request(
            manifest_url,
            headers={"Accept": "application/json", "User-Agent": f"FileMemory/{APP_VERSION}"},
        )
        with opener(request, timeout=timeout) as response:
            raw = response.read(MAX_MANIFEST_BYTES + 1)
        if len(raw) > MAX_MANIFEST_BYTES:
            return None
        return parse_manifest(json.loads(raw.decode("utf-8")))
    except (
        HTTPError,
        URLError,
        OSError,
        TimeoutError,
        ValueError,
        TypeError,
        AttributeError,
        UnicodeError,
        json.JSONDecodeError,
    ):
        return None


def _state_path(path: str | Path | None) -> Path:
    return Path(path) if path is not None else app_data_dir() / UPDATE_CHECK_STATE_FILE


def _today(now: date | None = None) -> str:
    return (now or date.today()).isoformat()


def _already_checked_today(path: Path, today: str) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload.get("last_checked") == today
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def _mark_checked(path: Path, today: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps({"last_checked": today}), encoding="utf-8")
        temporary.replace(path)
    except OSError:
        # A read-only profile should not disable the app's normal operation.
        pass


def check_for_update(
    current_version: str = APP_VERSION,
    manifest_url: str | None = None,
    state_path: str | Path | None = None,
    now: date | None = None,
    fetcher: Callable[[str], UpdateManifest | None] = fetch_manifest,
) -> UpdateManifest | None:
    """Check at most once per local calendar day and return an available update."""

    path = _state_path(state_path)
    today = _today(now)
    if _already_checked_today(path, today):
        return None
    _mark_checked(path, today)
    url = manifest_url or os.getenv(UPDATE_MANIFEST_ENV, DEFAULT_UPDATE_MANIFEST_URL)
    manifest = fetcher(url)
    if manifest is None:
        return None
    try:
        return manifest if is_newer_version(manifest.version, current_version) else None
    except ValueError:
        return None
