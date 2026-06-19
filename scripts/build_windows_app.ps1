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
    "--name", "Setpiece",
    "--icon", "setpiece\assets\brand\app\setpiece_app_icon.ico",
    "--version-file", "scripts\setpiece_version_info.txt",
    "--collect-submodules", "setpiece.actions",
    "--collect-submodules", "setpiece.adapters",
    "--collect-submodules", "setpiece.agent",
    "--collect-submodules", "setpiece.canvas",
    "--collect-submodules", "setpiece.home",
    "--collect-submodules", "setpiece.ui",
    "--hidden-import", "setpiece.home.confirmation",
    "--collect-data", "setpiece.agent.qml",
    "--collect-data", "setpiece.assets",
    "--collect-data", "setpiece.canvas.qml",
    "--collect-data", "setpiece.sample_canvases",
    "--collect-data", "setpiece.home.qml",
    "--collect-data", "setpiece.sample_recipes",
    "--add-data", "themes;themes",
    "setpiece\desktop_entry.py"
)

if (-not $NoClean) {
    $pyinstallerArgs = @("--clean") + $pyinstallerArgs
}

python -m PyInstaller @pyinstallerArgs
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

Write-Host "Built dist\Setpiece\Setpiece.exe"
