File Memory
Local-first Python 3.12 app for indexing folders you explicitly select and searching file names, notes, and snippets. SQLite is the only required storage. Semantic embeddings, SmolLM2, Groq, and filesystem watching are optional.

⬇️ Install (Windows)
Download from GitHub Releases — anyone can install anytime.

online — model runtime + first-run download (no weights bundled)

Requires Microsoft Edge WebView2 Runtime (usually already installed).

Setup
Windows

powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.lock
Linux

bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.lock
Base app is fully offline (SQLite keyword search + offline note suggestions). Deps: watchdog (runtime), pytest (tests).

Optional local models (semantic search + SmolLM2):

powershell
python -m pip install -r requirements-models.txt
python scripts\prepare_models.py
Downloads all-MiniLM-L6-v2 and HuggingFaceTB/SmolLM2-360M-Instruct into .models/ (Git-ignored). Set FILE_MEMORY_OFFLINE_MODE=1 after prep. Missing models fall back to keyword search / offline suggestions.

Copy .env.example → .env for Groq or model cache config. Never commit credentials.

Run
Web UI (loopback only)

bash
python -m filememory.web
Open http://127.0.0.1:8765/. Add folders, search, open/forget files, manage settings (AI mode: No AI default / Local AI / Groq), rebuild index. Forget never deletes real files.

Desktop (Windows, native WebView2)

powershell
python -m pip install -r requirements-packaging.lock
.\.venv\Scripts\python.exe -m filememory.desktop
Tray: Show/Hide dashboard, Pause/Resume tracking, Exit. Hiding keeps API + watcher running; only Exit stops them. Add --minimized to launch hidden to tray after setup.

Python API
python
from filememory.service import FileMemoryService

service = FileMemoryService()
service.add_folder("/home/me/Documents")
service.index_path("/home/me/Documents/plan.txt", note="project plan")
matches = service.search("where is the project plan?", semantic=True)
get_settings() / update_settings(...)

rebuild_search_index()

forget_file / remove_folder — require confirmed=True, never delete user files

start_tracking() / stop_tracking() — watchdog events, stable files only

list_pending_suggestions() / confirm_suggestion(id, note)

API: GET /api/suggestions, POST /api/suggestions/confirm

open_file / open_folder — argument arrays, never a shell

Semantic search is independent of chat setting: tries all-MiniLM-L6-v2, falls back to SQLite keyword ranking.

Test
bash
python -m pytest -q
Offline only — temp DBs, fake embedding providers, no network. make test on Unix.

Docker
bash
docker build -t filememory-backend .
docker run --rm -p 8765:8765 -v "$PWD/data:/data" filememory-backend
DB at /data/filememory.sqlite3. Watched folders must be accessible to the container.

Windows Packaging
Windows x64 only (PyInstaller doesn't cross-compile).

powershell
.\scripts\build_windows.ps1 -Variant online -Mode both
.\scripts\validate_windows_package.ps1 -Variant online -Mode both
Installers (needs Inno Setup's ISCC.exe):

powershell
.\scripts\build_installer.ps1 -Variant online
.\scripts\build_installer.ps1 -Variant offline
Output: dist\FileMemory-Setup-online.exe / FileMemory-Setup-offline.exe. Use -SkipPackageBuild if onedir exists. Offline needs both model snapshots in %LOCALAPPDATA%\FileMemory\models (or -ModelSource); fails fast if missing.

Installer: installs to C:\Program Files\File Memory (admin), creates Start Menu + Desktop shortcuts, HKCU Startup entry (minimized to tray), optional post-install launch.

Release checklist: validate both onedir variants → compile/validate both installers → clean-machine test → online first-run test → offline semantic test → record SHA-256.

Desktop Behavior
Startup: first launch shows dashboard for setup (folder, model check, AI provider). Startup shortcut launches hidden to tray afterward. Tray: Show/Hide, Pause/Resume, Exit.

New-file flow: watcher fires (no polling) → waits for file stability, skips incomplete downloads → generates draft note (Local AI / Groq / offline fallback) → bottom-right prompt with editable note, Remember / Dismiss → auto-hides after 8s. Remember saves to SQLite; Dismiss leaves draft in suggestions.

Layout: ~1200×820, indigo/lime FM branding, split view — left: intro + folders; right: search, meaning/exact-word toggles, results, suggestions. WebView2 shell shares the same web/ code as browser fallback.

Credits: Vibecoded by Osman ♥ · with OmniRush ♥. Background update check once per day via FILE_MEMORY_UPDATE_MANIFEST_URL; failures ignored silently.
