# File Memory backend

Local-first Python 3.12 backend for indexing explicitly selected folders and
searching file names, notes, and short text snippets. SQLite is the only
required storage system. Semantic embeddings, local language-model suggestions,
Groq suggestions, and filesystem watching are optional integrations loaded only
when used.

## Setup

Python 3.12 is pinned in `.python-version`. Create an environment inside the
project and install the pinned lock file:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.lock
```

The runtime dependency is `watchdog`; the test dependency is `pytest`. The
optional `sentence-transformers` and `transformers` integrations are intentionally
not installed by default because they download large model packages. If enabled
by an application, models are loaded lazily and failures fall back safely.

Copy `.env.example` to `.env` only when configuring the optional Groq provider.
Never commit credentials.

## Run

The service can be embedded in a future HTTP API or a Python process:

```python
from filememory.service import FileMemoryService

service = FileMemoryService()
service.add_folder("/home/me/Documents")
service.index_path("/home/me/Documents/plan.txt", note="project plan")
matches = service.search("where is the project plan?", semantic=True)
```

Use `filememory.watcher.FolderWatcher` with the folders returned by
`list_folders()` to receive watchdog create/modify/move events. Events are
indexed only after a file is stable; incomplete download suffixes are skipped.
`open_file` and `open_folder` use argument arrays (never a shell) and reject
missing paths.

## Test

The one offline test command is:

```bash
make test
```

Tests use temporary SQLite databases and fake embedding providers. They never
download models or call the network.

## Deploy / container smoke run

Build and run the self-contained backend image:

```bash
docker build -t filememory-backend .
docker run --rm -v "$PWD/data:/data" filememory-backend
```

The container command initializes `/data/filememory.sqlite3` and prints
`filememory ready`. Mount a host data directory to keep the local database.
