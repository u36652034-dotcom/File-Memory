[CmdletBinding()]
param([string]$ModelDir = (Join-Path $env:LOCALAPPDATA "FileMemory\models"))

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    & py -3.12 -m venv (Join-Path $root ".venv")
    if ($LASTEXITCODE -ne 0) { throw "Could not create a project-local Python 3.12 environment." }
}
& $python -m pip install --disable-pip-version-check -r (Join-Path $root "requirements-models.lock")
if ($LASTEXITCODE -ne 0) { throw "Could not install optional model dependencies into .venv." }
$oldModelDir = $env:FILE_MEMORY_MODEL_DIR
try {
    $env:FILE_MEMORY_MODEL_DIR = [System.IO.Path]::GetFullPath($ModelDir)
    & $python (Join-Path $root "scripts\prepare_models.py")
    if ($LASTEXITCODE -ne 0) { throw "Model download failed; retry with network access." }
} finally {
    $env:FILE_MEMORY_MODEL_DIR = $oldModelDir
}
