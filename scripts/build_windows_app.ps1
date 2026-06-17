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
    "--collect-submodules", "ritualist.canvas",
    "--collect-submodules", "ritualist.home",
    "--collect-submodules", "ritualist.ui",
    "--hidden-import", "ritualist.home.confirmation",
    "--collect-data", "ritualist.canvas.qml",
    "--collect-data", "ritualist.sample_canvases",
    "--collect-data", "ritualist.home.qml",
    "--collect-data", "ritualist.sample_recipes",
    "--add-data", "themes;themes",
    "--copy-metadata", "ritualist",
    "ritualist\desktop_entry.py"
)

if (-not $NoClean) {
    $pyinstallerArgs = @("--clean") + $pyinstallerArgs
}

python -m PyInstaller @pyinstallerArgs

Write-Host "Built dist\Ritualist\Ritualist.exe"
