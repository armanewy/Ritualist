param(
    [switch]$NoClean
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$pyinstallerArgs = @(
    "--noconfirm",
    "--onedir",
    "--windowed",
    "--name", "Ritualist",
    "--collect-submodules", "ritualist.actions",
    "--collect-submodules", "ritualist.adapters",
    "--collect-submodules", "ritualist.ui",
    "--collect-data", "ritualist.sample_recipes",
    "--copy-metadata", "ritualist",
    "ritualist\desktop_entry.py"
)

if (-not $NoClean) {
    $pyinstallerArgs = @("--clean") + $pyinstallerArgs
}

python -m PyInstaller @pyinstallerArgs

Write-Host "Built dist\Ritualist\Ritualist.exe"
