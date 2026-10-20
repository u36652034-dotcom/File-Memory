# File Memory

Local-first Python 3.12 app for indexing folders you explicitly select and searching file names, notes, and short text snippets. **SQLite is the only required storage.** Semantic embeddings, SmolLM2, Groq, and filesystem watching are optional integrations loaded only when used.

## ⬇️ Install (Windows)

**[Download from GitHub Releases](https://github.com/usman-automates/File-Memory/releases)** — anyone can install anytime.

| Variant | Description |
|---------|-------------|
| **online** | Model runtime + first-run download. No model weights bundled. |

Requires **Microsoft Edge WebView2 Runtime** (normally already present on supported Windows).

---

## Setup

### Windows

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.lock
```

### Linux

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.lock
```

The base app is fully offline: SQLite keyword search + deterministic note suggestions. Dependencies: `watchdog` (runtime), `pytest` (tests).

### Optional Local Models (semantic search + SmolLM2)

```powershell
# Windows
python -m pip install -r requirements-models.txt
python scripts\prepare_models.py
```

```bash
# Linux
python -m pip install -r requirements-models.txt
python scripts/prepare_models.py
```

This downloads `all-MiniLM-L6-v2` and `HuggingFaceTB/SmolLM2-360M-Instruct` into `.models/` (Git-ignored). Set `FILE_MEMORY_OFFLINE_MODE=1` after prep to prevent later network calls. Missing models fall back to keyword search / offline note suggestions.

Copy `.env.example` → `.env` when configuring the optional Groq provider or a project-local model cache. **Never commit credentials.**

---

## Run

### Web UI (loopback only)

```bash
python -m filememory.web
```

Open <http://127.0.0.1:8765/>. From the Inbox you can add folders, search, open/forget files, and manage settings.

- AI mode: **No AI** (default) / **Local AI** / **Groq**
- Ignored extensions configurable
- Rebuild search index
- Forget never deletes the real file

### Desktop App (Windows, native WebView2)

```powershell
python -m pip install -r requirements-packaging.lock
.\.venv\Scripts\python.exe -m filememory.desktop
```

Tray menu: **Show dashboard**, **Hide dashboard**, **Pause/Resume tracking**, **Exit**. Hiding keeps the API + watcher running; only **Exit** stops them.

Launch hidden to tray after setup:

```powershell
.\.venv\Scripts\python.exe -m filememory.desktop --minimized
```

> `--minimized` hides the dashboard only after setup is complete. First run still shows the dashboard so setup can be finished.

---

## Python API

```python
from filememory.service import FileMemoryService

service = FileMemoryService()
service.add_folder("/home/me/Documents")
service.index_path("/home/me/Documents/plan.txt", note="project plan")
matches = service.search("where is the project plan?", semantic=True)
```

Key methods:

- `get_settings()` / `update_settings(...)` — pause state, chat mode, ignored extensions
- `rebuild_search_index()` — explicit scan + FTS rebuild
- `forget_file` / `remove_folder` — require `confirmed=True`, never delete user files
- `start_tracking()` / `stop_tracking()` — watchdog events; stable files only, incomplete downloads skipped
- `list_pending_suggestions()` / `confirm_suggestion(id, note)`
- API mirror: `GET /api/suggestions`, `POST /api/suggestions/confirm`
- `open_file` / `open_folder` — argument arrays, never a shell

Semantic search is independent of the chat suggestion setting: it tries `all-MiniLM-L6-v2` and falls back to SQLite keyword ranking.

---

## Test

```bash
python -m pytest -q
```

Fully offline: temporary SQLite databases, fake embedding providers, no downloads, no network. `make test` is a Unix convenience wrapper.

---

## Docker

```bash
docker build -t filememory-backend .
docker run --rm -p 8765:8765 -v "$PWD/data:/data" filememory-backend
```

Open <http://127.0.0.1:8765/>. The database is stored at `/data/filememory.sqlite3`; mount a host directory to persist it. Watched folders must also be accessible to the container.

---

## Windows Packaging

Packaging runs on **Windows x64** with the project-local Python 3.12 environment (PyInstaller does not cross-compile).

```powershell
.\scripts\build_windows.ps1 -Variant online -Mode both
.\scripts\validate_windows_package.ps1 -Variant online -Mode both
```

### Installers

Requires [Inno Setup](https://jrsoftware.org/isinfo.php)'s `ISCC.exe` (not installed by project scripts).

```powershell
.\scripts\build_installer.ps1 -Variant online
.\scripts\build_installer.ps1 -Variant offline
```

**Output:**

- `dist\FileMemory-Setup-online.exe`
- `dist\FileMemory-Setup-offline.exe`

Use `-SkipPackageBuild` if the matching onedir artifact already exists. The offline build requires both model snapshots in `%LOCALAPPDATA%\FileMemory\models` (or pass `-ModelSource 'D:\FileMemoryModelCache'`); it fails fast if either cache is missing.

**Installer behavior:**

- Installs to `C:\Program Files\File Memory` (admin required)
- Creates Start Menu + Desktop shortcuts
- Creates a checked-by-default HKCU Startup entry (launches minimized to tray)
- Optional post-install launch checkbox

**Release checklist:**

1. Validate both onedir variants (online has no model cache; offline has both trees).
2. Compile and validate both installers with `-RequireInstaller`.
3. Test on clean Windows x64 with WebView2 Runtime (install path, shortcuts, startup, tray).
4. Verify online first-run download; verify offline semantic + Local AI without network.
5. Record SHA-256 hashes for both installers.

---

## Desktop Behavior

### Startup

1. First launch opens the dashboard so setup can be completed.
2. Setup asks for a watched folder, verifies the embedding model, and lets the user choose **Local AI** (SmolLM2) or **Groq**.
3. After setup, the optional Startup shortcut launches File Memory hidden to the notification area.
4. Tray menu: **Show dashboard**, **Hide dashboard**, **Pause/Resume tracking**, **Exit**.

### New-file flow

1. A watched folder emits a filesystem event (no polling).
2. The watcher ignores incomplete download suffixes and waits for file stability.
3. A draft note is generated — Local AI, Groq, or offline heuristic fallback.
4. A small prompt appears bottom-right with the filename, editable note, **Remember**, and **Dismiss**.
5. Auto-hides after 8 seconds. **Remember** persists the note to SQLite; **Dismiss** leaves the draft in the dashboard's suggestions.

### Layout

Approximately 1200×820. Split view:

- **Left:** intro + watched-folder summary
- **Right:** search, meaning/exact-word toggles, ranked results, note suggestions

The WebView2 shell shares the same `web/` assets as the browser fallback, so desktop and web stay behaviorally aligned.

---

## Credits

> **Vibecoded by Osman ♥ · with OmniRush ♥**

The desktop shell checks the production update manifest once per calendar day in a background thread. Network or malformed-manifest failures are ignored silently. Set `FILE_MEMORY_UPDATE_MANIFEST_URL` to use a different HTTPS manifest during development; each manifest must provide a semantic `version`, an HTTPS `release_url`, and optional `features`, `fixes`, and `release_notes` fields.
