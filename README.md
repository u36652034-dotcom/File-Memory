# File Memory

Local-first Python 3.12 app for indexing explicitly selected folders and
searching file names, notes, and short text snippets. SQLite is the only
required storage system. Semantic embeddings, local language-model suggestions,
Groq suggestions, and filesystem watching are optional integrations loaded only
when used.

## Setup (Windows)

Python 3.12 is pinned in `.python-version`. Create an environment inside the
project and install the pinned lock file:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.lock
```

If PowerShell blocks activation, run the project interpreter directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m filememory.web
```

## Setup (Linux)

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.lock
```

The runtime dependency is `watchdog`; the test dependency is `pytest`. The
base app has no model dependency and remains fully offline through SQLite
keyword search and deterministic note suggestions. Install the optional local
model runtime into the same project environment when you want semantic search
and SmolLM2 note suggestions:

```powershell
# Windows
.\.venv\Scripts\python.exe -m pip install -r requirements-models.txt
.\.venv\Scripts\python.exe scripts\prepare_models.py
```

```bash
# Linux
.venv/bin/python -m pip install -r requirements-models.txt
.venv/bin/python scripts/prepare_models.py
```

For reproducible installs, replace `requirements-models.txt` with
`requirements-models.lock` in the commands above. The preparation script
downloads `all-MiniLM-L6-v2` and
`HuggingFaceTB/SmolLM2-360M-Instruct` into `.models/`, which is ignored by
Git. Set `FILE_MEMORY_OFFLINE_MODE=1` after preparation to prevent later model
loads from attempting network access. If a model is unavailable, the app
continues with keyword search or the offline note provider.

Copy `.env.example` to `.env` when configuring the optional Groq provider or
project-local model cache. The app loads this file without an extra dependency.
Never commit credentials.

## Run the local inbox and settings screen

Start the loopback-only app with the standard library HTTP server from the
project environment:

```bash
python -m filememory.web
```

Open <http://127.0.0.1:8765/>. The Inbox searches indexed files and provides
safe open and forget actions. Newly indexed files appear as pending note
suggestions; edit or confirm a suggestion in the Inbox before it is saved to
the file's note. Settings lets you add/remove watched folder
paths, pause tracking, choose **No AI** (default), **Local AI**, or **Groq**,
ignore extensions, and rebuild the search index. Folder removal and forgetting
an indexed file require a browser confirmation; forgetting never deletes the
real file.

All API routes bind to `127.0.0.1` by default. The UI has no external assets or
network calls. When Groq is selected, only the optional note suggestion call
uses the configured Groq endpoint. Adding a watched folder explicitly scans
files already present and returns an `indexed`/`skipped`/`total` summary; it
does not start a polling loop. Watchdog handles later changes through
filesystem events.

The database defaults to the platform application-data directory. Override it
with `FILE_MEMORY_DATABASE` when you need a portable project-local file. If a
system Python is used without installing `requirements.lock`, the UI can still
start but it will display a filesystem-tracking warning; use the project-local
interpreter above to enable event watching.

## Run the native Windows desktop app

The desktop entrypoint starts the same loopback API in-process and displays
the existing `web/index.html`, `web/styles.css`, and `web/app.js` through
pywebview's native Microsoft Edge WebView2 backend. It does not launch an
external browser or replace the web UI with a second desktop UI. On first run,
use **Watched folders** and **Settings** in the embedded app to choose a folder
and configure tracking/provider options; those controls use the existing API.
Install the packaging lock in the project environment first:

```powershell
python -m pip install -r requirements-packaging.lock
.\.venv\Scripts\python.exe -m filememory.desktop
```

The embedded app registers the custom FM grid icon in the Windows notification
area and offers **Show dashboard**, **Hide dashboard**, **Pause/Resume
tracking**, and **Exit** tray actions. Hiding the dashboard leaves the local
API and filesystem watcher running; only **Exit** or closing the dashboard
stops them. It supports the same keyword/semantic search, safe open-file/open-
folder and copy-path actions, editable pending notes, watched-folder
management, AI mode, and tracking controls as the local web app. New watcher
events use the web UI's non-blocking toast and auto-hide after eight seconds.
To preserve the startup shortcut behavior, pass `--minimized`:

```powershell
.\.venv\Scripts\python.exe -m filememory.desktop --minimized
```

After a watched folder has been selected, `--minimized` hides the dashboard to
the notification area after startup. On a first run it still shows the
dashboard so setup can be completed.

Windows must have the Microsoft Edge WebView2 Runtime installed. pywebview and
the PyInstaller package do not bundle that runtime; the Evergreen WebView2
Runtime is normally present on supported Windows installations and can be
installed separately by an administrator or device-management tool if it is
missing.

If the embedding model is not ready, the existing web Settings surface keeps
the app usable with offline keyword search and deterministic note suggestions.

## Python service API

```python
from filememory.service import FileMemoryService

