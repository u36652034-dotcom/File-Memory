[CmdletBinding()]
param(
    [Alias("BuildVariant")]
    [ValidateSet("online", "offline")]
    [string]$Variant = "online",
    [string]$ModelSource = "",
    [switch]$SkipPackageBuild
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

if (-not $SkipPackageBuild) {
    & (Join-Path $root "scripts\build_windows.ps1") -Mode onedir -Variant $Variant -ModelSource $ModelSource
    if ($LASTEXITCODE -ne 0) { throw "Windows package build failed." }
}

& (Join-Path $root ".venv\Scripts\python.exe") (Join-Path $root "scripts\generate_installer_art.py")
if ($LASTEXITCODE -ne 0) { throw "Installer artwork generation failed." }

$installer = Join-Path $root "dist\FileMemory-Setup-$Variant.exe"
Remove-Item $installer -Force -ErrorAction SilentlyContinue
$packageRoot = Join-Path $root (Join-Path "dist\$Variant" "FileMemory")
if (-not (Test-Path (Join-Path $packageRoot "FileMemory.exe") -PathType Leaf)) {
    throw "Missing $Variant onedir package. Build it first or omit -SkipPackageBuild."
}

$iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if ($null -eq $iscc) {
    $knownPaths = @(
        (Join-Path ${env:ProgramFiles} "Inno Setup 7\ISCC.exe"),
        (Join-Path ${env:ProgramFiles} "Inno Setup 6\ISCC.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 7\ISCC.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe")
    )
    $known = $knownPaths | Where-Object { Test-Path $_ } | Select-Object -First 1
    if ($null -ne $known) {
        $iscc = @{ Source = $known }
    } else {
        throw "Inno Setup Compiler (ISCC.exe) was not found. Install Inno Setup on Windows, then rerun scripts\build_installer.ps1. No global Python install is required."
    }
}

& $iscc.Source "/DMyAppVariant=$Variant" (Join-Path $root "installer\FileMemory.iss")
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed with exit code $LASTEXITCODE." }
& (Join-Path $root "scripts\validate_windows_package.ps1") -Variant $Variant -Mode onedir -RequireInstaller
