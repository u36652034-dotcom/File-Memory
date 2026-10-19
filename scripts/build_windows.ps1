[CmdletBinding()]
param(
    [ValidateSet("onedir", "onefile", "both")]
    [string]$Mode = "both",
    [switch]$SkipRuntimeDependencies,
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

& $venvPython -c "import platform, struct, sys; assert sys.platform == 'win32' and struct.calcsize('P') == 8 and platform.machine().upper() in ('AMD64', 'X86_64'), 'Build requires Windows x64 Python'"
if ($LASTEXITCODE -ne 0) { throw "Windows x64 Python is required for this package." }
if (-not (Test-Path (Join-Path $root "filememory\desktop.py"))) { throw "Native entrypoint filememory\desktop.py is missing." }

Invoke-ProjectPython @("-m", "pip", "install", "--disable-pip-version-check", "-r", (Join-Path $root "requirements-packaging.lock"))
Invoke-ProjectPython @("-c", "import webview; print('pywebview ' + getattr(webview, '__version__', 'unknown') + ' ready for WebView2 packaging')")
if ($IncludeModelRuntime) {
    Invoke-ProjectPython @("-m", "pip", "install", "--disable-pip-version-check", "-r", (Join-Path $root "requirements-models.lock"))
}

Invoke-ProjectPython @("scripts\generate_icon.py")

$modes = if ($Mode -eq "both") { @("onedir", "onefile") } else { @($Mode) }
foreach ($currentMode in $modes) {
    $env:FILE_MEMORY_BUILD_MODE = $currentMode
    $env:FILE_MEMORY_INCLUDE_MODELS = if ($IncludeModelRuntime) { "1" } else { "0" }
    Write-Host "Building Windows x64 $currentMode artifact..."
    Invoke-ProjectPython @(
        "-m", "PyInstaller", "--clean", "--noconfirm",
        "--distpath", (Join-Path $root "dist"),
        "--workpath", (Join-Path $root "build\pyinstaller-$currentMode"),
        (Join-Path $root "packaging\filememory.spec")
    )
}
Remove-Item Env:FILE_MEMORY_BUILD_MODE -ErrorAction SilentlyContinue
Remove-Item Env:FILE_MEMORY_INCLUDE_MODELS -ErrorAction SilentlyContinue

Write-Host "Artifacts are under $root\dist"
Write-Host "Validate with: .\scripts\validate_windows_package.ps1 -Mode $Mode"