service = FileMemoryService()
service.add_folder("/home/me/Documents")
service.index_path("/home/me/Documents/plan.txt", note="project plan")
matches = service.search("where is the project plan?", semantic=True)
```

`service.get_settings()` and `service.update_settings(...)` persist the pause
state, chat suggestion mode, and ignored extensions. Semantic search is
independent of the chat suggestion setting: it attempts the lazy
`all-MiniLM-L6-v2` embedding model whenever Meaning is selected and falls back
to SQLite keyword ranking if the model cannot load. `service.rebuild_search_index()` is an
explicit scan of selected folders plus an FTS rebuild. `forget_file` and
`remove_folder` require `confirmed=True` and never remove user files.

Use `start_tracking()` and `stop_tracking()` with the folders returned by
`list_folders()` to receive watchdog create/modify/move events. Events are
indexed only after a file is stable; incomplete download suffixes are skipped.
`list_pending_suggestions()` exposes drafts, and `confirm_suggestion(id, note)`
persists an edited or unchanged note. The loopback API mirrors these operations
at `GET /api/suggestions` and `POST /api/suggestions/confirm`.
`open_file` and `open_folder` use argument arrays (never a shell) and reject
missing paths.

## Test (Windows and Linux)

The one offline test command is:

```bash
python -m pytest -q
```

`make test` is also available as a Unix convenience wrapper.

Tests use temporary SQLite databases and fake embedding providers. They never
download models or call the network.

## Deploy / container smoke run

Build and run the self-contained backend image:

```bash
docker build -t filememory-backend .
docker run --rm -p 8765:8765 -v "$PWD/data:/data" filememory-backend
```

Open <http://127.0.0.1:8765/>. The container serves the loopback-style local
HTTP UI and stores the SQLite database at `/data/filememory.sqlite3`; mount a
host data directory to keep it between runs. The selected folders must also be
accessible to the process/container for event watching.

## Windows x64 packaging

Packaging is performed on Windows x64 with the project-local Python 3.12
environment. PyInstaller does not cross-compile Windows executables, so run
these commands from a Windows x64 checkout:

```powershell
py -3.12 -m venv .venv                 # only needed once
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\scripts\build_windows.ps1 -Variant online -Mode both
```

The build script installs PyInstaller and Pillow only into `.venv` when they
are missing, generates `assets\filememory.ico`, and writes these portable
artifacts:

* `dist\online\FileMemory\` and `dist\online\FileMemory-onefile.exe` — the
  online artifacts. They include the model runtime and first-run download
  flow, but no Hugging Face model weights.
* `dist\offline\FileMemory\` and `dist\offline\FileMemory-onefile.exe` —
  offline artifacts with the cached Hugging Face assets under `models\`.

Separate output roots prevent an offline model payload from leaking into an
online build. The build removes the selected output before PyInstaller runs,
and online validation rejects model-cache directories.

Use the project interpreter to run the validation script after a build:

```powershell
.\scripts\validate_windows_package.ps1 -Variant online -Mode both
```

The spec includes every `filememory` module, the exact `web` files, pywebview,
the model runtime, and the model download scripts. It uses
`filememory\desktop.py` through `packaging\desktop_entrypoint.py`, so the
packaged app opens the native WebView2 shell rather than an external browser.
The application stores its database and model cache in the user's
application-data directory by default.

### Online installer

```powershell
.\scripts\build_installer.ps1 -Variant online
.\scripts\validate_windows_package.ps1 -Variant online -Mode onedir -RequireInstaller
```

Output: `dist\FileMemory-Setup-online.exe`.

### Offline installer

Prepare both models into the default Windows cache, then build from that cache:

```powershell
.\scripts\prepare_models_windows.ps1
.\scripts\build_installer.ps1 -Variant offline
.\scripts\validate_windows_package.ps1 -Variant offline -Mode onedir -RequireInstaller
```

The default source is `%LOCALAPPDATA%\FileMemory\models`. A different cache can
be supplied without committing a machine-specific path:

```powershell
.\scripts\build_windows.ps1 -Variant offline -Mode onedir `
  -ModelSource 'D:\FileMemoryModelCache'
.\scripts\validate_windows_package.ps1 -Variant offline -Mode onedir
```

The offline build requires snapshot files for both
`sentence-transformers/all-MiniLM-L6-v2` and
`HuggingFaceTB/SmolLM2-360M-Instruct`; it fails before PyInstaller if either
cache is absent. Output: `dist\FileMemory-Setup-offline.exe`.

