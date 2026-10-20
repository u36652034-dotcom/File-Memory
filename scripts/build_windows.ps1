[CmdletBinding()]
param(
    [ValidateSet("onedir", "onefile", "both")]
    [string]$Mode = "both",
    [Alias("BuildVariant")]
    [ValidateSet("online", "offline")]
    [string]$Variant = "online",
    [string]$ModelSource = "",
    [switch]$SkipRuntimeDependencies,
    # Retained for command-line compatibility. Both variants include the
    # model runtime; only offline includes model weights.
    [switch]$IncludeModelRuntime
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

if (-not $IsWindows -and $env:OS -ne "Windows_NT") {
    throw "Windows x64 packaging must run on Windows. Use a Windows x64 Python environment; PyInstaller does not cross-compile Windows executables."
}

$venvPython = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($null -eq $py) {
        throw "Project .venv is missing and the Windows py launcher was not found. Create it with: py -3.12 -m venv .venv"
    }
    & $py.Source -3.12 -m venv (Join-Path $root ".venv")
    if ($LASTEXITCODE -ne 0) { throw "Could not create the project .venv with Python 3.12." }
}

function Invoke-ProjectPython {
    param([string[]]$Arguments)
    & $venvPython @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Project Python command failed ($LASTEXITCODE): $($Arguments -join ' ')"
    }
}

if (-not $SkipRuntimeDependencies) {
    Invoke-ProjectPython @("-m", "pip", "install", "--disable-pip-version-check", "-r", (Join-Path $root "requirements.lock"))
}

& $venvPython -c "import platform, struct, sys; assert sys.version_info[:2] == (3, 12), 'Build requires Python 3.12'; assert sys.platform == 'win32' and struct.calcsize('P') == 8 and platform.machine().upper() in ('AMD64', 'X86_64'), 'Build requires Windows x64 Python'"
if ($LASTEXITCODE -ne 0) { throw "Python 3.12 Windows x64 is required for this package. Recreate .venv with: py -3.12 -m venv .venv" }
if (-not (Test-Path (Join-Path $root "filememory\desktop.py"))) { throw "Native entrypoint filememory\desktop.py is missing." }

Invoke-ProjectPython @("-m", "pip", "install", "--disable-pip-version-check", "-r", (Join-Path $root "requirements-packaging.lock"))
Invoke-ProjectPython @("-c", "import webview; print('pywebview ' + getattr(webview, '__version__', 'unknown') + ' ready for WebView2 packaging')")
Invoke-ProjectPython @("-m", "pip", "install", "--disable-pip-version-check", "-r", (Join-Path $root "requirements-models.lock"))

Invoke-ProjectPython @("scripts\generate_icon.py")

$modes = if ($Mode -eq "both") { @("onedir", "onefile") } else { @($Mode) }
$distRoot = Join-Path $root (Join-Path "dist" $Variant)
New-Item -ItemType Directory -Force -Path $distRoot | Out-Null
if ($Mode -in @("onedir", "both")) { Remove-Item (Join-Path $distRoot "FileMemory") -Recurse -Force -ErrorAction SilentlyContinue }
if ($Mode -in @("onefile", "both")) { Remove-Item (Join-Path $distRoot "FileMemory-onefile.exe") -Force -ErrorAction SilentlyContinue }

$modelStage = Join-Path $root "build\model-cache\$Variant"
Remove-Item $modelStage -Recurse -Force -ErrorAction SilentlyContinue
if ($Variant -eq "offline") {
    if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) { throw "LOCALAPPDATA is not set; offline builds require %LOCALAPPDATA%\FileMemory\models." }
    if ([string]::IsNullOrWhiteSpace($ModelSource)) { $ModelSource = Join-Path $env:LOCALAPPDATA "FileMemory\models" }
    $modelSource = [System.IO.Path]::GetFullPath($ModelSource)
    if (-not (Test-Path $modelSource -PathType Container)) { throw "Offline model cache is missing: $modelSource. Run scripts\prepare_models_windows.ps1 first." }
    foreach ($modelName in @(
        "models--sentence-transformers--all-MiniLM-L6-v2",
        "models--HuggingFaceTB--SmolLM2-360M-Instruct"
    )) {
        $modelRoot = Join-Path $modelSource $modelName
        if (-not (Test-Path $modelRoot -PathType Container)) { throw "Offline model cache is missing $modelName under $modelSource." }
        $snapshotFiles = @(Get-ChildItem -LiteralPath (Join-Path $modelRoot "snapshots") -File -Recurse -Force -ErrorAction SilentlyContinue)
        if ($snapshotFiles.Count -eq 0) { throw "Offline model cache has no snapshot files for $modelName under $modelSource." }
    }
    New-Item -ItemType Directory -Force -Path $modelStage | Out-Null
    foreach ($item in @(Get-ChildItem -LiteralPath $modelSource -Force)) { Copy-Item -LiteralPath $item.FullName -Destination (Join-Path $modelStage $item.Name) -Recurse -Force }
    $env:FILE_MEMORY_MODEL_SOURCE = $modelStage
} else { Remove-Item Env:FILE_MEMORY_MODEL_SOURCE -ErrorAction SilentlyContinue }

try {
  foreach ($currentMode in $modes) {
    $env:FILE_MEMORY_BUILD_MODE = $currentMode
    $env:FILE_MEMORY_INCLUDE_MODELS = "1"
    Write-Host "Building Windows x64 $Variant $currentMode artifact..."
    Invoke-ProjectPython @(
        "-m", "PyInstaller", "--clean", "--noconfirm",
        "--distpath", $distRoot,
        "--workpath", (Join-Path $root "build\pyinstaller-$Variant-$currentMode"),
        (Join-Path $root "packaging\filememory.spec")
    )
  }
} finally {
  Remove-Item Env:FILE_MEMORY_BUILD_MODE -ErrorAction SilentlyContinue
  Remove-Item Env:FILE_MEMORY_INCLUDE_MODELS -ErrorAction SilentlyContinue
  Remove-Item Env:FILE_MEMORY_MODEL_SOURCE -ErrorAction SilentlyContinue
  Remove-Item $modelStage -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "Artifacts are under $distRoot"
Write-Host "Validate with: .\scripts\validate_windows_package.ps1 -Variant $Variant -Mode $Mode"
