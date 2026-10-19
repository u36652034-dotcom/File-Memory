$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root
if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
  throw "Project environment missing. Run: py -3.12 -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements.lock; .\.venv\Scripts\python.exe -m pip install -r requirements-packaging.lock"
}
& ".\.venv\Scripts\python.exe" -m filememory.desktop @args