Use `-SkipPackageBuild` with `build_installer.ps1` when the matching
`dist\online\FileMemory\` or `dist\offline\FileMemory\` directory already
exists. `ISCC.exe` is an external Inno Setup tool and is not installed by the
project scripts.

### Windows release checklist

1. Build and validate both onedir variants; confirm online has no model cache
   and offline has both model cache trees under `models\`.
2. Compile and validate both installers with `-RequireInstaller`.
3. On clean Windows x64 with WebView2 Runtime, verify install path, Start Menu
   and Desktop shortcuts, optional HKCU startup entry, minimized tray launch,
   dashboard hide/show, and tray Exit behavior.
4. Verify online first-run model preparation with network access; disconnect the
   network and verify offline semantic search and Local AI setup.
5. Record SHA-256 hashes for both installers before the GitHub release.

The native shell, packaged executable, taskbar identity, and notification-area
icon use the custom blue/lime FM grid icon in `assets\filememory.ico`. The
dashboard footer credits **Vibecoded by Osman
♥ · with OmniRush ♥**.

The desktop shell checks the production update manifest once per local calendar
day in a background thread. Network or malformed-manifest failures are ignored
so tracking continues normally. Set `FILE_MEMORY_UPDATE_MANIFEST_URL` to use a
different HTTPS manifest during development; each manifest must provide a
semantic `version`, an HTTPS `release_url`, and optional `features`, `fixes`,
and `release_notes` fields.

### Installer behavior

Install [Inno Setup](https://jrsoftware.org/isinfo.php) on the Windows build
machine. Build either variant as documented above, or compile an already-built
matching onedir artifact:

```powershell
.\scripts\build_installer.ps1 -Variant online
.\scripts\build_installer.ps1 -Variant offline
```

If `dist\online\FileMemory\` or `dist\offline\FileMemory\` already exists,
skip the PyInstaller step:

```powershell
.\scripts\build_installer.ps1 -Variant online -SkipPackageBuild
```

The installer defaults to `C:\Program Files\File Memory` and declares
`PrivilegesRequired=admin`, so Windows asks for administrator approval during
installation. It creates Start Menu and Desktop shortcuts and creates a
checked-by-default HKCU Startup Apps entry that launches the app minimized to
the notification area. Windows Startup Apps/Task Manager can disable or
re-enable that entry. A separate
post-install checkbox lets the user launch the app immediately. File Memory
only accesses folders the user explicitly selects inside the app; it does not
request or require administrator-only Windows permissions.

`ISCC.exe` is an external Inno Setup tool and is not installed by the project
scripts. If it is unavailable, `build_installer.ps1` stops with an actionable
message; PyInstaller artifacts can still be built and validated independently.

## Windows desktop behavior

The installed app is a native WebView2 desktop shell around the existing File
Memory interface; it does not open a normal browser tab.

### Startup and tray

1. The first launch opens the dashboard so setup can be completed.
2. Setup asks for a watched folder, verifies the required `all-MiniLM-L6-v2`
   embedding model, and lets the user choose Local AI (SmolLM2) or Groq for
   note suggestions.
3. After setup, the optional Startup shortcut launches File Memory hidden from
   the main taskbar and keeps it in the Windows notification area.
4. The tray menu provides **Show dashboard**, **Hide dashboard**, **Pause/Resume
   tracking**, and **Exit**. Windows may place the icon inside its overflow
   arrow according to the user's taskbar settings.
5. Hiding the dashboard does not stop SQLite, the event watcher, or the local
   API. Closing from the tray exits all of them.

### New-file notification flow

1. A selected folder emits a filesystem event; the app does not poll.
2. The watcher ignores incomplete download suffixes and waits for the file to
   become stable.
3. File Memory creates a short draft from the filename/snippet using the
   selected provider. Local AI and Groq are optional; the offline heuristic is
   the safe fallback.
4. A small in-app prompt appears above the lower-right edge of the dashboard,
   with the filename, editable note, **Remember**, and **Dismiss**.
5. The prompt disappears automatically after eight seconds. Remember persists
   the edited note in SQLite; Dismiss leaves the draft available in the
   dashboard's suggestions section.

### Dashboard layout

The standard window is approximately 1200×820 and uses the supplied indigo,
lime, and FM icon language. It has a flexible split layout: the left side is
the memory introduction and watched-folder summary; the right side contains
search, meaning/exact-word controls, ranked results, and note suggestions.
Maximizing the window expands the grid and type; only long result lists scroll.
The WebView2 shell keeps the same UI code as the earlier web preview, so the
desktop and browser fallback remain behaviorally aligned.
