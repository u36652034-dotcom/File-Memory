# PyInstaller spec for Windows x64 File Memory artifacts.
# Build with scripts/build_windows.ps1, which sets FILE_MEMORY_BUILD_MODE.

from pathlib import Path
import os
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


ROOT = Path(SPECPATH).resolve().parent
MODE = os.environ.get("FILE_MEMORY_BUILD_MODE", "onedir").lower()
if MODE not in {"onedir", "onefile"}:
    raise SystemExit(f"Unsupported FILE_MEMORY_BUILD_MODE: {MODE}")

sys.path.insert(0, str(ROOT))
if not (ROOT / "filememory" / "desktop.py").is_file():
    raise SystemExit("Native entrypoint filememory/desktop.py is missing.")
entrypoint = ROOT / "packaging" / "desktop_entrypoint.py"


def collect_model_cache(source: Path):
    """Return PyInstaller data entries for a staged offline model cache."""
    if not source.is_dir():
        raise SystemExit(f"Offline model cache is missing: {source}")
    files = sorted(path for path in source.rglob("*") if path.is_file())
    if not files:
        raise SystemExit(f"Offline model cache is empty: {source}")
    return [(str(path), str(Path("models") / path.relative_to(source).parent)) for path in files]

datas = [
    (str(ROOT / "web"), "web"),
    (str(ROOT / "scripts" / "prepare_models.py"), "tools/scripts"),
    (str(ROOT / "scripts" / "prepare_models_windows.ps1"), "tools/scripts"),
    (str(ROOT / "requirements-models.lock"), "tools"),
    (str(ROOT / "requirements-models.txt"), "tools"),
    (str(ROOT / "assets" / "filememory.ico"), "assets"),
    (str(ROOT / ".env.example"), "."),
]
model_source = os.environ.get("FILE_MEMORY_MODEL_SOURCE")
if model_source:
    # build_windows.ps1 stages %LOCALAPPDATA%\FileMemory\models in the
    # project-local build tree before invoking PyInstaller.
    source = Path(model_source).resolve()
    required_caches = (
        "models--sentence-transformers--all-MiniLM-L6-v2",
        "models--HuggingFaceTB--SmolLM2-360M-Instruct",
    )
    for cache_name in required_caches:
        snapshot_dir = source / cache_name / "snapshots"
        if not snapshot_dir.is_dir() or not any(snapshot_dir.rglob("*")):
            raise SystemExit(f"Offline model cache has no snapshot files for {cache_name}: {source}")
    datas += collect_model_cache(source)
# Supply clean Python sources for the optional, separate project-local model
# downloader. Never collect developer caches, databases, secrets, or models.
datas += [(str(path), "tools/filememory") for path in sorted((ROOT / "filememory").glob("*.py"))]

hiddenimports = collect_submodules("filememory")
try:
    hiddenimports += collect_submodules("watchdog")
except ImportError:
    # Runtime dependencies are installed by the normal build path. This
    # fallback keeps the spec importable for static inspection.
    pass
try:
    hiddenimports += collect_submodules("webview")
    datas += collect_data_files("webview")
except ImportError:
    # Runtime packaging installs pywebview from requirements-packaging.lock.
    # This fallback keeps static spec inspection possible on a non-Windows host.
    pass
try:
    hiddenimports += collect_submodules("pystray")
except ImportError:
    # Runtime packaging installs pystray from requirements-packaging.lock.
    pass

with_models = os.environ.get("FILE_MEMORY_INCLUDE_MODELS") == "1"
excludes = [] if with_models else [
    "sentence_transformers", "sentence_transformers.*",
    "transformers", "transformers.*",
    "torch", "torch.*", "sklearn", "sklearn.*", "scipy", "scipy.*", "numpy", "numpy.*",
]

analysis = Analysis(
    [str(entrypoint)],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(analysis.pure)
name = "FileMemory" if MODE == "onedir" else "FileMemory-onefile"
exe = EXE(
    pyz,
    analysis.scripts,
    *( [[], []] if MODE == "onedir" else [analysis.binaries, analysis.datas] ),
    [],
    name=name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    contents_directory=".",
    icon=str(ROOT / "assets" / "filememory.ico"),
    exclude_binaries=MODE == "onedir",
)

if MODE == "onedir":
    coll = COLLECT(
        exe,
        analysis.binaries,
        analysis.datas,
        strip=False,
        upx=False,
        name=name,
    )
