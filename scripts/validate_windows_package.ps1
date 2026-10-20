[CmdletBinding()]
param(
    [ValidateSet("onedir", "onefile", "both")]
    [string]$Mode = "both",
    [switch]$RequireInstaller,
    [switch]$SmokeTest
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$dist = Join-Path $root "dist"

function Assert-Artifact {
    param([string]$Path, [switch]$AllowInstallerBootstrapper)
    if (-not (Test-Path $Path -PathType Leaf)) { throw "Missing artifact: $Path" }
    $bytes = [System.IO.File]::ReadAllBytes($Path)
    if ($bytes.Length -lt 64 -or $bytes[0] -ne 0x4D -or $bytes[1] -ne 0x5A) {
        throw "Not a Windows PE executable: $Path"
    }
    $peOffset = [BitConverter]::ToInt32($bytes, 0x3C)
    if ($peOffset -lt 0 -or $peOffset + 6 -gt $bytes.Length) { throw "Invalid PE header: $Path" }
    $signature = [Text.Encoding]::ASCII.GetString($bytes, $peOffset, 4)
    if ($signature -ne "PE`0`0") { throw "Invalid PE signature: $Path" }
    $machine = [BitConverter]::ToUInt16($bytes, $peOffset + 4)
    if ($machine -ne 0x8664 -and -not ($AllowInstallerBootstrapper -and $machine -eq 0x014C)) {
        throw "Expected x64 PE (0x8664), found 0x$('{0:X4}' -f $machine): $Path"
    }
    Write-Host "Validated x64 PE: $Path"
}

function Invoke-SmokeTest {
    param([string]$Executable, [string]$WorkingDirectory)
    $result = Join-Path $env:TEMP ("filememory-package-check-" + [guid]::NewGuid().ToString("N") + ".json")
    try {
        $process = Start-Process -FilePath $Executable -WorkingDirectory $WorkingDirectory -ArgumentList @("--package-check", $result) -PassThru -Wait -WindowStyle Hidden
        if ($process.ExitCode -ne 0) { throw "Package smoke test failed with exit code $($process.ExitCode): $Executable" }
        if (-not (Test-Path $result -PathType Leaf)) { throw "Package smoke test did not write its receipt: $Executable" }
        $receipt = Get-Content $result -Raw | ConvertFrom-Json
        if (-not $receipt.ok) { throw "Package smoke test returned an unsuccessful receipt: $Executable" }
        Write-Host "Smoke test passed: $Executable"
    } finally {
        Remove-Item $result -Force -ErrorAction SilentlyContinue
    }
}

if (-not (Test-Path (Join-Path $root "assets\filememory.ico") -PathType Leaf)) {
    throw "Generated icon is missing. Run scripts\build_windows.ps1 first."
}
$iconHeader = [System.IO.File]::ReadAllBytes((Join-Path $root "assets\filememory.ico"))
if ($iconHeader.Length -lt 6 -or $iconHeader[0] -ne 0 -or $iconHeader[1] -ne 0 -or $iconHeader[2] -ne 1) {
    throw "Generated icon is not a Windows ICO file."
}

if ($Mode -in @("onedir", "both")) {
    $onedirExe = Join-Path $dist "FileMemory\FileMemory.exe"
    Assert-Artifact $onedirExe
    foreach ($required in @("web\index.html", "web\app.js", "web\styles.css", "tools\scripts\prepare_models.py", "tools\scripts\prepare_models_windows.ps1")) {
        $path = Join-Path (Join-Path $dist "FileMemory") $required
        if (-not (Test-Path $path -PathType Leaf)) { throw "Onedir artifact is missing bundled file: $required" }
    }
    if ($SmokeTest) { Invoke-SmokeTest $onedirExe (Join-Path $dist "FileMemory") }
}
if ($Mode -in @("onefile", "both")) {
    $onefileExe = Join-Path $dist "FileMemory-onefile.exe"
    Assert-Artifact $onefileExe
    if ($SmokeTest) { Invoke-SmokeTest $onefileExe $dist }
}
if ($RequireInstaller) {
    # Inno Setup's launcher is commonly a 32-bit PE even when it installs an
    # x64 application; the packaged FileMemory.exe above is the x64 payload.
    Assert-Artifact (Join-Path $dist "FileMemory-Setup.exe") -AllowInstallerBootstrapper
}

Write-Host "File Memory Windows package validation passed."
