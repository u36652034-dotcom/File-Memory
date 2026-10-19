[CmdletBinding()]
param([switch]$SkipPackageBuild)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

if (-not $SkipPackageBuild) {
    & (Join-Path $root "scripts\build_windows.ps1") -Mode onedir -IncludeModelRuntime
    if ($LASTEXITCODE -ne 0) { throw "Windows package build failed." }
}

$iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if ($null -eq $iscc) {
    throw "Inno Setup Compiler (ISCC.exe) was not found. Install Inno Setup on Windows, then rerun scripts\build_installer.ps1. No global Python install is required."
}

& $iscc.Source (Join-Path $root "installer\FileMemory.iss")
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed with exit code $LASTEXITCODE." }
& (Join-Path $root "scripts\validate_windows_package.ps1") -Mode onedir -RequireInstaller
