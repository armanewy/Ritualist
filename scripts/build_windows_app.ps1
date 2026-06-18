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
    "--collect-submodules", "ritualist.agent",
    "--collect-submodules", "ritualist.canvas",
    "--collect-submodules", "ritualist.home",
    "--collect-submodules", "ritualist.ui",
    "--hidden-import", "ritualist.home.confirmation",
    "--collect-data", "ritualist.canvas.qml",
    "--collect-data", "ritualist.sample_canvases",
    "--collect-data", "ritualist.home.qml",
    "--collect-data", "ritualist.sample_recipes",
    "--add-data", "themes;themes",
    "ritualist\desktop_entry.py"
)

if (-not $NoClean) {
    $pyinstallerArgs = @("--clean") + $pyinstallerArgs
}

python -m PyInstaller @pyinstallerArgs
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

Write-Host "Built dist\Ritualist\Ritualist.exe"
