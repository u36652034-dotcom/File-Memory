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
