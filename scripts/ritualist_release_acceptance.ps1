param(
    [switch]$Packaged,
    [switch]$RecordScreen,
    [switch]$Build,
    [string]$EvidenceDir = "artifacts\release-acceptance",
    [string]$ExecutablePath = "",
    [int]$ScenarioDwellSeconds = 5
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

if ([System.IO.Path]::IsPathRooted($EvidenceDir)) {
    $AcceptanceRoot = [System.IO.Path]::GetFullPath($EvidenceDir)
}
else {
    $AcceptanceRoot = [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $EvidenceDir))
}
$EvidenceRoot = Join-Path $AcceptanceRoot "evidence"
$ScreenshotRoot = Join-Path $EvidenceRoot "screenshots"
$FrameRoot = Join-Path $EvidenceRoot "screen-frames"
$SnapshotRoot = Join-Path $EvidenceRoot "snapshots"
$CommandRoot = Join-Path $EvidenceRoot "commands"
$RunLogRoot = Join-Path $EvidenceRoot "run-logs"
$FixtureRoot = Join-Path $EvidenceRoot "fixtures"
$E2ERoot = Join-Path $EvidenceRoot "e2e-events"
$SummaryJson = Join-Path $AcceptanceRoot "acceptance-summary.json"
$SummaryMd = Join-Path $AcceptanceRoot "acceptance-summary.md"
$AcceptanceSpec = Join-Path $RepoRoot "tests\acceptance\release_v0_2_alpha_1.yaml"
$script:E2EParseErrors = @()

$resolvedRepoRoot = [System.IO.Path]::GetFullPath($RepoRoot)
$resolvedAcceptanceRoot = [System.IO.Path]::GetFullPath($AcceptanceRoot)
$resolvedArtifactsRoot = [System.IO.Path]::GetFullPath((Join-Path $RepoRoot "artifacts"))
$artifactsRootWithSeparator = $resolvedArtifactsRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
if (-not $resolvedAcceptanceRoot.StartsWith($artifactsRootWithSeparator, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Acceptance artifact root must be inside the repository artifacts directory: $resolvedAcceptanceRoot"
}
if (Test-Path $AcceptanceRoot) {
    Remove-Item -LiteralPath $AcceptanceRoot -Recurse -Force
}

New-Item -ItemType Directory -Force -Path @(
    $AcceptanceRoot,
    $EvidenceRoot,
    $ScreenshotRoot,
    $FrameRoot,
    $SnapshotRoot,
    $CommandRoot,
    $RunLogRoot,
    $FixtureRoot,
    $E2ERoot
) | Out-Null

Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;

public static class RitualistAcceptanceWin32 {
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

    [DllImport("user32.dll")]
    public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);

    [DllImport("user32.dll")]
    public static extern bool IsWindowVisible(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);

    [DllImport("user32.dll")]
    public static extern int GetWindowTextLength(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern bool MoveWindow(IntPtr hWnd, int X, int Y, int nWidth, int nHeight, bool bRepaint);

    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);

    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
}
"@

$Results = [ordered]@{}
$GeneratedProcesses = New-Object System.Collections.Generic.List[object]
$ForbiddenMarkers = @(
    "password",
    "passwd",
    "credential",
    "secret",
    "token",
    "cookie",
    "clipboard",
    "screenshot",
    "keystroke",
    "keylog",
    "page_content",
    "page_contents",
    "html",
    "dom"
)
$FakeBattleNetTitle = "Battle.net Fixture"

function Write-JsonFile {
    param([string]$Path, [object]$Value, [int]$Depth = 8)
    $Value | ConvertTo-Json -Depth $Depth | Set-Content -Path $Path -Encoding UTF8
    return $Path
}

function Set-Check {
    param(
        [string]$Id,
        [ValidateSet("PASS", "FAIL", "NEEDS_HUMAN_REVIEW")]
        [string]$Status,
        [string]$Message,
        [hashtable]$Evidence = @{}
    )
    $Results[$Id] = [ordered]@{
        id = $Id
        status = $Status
        message = $Message
        evidence = $Evidence
    }
}

function Save-Screenshot {
    param([string]$Name)
    $bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
    $bitmap = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    try {
        $graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
        $path = Join-Path $ScreenshotRoot "$Name.png"
        $bitmap.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
        return $path
    }
    finally {
        $graphics.Dispose()
        $bitmap.Dispose()
    }
}

function Test-ScreenshotNonBlank {
    param([string]$Path)
    $bitmap = [System.Drawing.Bitmap]::FromFile($Path)
    try {
        $first = $bitmap.GetPixel(0, 0).ToArgb()
        for ($x = 0; $x -lt $bitmap.Width; $x += [Math]::Max(1, [int]($bitmap.Width / 20))) {
            for ($y = 0; $y -lt $bitmap.Height; $y += [Math]::Max(1, [int]($bitmap.Height / 20))) {
                if ($bitmap.GetPixel($x, $y).ToArgb() -ne $first) {
                    return $true
                }
            }
        }
        return $false
    }
    finally {
        $bitmap.Dispose()
    }
}

function Capture-ScreenFrames {
    param([string]$Name, [int]$Seconds = 3, [int]$IntervalMilliseconds = 500)
    if (-not $RecordScreen) {
        return $null
    }
    $dir = Join-Path $FrameRoot $Name
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $frames = @()
    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $index = 0
    while ($stopwatch.Elapsed.TotalSeconds -lt $Seconds) {
        $source = Save-Screenshot "$Name-frame-$index"
        $dest = Join-Path $dir ("frame-{0:D4}.png" -f $index)
        Move-Item -Path $source -Destination $dest -Force
        $frames += [ordered]@{
            index = $index
            elapsed_ms = [Math]::Round($stopwatch.Elapsed.TotalMilliseconds, 1)
            path = $dest
        }
        Start-Sleep -Milliseconds $IntervalMilliseconds
        $index += 1
    }
    $manifest = Join-Path $dir "recording-manifest.json"
    Write-JsonFile $manifest ([ordered]@{
        schema = "ritualist.acceptance.frame_recording.v1"
        name = $Name
        frames = $frames
        encoded_video = $null
        note = "Frame sequence captured because no bundled video encoder is required."
    }) 8 | Out-Null
    return [ordered]@{ manifest = $manifest; frame_count = $frames.Count; directory = $dir }
}

function Get-TopLevelWindows {
    $handles = New-Object System.Collections.Generic.List[System.IntPtr]
    $callback = [RitualistAcceptanceWin32+EnumWindowsProc]{
        param([System.IntPtr]$hWnd, [System.IntPtr]$lParam)
        if ([RitualistAcceptanceWin32]::IsWindowVisible($hWnd)) {
            $handles.Add($hWnd)
        }
        return $true
    }
    [RitualistAcceptanceWin32]::EnumWindows($callback, [System.IntPtr]::Zero) | Out-Null
    $foreground = [RitualistAcceptanceWin32]::GetForegroundWindow()
    $rows = @()
    $index = 0
    foreach ($handle in $handles) {
        $length = [RitualistAcceptanceWin32]::GetWindowTextLength($handle)
        $builder = New-Object System.Text.StringBuilder ([Math]::Max(1, $length + 1))
        [RitualistAcceptanceWin32]::GetWindowText($handle, $builder, $builder.Capacity) | Out-Null
        $title = $builder.ToString()
        if ([string]::IsNullOrWhiteSpace($title)) {
            continue
        }
        [uint32]$processId = 0
        [RitualistAcceptanceWin32]::GetWindowThreadProcessId($handle, [ref]$processId) | Out-Null
        $rows += [ordered]@{
            z_index = $index
            hwnd = $handle.ToInt64()
            title = $title
            process_id = [int64]$processId
            is_foreground = ($handle -eq $foreground)
        }
        $index += 1
    }
    return $rows
}

function Save-ZOrderSnapshot {
    param([string]$Name)
    $path = Join-Path $SnapshotRoot "$Name-z-order.json"
    Write-JsonFile $path (Get-TopLevelWindows) 6 | Out-Null
    return $path
}

function Get-WindowByName {
    param([string]$Name, [int]$TimeoutSeconds = 15)
    $root = [System.Windows.Automation.AutomationElement]::RootElement
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $condition = New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::NameProperty,
            $Name
        )
        $window = $root.FindFirst([System.Windows.Automation.TreeScope]::Children, $condition)
        if ($window) {
            return $window
        }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $deadline)
    return $null
}

function Find-Button {
    param([object]$Window, [string]$Name)
    $nameCondition = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::NameProperty,
        $Name
    )
    $typeCondition = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
        [System.Windows.Automation.ControlType]::Button
    )
    $condition = New-Object System.Windows.Automation.AndCondition($nameCondition, $typeCondition)
    return $Window.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condition)
}

function Invoke-NamedButton {
    param([object]$Window, [string]$Name, [int]$TimeoutSeconds = 15)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $button = Find-Button $Window $Name
        if ($button -and $button.Current.IsEnabled) {
            $pattern = $button.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
            $pattern.Invoke()
            return $true
        }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $deadline)
    return $false
}

function Save-WindowTree {
    param([string]$Name, [object]$Window, [int]$Limit = 250)
    $items = @()
    if ($Window) {
        $all = $Window.FindAll(
            [System.Windows.Automation.TreeScope]::Descendants,
            [System.Windows.Automation.Condition]::TrueCondition
        )
        for ($i = 0; $i -lt [Math]::Min($all.Count, $Limit); $i++) {
            $element = $all.Item($i)
            $items += [ordered]@{
                name = $element.Current.Name
                control_type = $element.Current.ControlType.ProgrammaticName
                automation_id = $element.Current.AutomationId
                enabled = $element.Current.IsEnabled
            }
        }
    }
    $path = Join-Path $SnapshotRoot "$Name-window-tree.json"
    Write-JsonFile $path $items 6 | Out-Null
    return $path
}

function Save-ProcessTree {
    param([string]$Name, [int]$RootProcessId)
    $all = Get-CimInstance Win32_Process
    $ids = New-Object System.Collections.Generic.HashSet[int]
    [void]$ids.Add($RootProcessId)
    $changed = $true
    while ($changed) {
        $changed = $false
        foreach ($process in $all) {
            if ($ids.Contains([int]$process.ParentProcessId) -and -not $ids.Contains([int]$process.ProcessId)) {
                [void]$ids.Add([int]$process.ProcessId)
                $changed = $true
            }
        }
    }
    $rows = foreach ($process in $all) {
        if ($ids.Contains([int]$process.ProcessId)) {
            [ordered]@{
                process_id = [int]$process.ProcessId
                parent_process_id = [int]$process.ParentProcessId
                name = $process.Name
                command_line = $process.CommandLine
            }
        }
    }
    $path = Join-Path $SnapshotRoot "$Name-process-tree.json"
    Write-JsonFile $path @($rows) 6 | Out-Null
    return $path
}

function Start-AcceptanceProcess {
    param([string]$FilePath, [string[]]$Arguments = @())
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $FilePath
    foreach ($argument in $Arguments) {
        [void]$startInfo.ArgumentList.Add($argument)
    }
    $startInfo.UseShellExecute = $false
    $startInfo.EnvironmentVariables["RITUALIST_E2E"] = "1"
    $startInfo.EnvironmentVariables["RITUALIST_E2E_ARTIFACT_DIR"] = $E2ERoot
    $startInfo.EnvironmentVariables["RITUALIST_E2E_APP_DATA_DIR"] = $script:FixtureAppData
    $startInfo.EnvironmentVariables["LOCALAPPDATA"] = $script:FixtureLocalAppData
    $process = [System.Diagnostics.Process]::Start($startInfo)
    $GeneratedProcesses.Add($process) | Out-Null
    return $process
}

function Stop-AcceptanceProcess {
    param([object]$Process, [switch]$Force)
    if (-not $Process -or $Process.HasExited) {
        return
    }
    if (-not $Force) {
        try {
            [void]$Process.CloseMainWindow()
            Start-Sleep -Seconds 2
        }
        catch {
        }
    }
    if (-not $Process.HasExited) {
        Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
    }
}

function Stop-FakeExternalApps {
    $fakeScript = Join-Path $FixtureRoot "fake-battlenet.ps1"
    $windows = @(Get-TopLevelWindows | Where-Object { $_.title -eq $FakeBattleNetTitle })
    foreach ($window in $windows) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId = $($window.process_id)" -ErrorAction SilentlyContinue
        if ($process -and $process.CommandLine -and $process.CommandLine.Contains($fakeScript)) {
            Stop-Process -Id ([int]$window.process_id) -Force -ErrorAction SilentlyContinue
        }
    }
}

function Start-FakeExternalApp {
    Stop-FakeExternalApps
    $fakeScript = Join-Path $FixtureRoot "fake-battlenet.ps1"
    $process = Start-AcceptanceProcess "powershell.exe" @(
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-STA",
        "-File",
        $fakeScript
    )
    [void](Get-WindowByName $FakeBattleNetTitle 20)
    return $process
}

function Invoke-CapturedCommand {
    param(
        [string]$Name,
        [string]$FilePath,
        [string[]]$Arguments = @(),
        [hashtable]$ExtraEnv = @{}
    )
    $stdout = Join-Path $CommandRoot "$Name.stdout.txt"
    $stderr = Join-Path $CommandRoot "$Name.stderr.txt"
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $FilePath
    foreach ($argument in $Arguments) {
        [void]$startInfo.ArgumentList.Add($argument)
    }
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.EnvironmentVariables["RITUALIST_E2E"] = "1"
    $startInfo.EnvironmentVariables["RITUALIST_E2E_ARTIFACT_DIR"] = $E2ERoot
    $startInfo.EnvironmentVariables["RITUALIST_E2E_APP_DATA_DIR"] = $script:FixtureAppData
    $startInfo.EnvironmentVariables["LOCALAPPDATA"] = $script:FixtureLocalAppData
    foreach ($key in $ExtraEnv.Keys) {
        $startInfo.EnvironmentVariables[$key] = [string]$ExtraEnv[$key]
    }
    $process = [System.Diagnostics.Process]::Start($startInfo)
    $outText = $process.StandardOutput.ReadToEnd()
    $errText = $process.StandardError.ReadToEnd()
    $process.WaitForExit()
    $outText | Set-Content -Path $stdout -Encoding UTF8
    $errText | Set-Content -Path $stderr -Encoding UTF8
    return [ordered]@{
        exit_code = $process.ExitCode
        stdout = $stdout
        stderr = $stderr
        stdout_text = $outText
        stderr_text = $errText
    }
}

function Get-LatestRun {
    param([string]$Prefix = "gaming_mode")
    $runs = Join-Path $script:FixtureAppData "runs"
    if (-not (Test-Path $runs)) {
        return $null
    }
    return Get-ChildItem -Path $runs -Directory |
        Where-Object { $_.Name -like "*_$Prefix" } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
}

function Copy-RunLogEvidence {
    param([string]$RunId)
    if (-not $RunId) {
        return $null
    }
    $source = Join-Path (Join-Path $script:FixtureAppData "runs") $RunId
    $destination = Join-Path $RunLogRoot $RunId
    if (Test-Path $destination) {
        Remove-Item -Recurse -Force -Path $destination
    }
    Copy-Item -Recurse -Force -Path $source -Destination $destination
    return $destination
}

function Read-RunJson {
    param([string]$RunId)
    $path = Join-Path (Join-Path (Join-Path $script:FixtureAppData "runs") $RunId) "run.json"
    if (-not (Test-Path $path)) {
        return $null
    }
    return Get-Content -Path $path -Raw | ConvertFrom-Json
}

function Get-E2EEvents {
    if (-not (Test-Path $E2ERoot)) {
        return @()
    }
    $events = @()
    $parseErrors = @()
    foreach ($file in Get-ChildItem -Path $E2ERoot -Filter "*.jsonl" -ErrorAction SilentlyContinue) {
        $lineNumber = 0
        foreach ($line in Get-Content -Path $file) {
            $lineNumber += 1
            if ($line.Trim()) {
                try {
                    $events += ($line | ConvertFrom-Json -ErrorAction Stop)
                }
                catch {
                    $previewLength = [Math]::Min(240, $line.Length)
                    $parseErrors += [pscustomobject]@{
                        file = $file.FullName
                        line = $lineNumber
                        error = $_.Exception.Message
                        preview = $line.Substring(0, $previewLength)
                    }
                }
            }
        }
    }
    $script:E2EParseErrors = $parseErrors
    return $events
}

function Test-E2EEvent {
    param([string]$EventName)
    return [bool](Get-E2EEvents | Where-Object { $_.event -eq $EventName } | Select-Object -First 1)
}

function Get-CanvasThemeEvidence {
    param($Events)
    $ready = @(
        $Events |
            Where-Object { $_.event -eq "canvas.ready" } |
            ForEach-Object {
                [pscustomobject]@{
                    canvas = $_.payload.canvas
                    mock = $_.payload.mock
                    theme_id = $_.payload.theme_id
                    theme_valid = $_.payload.theme_valid
                    theme_source = $_.payload.theme_source
                }
            }
    )
    return [ordered]@{
        canvas_ready = $ready
        selected_theme_ids = @($ready | ForEach-Object { $_.theme_id } | Where-Object { $_ } | Select-Object -Unique)
        invalid_theme_events = @($ready | Where-Object { $_.theme_valid -eq $false })
    }
}

function Get-CanvasStatusEvents {
    param([string]$ComponentId = "")
    $events = Get-E2EEvents | Where-Object { $_.event -eq "canvas.status" }
    if ($ComponentId) {
        $events = $events | Where-Object { $_.payload.component_id -eq $ComponentId }
    }
    return @($events)
}

function Get-RuntimeEventsForRun {
    param([string]$RunId)
    if (-not $RunId) {
        return @()
    }
    return @(
        Get-E2EEvents |
            Where-Object {
                $_.event -eq "runtime.event" -and
                $_.payload.runtime_event -and
                $_.payload.runtime_event.run_id -eq $RunId
            }
    )
}

function Test-WindowTreeContainsText {
    param([string]$Path, [string]$Text)
    if (-not (Test-Path $Path)) {
        return $false
    }
    $items = Get-Content -Path $Path -Raw | ConvertFrom-Json
    return [bool]($items | Where-Object { $_.name -match [regex]::Escape($Text) } | Select-Object -First 1)
}

function New-Fixtures {
    $script:FixtureLocalAppData = Join-Path $FixtureRoot "LOCALAPPDATA"
    $script:FixtureAppData = Join-Path $script:FixtureLocalAppData "Ritualist\Ritualist"
    $recipes = Join-Path $script:FixtureAppData "recipes"
    $themes = Join-Path $script:FixtureAppData "themes"
    $canvases = Join-Path $script:FixtureAppData "canvases"
    New-Item -ItemType Directory -Force -Path @($recipes, $themes, $canvases) | Out-Null

    $fakeApp = Join-Path $FixtureRoot "fake-battlenet.ps1"
    @'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$form = New-Object System.Windows.Forms.Form
$form.Text = "Battle.net Fixture"
$form.Width = 1000
$form.Height = 720
$form.StartPosition = "CenterScreen"
$form.BackColor = [System.Drawing.Color]::FromArgb(22, 24, 30)
$title = New-Object System.Windows.Forms.Label
$title.Text = "Battle.net Fixture"
$title.ForeColor = [System.Drawing.Color]::White
$title.Font = New-Object System.Drawing.Font("Segoe UI", 18, [System.Drawing.FontStyle]::Bold)
$title.AutoSize = $true
$title.Location = New-Object System.Drawing.Point(32, 28)
$diablo = New-Object System.Windows.Forms.Button
$diablo.Text = "Diablo IV"
$diablo.Width = 220
$diablo.Height = 64
$diablo.Location = New-Object System.Drawing.Point(32, 110)
$play = New-Object System.Windows.Forms.Button
$play.Text = "Play"
$play.Width = 220
$play.Height = 64
$play.Location = New-Object System.Drawing.Point(32, 210)
$status = New-Object System.Windows.Forms.Label
$status.Text = "Fixture ready; no game login or gameplay automation."
$status.ForeColor = [System.Drawing.Color]::LightGray
$status.AutoSize = $true
$status.Location = New-Object System.Drawing.Point(32, 310)
$play.Add_Click({ $status.Text = "Play was invoked." })
$form.Controls.AddRange(@($title, $diablo, $play, $status))
[System.Windows.Forms.Application]::EnableVisualStyles()
[System.Windows.Forms.Application]::Run($form)
'@ | Set-Content -Path $fakeApp -Encoding UTF8

    $recipe = @"
version: "0.1"
id: gaming_mode
name: Gaming Mode
description: Acceptance fixture for packaged release dogfood.
home:
  category: Gaming
  card:
    title: Diablo IV Night
    subtitle: Acceptance fixture
    image: ""
    accent: ""
variables:
  battle_net_window: Battle.net Fixture
steps:
  - name: Wait for Battle.net fixture
    action: window.wait
    title_contains: "{{ battle_net_window }}"
    timeout_seconds: 20
  - name: Control checkpoint
    action: wait.seconds
    seconds: 8
  - name: Select Diablo IV
    action: desktop.click_text
    text: Diablo IV
    window_title_contains: "{{ battle_net_window }}"
    exact: true
    timeout_seconds: 10
  - name: Ask before clicking Play
    action: desktop.click_text
    text: Play
    window_title_contains: "{{ battle_net_window }}"
    requires_confirmation: true
    timeout_seconds: 10
"@
    $recipe | Set-Content -Path (Join-Path $recipes "gaming_mode.yaml") -Encoding UTF8

    @"
schema: ritualist.canvas.v1
id: visual_acceptance
name: Visual Acceptance
mode: desktop_canvas
components:
  - id: title
    type: text.label
    width: 320
    height: 80
    props:
      text: Visual only
"@ | Set-Content -Path (Join-Path $canvases "visual_acceptance.yaml") -Encoding UTF8

    @"
id: minimal_theme
name: Minimal Theme
"@ | Set-Content -Path (Join-Path $themes "minimal_theme.yaml") -Encoding UTF8
}

function Resolve-RitualistExe {
    if ($ExecutablePath) {
        return (Resolve-Path $ExecutablePath).Path
    }
    $candidate = Join-Path $RepoRoot "dist\Ritualist\Ritualist.exe"
    if ($Build -or -not (Test-Path $candidate)) {
        & (Join-Path $RepoRoot "scripts\build_windows_app.ps1")
    }
    if (-not (Test-Path $candidate)) {
        throw "Packaged executable not found: $candidate"
    }
    return $candidate
}

function Assert-LaunchWindow {
    param(
        [string]$Id,
        [string]$Title,
        [string[]]$LaunchArguments = @(),
        [string]$ScreenshotName
    )
    $process = Start-AcceptanceProcess -FilePath $script:RitualistExe -Arguments $LaunchArguments
    try {
        Start-Sleep -Seconds $ScenarioDwellSeconds
        $window = Get-WindowByName $Title 10
        $screenshot = Save-Screenshot $ScreenshotName
        $frames = Capture-ScreenFrames $ScreenshotName 2
        $processTree = Save-ProcessTree $ScreenshotName $process.Id
        $windowTree = Save-WindowTree $ScreenshotName $window
        $zOrder = Save-ZOrderSnapshot $ScreenshotName
        if ($window -and -not $process.HasExited -and (Test-ScreenshotNonBlank $screenshot)) {
            Set-Check $Id "PASS" "$Title opened and stayed alive." @{
                screenshot = $screenshot
                frames = $frames
                process_tree = $processTree
                window_tree = $windowTree
                z_order = $zOrder
            }
        }
        else {
            Set-Check $Id "FAIL" "$Title did not open, exited early, or screenshot was blank." @{
                screenshot = $screenshot
                process_tree = $processTree
                window_tree = $windowTree
                z_order = $zOrder
            }
        }
    }
    finally {
        Stop-AcceptanceProcess $process
    }
}

function Invoke-CanvasStaticActions {
    $process = Start-AcceptanceProcess $script:RitualistExe @("--canvas", "gaming_desktop")
    try {
        Start-Sleep -Seconds 5
        $window = Get-WindowByName "Ritualist Canvas" 15
        $initial = Save-Screenshot "canvas-initial"
        $tree = Save-WindowTree "canvas-initial" $window
        $themeEvidence = Get-CanvasThemeEvidence (Get-E2EEvents)
        $buttons = @("run", "dry_run", "doctor", "preview_plan") | Where-Object {
            $window -and (Find-Button $window $_)
        }
        if ($window -and (Test-ScreenshotNonBlank $initial) -and $buttons.Count -ge 4) {
            Set-Check "gaming_desktop_renders" "PASS" "gaming_desktop rendered with expected controls." @{
                screenshot = $initial
                window_tree = $tree
                controls = $buttons
                theme = $themeEvidence
            }
            Set-Check "expected_canvas_components_appear" "PASS" "Expected Canvas action controls were visible to UIA." @{
                screenshot = $initial
                window_tree = $tree
                controls = $buttons
                theme = $themeEvidence
            }
        }
        else {
            Set-Check "gaming_desktop_renders" "FAIL" "Canvas render or expected controls were missing." @{
                screenshot = $initial
                window_tree = $tree
                controls = $buttons
                theme = $themeEvidence
            }
            Set-Check "expected_canvas_components_appear" "FAIL" "Expected Canvas controls were not available." @{
                screenshot = $initial
                window_tree = $tree
                controls = $buttons
                theme = $themeEvidence
            }
        }

        $doctorInvoked = Invoke-NamedButton $window "doctor" 10
        Start-Sleep -Seconds 4
        $doctorShot = Save-Screenshot "canvas-doctor"
        $doctorStatus = Get-CanvasStatusEvents "diablo_night" |
            Where-Object {
                $_.payload.status -eq "success" -and
                $_.payload.message -match "doctor completed"
            } |
            Select-Object -First 1
        if ($doctorInvoked -and $doctorStatus) {
            Set-Check "ritual_card_doctor" "PASS" "Doctor action completed with packaged Canvas status evidence." @{
                screenshot = $doctorShot
                invoked = $doctorInvoked
                e2e_event = $doctorStatus
            }
        }
        else {
            Set-Check "ritual_card_doctor" "FAIL" "Doctor action did not produce success status evidence." @{
                screenshot = $doctorShot
                invoked = $doctorInvoked
            }
        }

        $dryRunInvoked = Invoke-NamedButton $window "dry_run" 10
        Start-Sleep -Seconds 8
        $dryRun = Get-LatestRun
        $dryRunJson = if ($dryRun) { Read-RunJson $dryRun.Name } else { $null }
        $dryRunEvidence = if ($dryRun) { Copy-RunLogEvidence $dryRun.Name } else { $null }
        if ($dryRunInvoked -and $dryRunJson -and $dryRunJson.dry_run -and $dryRunJson.status -eq "success") {
            Set-Check "ritual_card_dry_run" "PASS" "Dry run completed successfully with run-log evidence." @{
                run_id = $dryRun.Name
                run_log = $dryRunEvidence
            }
        }
        else {
            Set-Check "ritual_card_dry_run" "FAIL" "Dry run did not produce a successful dry-run log." @{
                invoked = $dryRunInvoked
                run_id = if ($dryRun) { $dryRun.Name } else { $null }
                run_log = $dryRunEvidence
            }
        }

        $previewInvoked = Invoke-NamedButton $window "preview_plan" 10
        Start-Sleep -Seconds 3
        $previewCommand = Invoke-CapturedCommand "target-preview" "python" @(
            "-m", "ritualist", "canvas", "action", "gaming_desktop", "diablo_target", "preview_plan", "--json"
        )
        $previewStatus = Get-CanvasStatusEvents "diablo_target" |
            Where-Object {
                $_.payload.status -eq "success" -and
                $_.payload.message -match "target plan preview completed"
            } |
            Select-Object -First 1
        if ($previewInvoked -and $previewStatus -and $previewCommand.exit_code -eq 0 -and $previewCommand.stdout_text -match "target_plan") {
            Set-Check "target_card_preview" "PASS" "Packaged Canvas preview completed and source CLI returned structured target plan JSON." @{
                command_stdout = $previewCommand.stdout
                command_stderr = $previewCommand.stderr
                packaged_e2e_event = $previewStatus
            }
        }
        else {
            Set-Check "target_card_preview" "FAIL" "Target plan preview did not return expected evidence." @{
                invoked = $previewInvoked
                command_stdout = $previewCommand.stdout
                command_stderr = $previewCommand.stderr
            }
        }

        $watchStarted = Invoke-NamedButton $window "Create from what I do" 10
        Start-Sleep -Seconds 2
        $watchStopped = Invoke-NamedButton $window "Stop Watch Me" 10
        Start-Sleep -Seconds 2
        $watchDrafted = Invoke-NamedButton $window "Create Draft" 10
        Start-Sleep -Seconds 2
        [void](Invoke-NamedButton $window "Discard" 5)
        $watchDir = Join-Path $script:FixtureAppData "watch-me"
        $latestWatch = if (Test-Path $watchDir) {
            Get-ChildItem -Path $watchDir -Directory | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        }
        else {
            $null
        }
        $scanMatches = @()
        if ($latestWatch) {
            foreach ($marker in $ForbiddenMarkers) {
                $match = Select-String -Path (Join-Path $latestWatch.FullName "*") -Pattern $marker -CaseSensitive:$false -ErrorAction SilentlyContinue
                if ($match) {
                    $scanMatches += $marker
                }
            }
        }
        if ($watchStarted -and $watchStopped -and $watchDrafted -and $latestWatch -and $scanMatches.Count -eq 0) {
            Set-Check "watch_me_preview_privacy" "PASS" "Watch Me draft was review-only and forbidden marker scan was clean." @{
                session_dir = $latestWatch.FullName
                forbidden_matches = $scanMatches
            }
        }
        else {
            Set-Check "watch_me_preview_privacy" "FAIL" "Watch Me evidence was missing or forbidden marker scan found data." @{
                started = $watchStarted
                stopped = $watchStopped
                drafted = $watchDrafted
                session_dir = if ($latestWatch) { $latestWatch.FullName } else { $null }
                forbidden_matches = $scanMatches
            }
        }
    }
    finally {
        Stop-AcceptanceProcess $process
    }
}

function Invoke-CanvasRunControls {
    $fakeProcess = Start-FakeExternalApp
    $process = Start-AcceptanceProcess $script:RitualistExe @("--canvas", "gaming_desktop")
    try {
        Start-Sleep -Seconds 5
        $window = Get-WindowByName "Ritualist Canvas" 15
        [void](Invoke-NamedButton $window "run" 10)
        [void](Get-WindowByName $FakeBattleNetTitle 20)
        Start-Sleep -Seconds 1
        $pause = Invoke-NamedButton $window "Pause" 15
        Start-Sleep -Seconds 1
        $resume = Invoke-NamedButton $window "Resume" 15
        Start-Sleep -Seconds 1
        $stop = Invoke-NamedButton $window "Stop" 15
        Start-Sleep -Seconds 5
        $run = Get-LatestRun
        $runJson = if ($run) { Read-RunJson $run.Name } else { $null }
        $runEvidence = if ($run) { Copy-RunLogEvidence $run.Name } else { $null }
        $statusHistory = if ($runJson -and $runJson.run_state_history) {
            @($runJson.run_state_history | ForEach-Object { $_.state })
        }
        else {
            @()
        }
        if ($pause -and $resume -and $stop -and $statusHistory -contains "paused" -and $statusHistory -contains "stopped") {
            Set-Check "ritual_controller_pause_resume_stop" "PASS" "Pause/Resume/Stop path was recorded during a real run." @{
                run_id = $run.Name
                run_log = $runEvidence
                state_history = $statusHistory
            }
        }
        else {
            Set-Check "ritual_controller_pause_resume_stop" "FAIL" "Pause/Resume/Stop evidence was incomplete." @{
                pause_invoked = $pause
                resume_invoked = $resume
                stop_invoked = $stop
                run_id = if ($run) { $run.Name } else { $null }
                state_history = $statusHistory
            }
        }
    }
    finally {
        Stop-AcceptanceProcess $process
        Stop-AcceptanceProcess $fakeProcess -Force
        Stop-FakeExternalApps
    }
}

function Invoke-CanvasRunDecline {
    $fakeProcess = Start-FakeExternalApp
    $process = Start-AcceptanceProcess $script:RitualistExe @("--canvas", "gaming_desktop")
    try {
        Start-Sleep -Seconds 5
        $window = Get-WindowByName "Ritualist Canvas" 15
        [void](Invoke-NamedButton $window "run" 10)
        $confirmation = Get-WindowByName "Ritualist Confirmation Required" 60
        $confirmationShot = Save-Screenshot "confirmation-z-order"
        $confirmationTree = Save-WindowTree "confirmation" $confirmation
        $zOrder = Save-ZOrderSnapshot "confirmation"
        $cancel = if ($confirmation) { Invoke-NamedButton $confirmation "Cancel Ritual" 5 } else { $false }
        Start-Sleep -Seconds 6
        $fakeWindow = Get-WindowByName $FakeBattleNetTitle 5
        $fakeWindowTree = Save-WindowTree "fake-battlenet-after-decline" $fakeWindow
        $playInvoked = Test-WindowTreeContainsText $fakeWindowTree "Play was invoked."
        $run = Get-LatestRun
        $runJson = if ($run) { Read-RunJson $run.Name } else { $null }
        $runEvidence = if ($run) { Copy-RunLogEvidence $run.Name } else { $null }
        $show = if ($run) {
            Invoke-CapturedCommand "show-run-declined" "python" @("-m", "ritualist", "show-run", $run.Name, "--no-repair")
        }
        else {
            $null
        }
        $zRows = Get-Content -Path $zOrder -Raw | ConvertFrom-Json
        $confirmationIndex = ($zRows | Where-Object { $_.title -eq "Ritualist Confirmation Required" } | Select-Object -First 1).z_index
        $battleNetIndex = ($zRows | Where-Object { $_.title -eq $FakeBattleNetTitle } | Select-Object -First 1).z_index
        $confirmationAbove = $null -ne $confirmationIndex -and $null -ne $battleNetIndex -and $confirmationIndex -lt $battleNetIndex
        if ($confirmation -and $confirmationAbove) {
            Set-Check "native_confirmation_z_order" "PASS" "Native confirmation was above fake Battle.net fixture." @{
                screenshot = $confirmationShot
                window_tree = $confirmationTree
                z_order = $zOrder
            }
        }
        else {
            Set-Check "native_confirmation_z_order" "FAIL" "Confirmation dialog was missing or not above fake Battle.net." @{
                screenshot = $confirmationShot
                window_tree = $confirmationTree
                z_order = $zOrder
            }
        }
        $runtimeEvents = if ($run) { Get-RuntimeEventsForRun $run.Name } else { @() }
        $runtimeEventStates = @(
            $runtimeEvents |
                Where-Object { $_.payload.runtime_event.type -eq "run.state_changed" } |
                ForEach-Object { $_.payload.runtime_event.state }
        )
        $canvasStatusEvents = Get-CanvasStatusEvents "diablo_night" |
            Where-Object { $_.payload.message -match "Run state:" -or $_.payload.message -match "Confirmation required" }
        if ($runJson -and $runJson.status -eq "stopped" -and $runJson.stopped_reason -eq "stopped_user_declined_confirmation") {
            Set-Check "declining_play_stopped" "PASS" "Declined Play ended as stopped." @{
                run_id = $run.Name
                run_log = $runEvidence
            }
            if (-not $playInvoked) {
                Set-Check "safe_ritual_card_run" "PASS" "Fixture run reached confirmation and Play was not invoked after decline." @{
                    run_id = $run.Name
                    run_log = $runEvidence
                    fixture_window_tree = $fakeWindowTree
                    fixture = "fake Battle.net"
                }
            }
            else {
                Set-Check "safe_ritual_card_run" "FAIL" "Fake Play button was invoked despite declined confirmation." @{
                    run_id = $run.Name
                    run_log = $runEvidence
                    fixture_window_tree = $fakeWindowTree
                }
            }
            if (
                $runtimeEventStates -contains "waiting" -and
                $runtimeEventStates -contains "confirming" -and
                $runtimeEventStates -contains "stopped" -and
                @($canvasStatusEvents).Count -gt 0
            ) {
                Set-Check "ritual_status_updates" "PASS" "Runtime state transitions were captured in run log and packaged Canvas E2E events." @{
                    run_id = $run.Name
                    run_log = $runEvidence
                    e2e_events = @($runtimeEvents | Select-Object -First 12)
                    canvas_status_event_count = @($canvasStatusEvents).Count
                }
            }
            else {
                Set-Check "ritual_status_updates" "FAIL" "Runtime state evidence was missing required E2E transitions." @{
                    run_id = $run.Name
                    run_log = $runEvidence
                    runtime_event_states = $runtimeEventStates
                    canvas_status_event_count = @($canvasStatusEvents).Count
                }
            }
        }
        else {
            Set-Check "declining_play_stopped" "FAIL" "Declined Play did not end with stopped_user_declined_confirmation." @{
                run_id = if ($run) { $run.Name } else { $null }
                run_log = $runEvidence
            }
            Set-Check "safe_ritual_card_run" "FAIL" "Fixture run did not reach safe declined confirmation." @{
                run_id = if ($run) { $run.Name } else { $null }
                run_log = $runEvidence
            }
            Set-Check "ritual_status_updates" "FAIL" "Runtime state evidence was missing." @{
                run_id = if ($run) { $run.Name } else { $null }
                run_log = $runEvidence
            }
        }
        if (
            $show -and
            $show.exit_code -eq 0 -and
            $show.stdout_text -match "stopped_user_declined_confirmation" -and
            $show.stdout_text -match "Confirmation declined" -and
            $show.stdout_text -match "Play"
        ) {
            Set-Check "show_run_declined_confirmation" "PASS" "show-run clearly records declined confirmation." @{
                command_stdout = $show.stdout
                command_stderr = $show.stderr
            }
        }
        else {
            Set-Check "show_run_declined_confirmation" "FAIL" "show-run did not clearly record declined confirmation." @{
                command_stdout = if ($show) { $show.stdout } else { $null }
                command_stderr = if ($show) { $show.stderr } else { $null }
            }
        }
    }
    finally {
        Stop-AcceptanceProcess $process
        Stop-AcceptanceProcess $fakeProcess -Force
        Stop-FakeExternalApps
    }
}

function Invoke-HardKillRecovery {
    $before = @()
    $runs = Join-Path $script:FixtureAppData "runs"
    if (Test-Path $runs) {
        $before = @(Get-ChildItem -Path $runs -Directory | ForEach-Object { $_.Name })
    }
    $fakeProcess = Start-FakeExternalApp
    $process = Start-AcceptanceProcess $script:RitualistExe @("--canvas", "gaming_desktop")
    $runId = $null
    try {
        Start-Sleep -Seconds 5
        $window = Get-WindowByName "Ritualist Canvas" 15
        [void](Invoke-NamedButton $window "run" 10)
        $confirmation = Get-WindowByName "Ritualist Confirmation Required" 35
        Start-Sleep -Seconds 1
        $newRun = Get-ChildItem -Path $runs -Directory |
            Where-Object { $before -notcontains $_.Name } |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1
        if ($newRun) {
            $runId = $newRun.Name
        }
        Stop-AcceptanceProcess $process -Force
        $process = $null
        Start-Sleep -Seconds 2
        $homeProcess = Start-AcceptanceProcess $script:RitualistExe @()
        Start-Sleep -Seconds 8
        $homeShot = Save-Screenshot "hard-kill-relaunch-home"
        Stop-AcceptanceProcess $homeProcess
        $runJson = if ($runId) { Read-RunJson $runId } else { $null }
        $runEvidence = if ($runId) { Copy-RunLogEvidence $runId } else { $null }
        $show = if ($runId) {
            Invoke-CapturedCommand "show-run-interrupted" "python" @("-m", "ritualist", "show-run", $runId, "--no-repair")
        }
        else {
            $null
        }
        if ($runJson -and $runJson.status -eq "interrupted" -and $show.stdout_text -match "exited before finalizing") {
            Set-Check "hard_kill_repairs_interrupted" "PASS" "Hard-kill recovery repaired abandoned run to interrupted." @{
                run_id = $runId
                run_log = $runEvidence
                relaunch_home_screenshot = $homeShot
                show_run_stdout = $show.stdout
            }
        }
        else {
            Set-Check "hard_kill_repairs_interrupted" "FAIL" "Hard-kill recovery evidence was missing or not interrupted." @{
                run_id = $runId
                run_log = $runEvidence
                relaunch_home_screenshot = $homeShot
                show_run_stdout = if ($show) { $show.stdout } else { $null }
            }
        }
    }
    finally {
        if ($process) {
            Stop-AcceptanceProcess $process -Force
        }
        Stop-AcceptanceProcess $fakeProcess -Force
        Stop-FakeExternalApps
    }
}

function Invoke-PackSafetyChecks {
    $canvasOut = Join-Path $CommandRoot "visual_acceptance.ritualistcanvas"
    $themeOut = Join-Path $CommandRoot "minimal_theme.ritualisttheme"
    $canvasPath = Join-Path $script:FixtureAppData "canvases\visual_acceptance.yaml"
    $themePath = Join-Path $script:FixtureAppData "themes\minimal_theme.yaml"
    $canvasExport = Invoke-CapturedCommand "canvas-pack-export" "python" @("-m", "ritualist", "canvas", "pack", "export", $canvasPath, "--out", $canvasOut, "--json")
    $canvasImport = Invoke-CapturedCommand "canvas-pack-import" "python" @("-m", "ritualist", "canvas", "pack", "import", $canvasOut, "--json")
    $themeExport = Invoke-CapturedCommand "theme-pack-export" "python" @("-m", "ritualist", "canvas", "theme", "export", $themePath, "--out", $themeOut, "--json")
    $themeImport = Invoke-CapturedCommand "theme-pack-import" "python" @("-m", "ritualist", "canvas", "theme", "import", $themeOut, "--json")
    if ($canvasExport.exit_code -eq 0 -and $canvasImport.exit_code -eq 0 -and $themeExport.exit_code -eq 0 -and $themeImport.exit_code -eq 0 -and $canvasImport.stdout_text -match "quarantined" -and $themeImport.stdout_text -match "quarantined") {
            Set-Check "canvas_theme_pack_import_export_no_autorun" "PASS" "Source CLI Canvas/theme packs exported and imported into quarantine without auto-run." @{
            canvas_export_stdout = $canvasExport.stdout
            canvas_import_stdout = $canvasImport.stdout
            theme_export_stdout = $themeExport.stdout
            theme_import_stdout = $themeImport.stdout
        }
    }
    else {
        Set-Check "canvas_theme_pack_import_export_no_autorun" "FAIL" "Canvas/theme pack import/export did not pass quarantine checks." @{
            canvas_export_stdout = $canvasExport.stdout
            canvas_import_stdout = $canvasImport.stdout
            theme_export_stdout = $themeExport.stdout
            theme_import_stdout = $themeImport.stdout
        }
    }

    $badCanvas = Join-Path $CommandRoot "bad_component.yaml"
    @"
schema: ritualist.canvas.v1
id: bad_component
name: Bad Component
mode: desktop_canvas
components:
  - id: bad
    type: text.label
    width: 220
    height: 80
    props:
      text: "<script>alert(1)</script>"
"@ | Set-Content -Path $badCanvas -Encoding UTF8
    $badOut = Join-Path $CommandRoot "bad_component.ritualistcanvas"
    $badExport = Invoke-CapturedCommand "bad-component-export" "python" @("-m", "ritualist", "canvas", "pack", "export", $badCanvas, "--out", $badOut, "--json")
    if ($badExport.exit_code -ne 0 -and ($badExport.stdout_text + $badExport.stderr_text) -match "script") {
            Set-Check "arbitrary_component_code_rejected" "PASS" "Source CLI script-like component content was rejected." @{
            stdout = $badExport.stdout
            stderr = $badExport.stderr
        }
    }
    else {
        Set-Check "arbitrary_component_code_rejected" "FAIL" "Script-like component content was not rejected." @{
            stdout = $badExport.stdout
            stderr = $badExport.stderr
            exit_code = $badExport.exit_code
        }
    }
}

function Invoke-PerformanceChecks {
    $perf100 = Invoke-CapturedCommand "perf-100" "python" @("-m", "ritualist", "perf", "canvas-use", "--mock-components", "100", "--json")
    $perf300 = Invoke-CapturedCommand "perf-300" "python" @("-m", "ritualist", "perf", "canvas-use", "--mock-components", "300", "--json")
    $frames = Capture-ScreenFrames "perf-heartbeat-sample" 3
    $ok = $perf100.exit_code -eq 0 -and $perf300.exit_code -eq 0
    if ($ok) {
            Set-Check "component_perf_100_300_recorded" "PASS" "Source CLI 100/300 component perf outputs were recorded." @{
            perf_100_stdout = $perf100.stdout
            perf_300_stdout = $perf300.stdout
            frames = $frames
        }
        Set-Check "ui_heartbeat_no_obvious_freeze" "NEEDS_HUMAN_REVIEW" "Frame/e2e timing was captured, but subjective smoothness still needs human review." @{
            frames = $frames
            e2e_dir = $E2ERoot
        }
    }
    else {
        Set-Check "component_perf_100_300_recorded" "FAIL" "Perf commands failed." @{
            perf_100_stdout = $perf100.stdout
            perf_100_stderr = $perf100.stderr
            perf_300_stdout = $perf300.stdout
            perf_300_stderr = $perf300.stderr
        }
        Set-Check "ui_heartbeat_no_obvious_freeze" "FAIL" "Perf command failure prevents heartbeat/render timing confidence." @{}
    }
}

function Set-RemainingReviewChecks {
    if (-not $Results.Contains("recent_activity_updates")) {
        $runsCommand = Invoke-CapturedCommand "runs-after-acceptance" "python" @("-m", "ritualist", "runs", "--limit", "5", "--no-repair")
        Set-Check "recent_activity_updates" "NEEDS_HUMAN_REVIEW" "Source CLI run history was captured, but packaged Home Recent activity was not exposed through UIA for machine assertion." @{
            runs_stdout = $runsCommand.stdout
            runs_stderr = $runsCommand.stderr
        }
    }
}

function Write-Summaries {
    $eventsPath = Join-Path $SnapshotRoot "e2e-events-merged.json"
    $parseErrorsPath = Join-Path $SnapshotRoot "e2e-parse-errors.json"
    $events = Get-E2EEvents
    $themeEvidence = Get-CanvasThemeEvidence $events
    Write-JsonFile $eventsPath $events 10 | Out-Null
    if ($script:E2EParseErrors.Count -gt 0) {
        Write-JsonFile $parseErrorsPath $script:E2EParseErrors 8 | Out-Null
    }
    $counts = [ordered]@{
        PASS = @($Results.Values | Where-Object { $_.status -eq "PASS" }).Count
        FAIL = @($Results.Values | Where-Object { $_.status -eq "FAIL" }).Count
        NEEDS_HUMAN_REVIEW = @($Results.Values | Where-Object { $_.status -eq "NEEDS_HUMAN_REVIEW" }).Count
    }
    $taggable = ($counts.FAIL -eq 0 -and $counts.NEEDS_HUMAN_REVIEW -eq 0)
    $summary = [ordered]@{
        schema = "ritualist.release_acceptance_summary.v1"
        release = "v0.2.0-alpha.1"
        acceptance_spec = $AcceptanceSpec
        generated_at = (Get-Date).ToUniversalTime().ToString("o")
        repo_root = $RepoRoot
        packaged = [bool]$Packaged
        executable = $script:RitualistExe
        command_scope = "Packaged executable is used for Home, Canvas Use Mode, classic GUI, and runtime scenarios. Source-tree python -m ritualist is used for supplemental CLI-only safety, perf, run-log, and visual-pack command evidence because the Windows app bundle is a GUI entry point."
        artifact_root = $AcceptanceRoot
        evidence_root = $EvidenceRoot
        e2e_events = $eventsPath
        theme_evidence = $themeEvidence
        e2e_parse_errors = [ordered]@{
            count = $script:E2EParseErrors.Count
            path = $parseErrorsPath
        }
        counts = $counts
        taggable = $taggable
        tag_created = $false
        checks = @($Results.Values)
    }
    Write-JsonFile $SummaryJson $summary 12 | Out-Null

    $lines = @()
    $lines += "# Ritualist v0.2.0-alpha.1 Acceptance Summary"
    $lines += ""
    $lines += "- Generated: $($summary.generated_at)"
    $lines += "- Executable: ``$($summary.executable)``"
    $lines += "- Command scope: $($summary.command_scope)"
    $lines += "- Artifact root: ``$AcceptanceRoot``"
    $lines += "- Taggable: **$taggable**"
    $lines += "- Tag created: **false**"
    if ($themeEvidence.selected_theme_ids.Count -gt 0) {
        $lines += "- Canvas theme evidence: ``$($themeEvidence.selected_theme_ids -join ", ")``"
    }
    $lines += ""
    $lines += "| Check | Status | Message |"
    $lines += "|---|---:|---|"
    foreach ($check in $Results.Values) {
        $message = ($check.message -replace "\|", "\|")
        $lines += "| ``$($check.id)`` | $($check.status) | $message |"
    }
    $blockers = @($Results.Values | Where-Object { $_.status -ne "PASS" })
    $lines += ""
    $lines += "## Blockers"
    if ($blockers.Count -eq 0) {
        $lines += ""
        $lines += "None."
    }
    else {
        foreach ($blocker in $blockers) {
            $lines += "- ``$($blocker.id)``: $($blocker.status) - $($blocker.message)"
        }
    }
    Set-Content -Path $SummaryMd -Value $lines -Encoding UTF8
}

try {
    New-Fixtures
    $script:RitualistExe = Resolve-RitualistExe
    Assert-LaunchWindow -Id "packaged_home_visible" -Title "Ritualist Home" -LaunchArguments @() -ScreenshotName "packaged-home"
    Assert-LaunchWindow -Id "packaged_canvas_visible" -Title "Ritualist Canvas" -LaunchArguments @("--canvas", "gaming_desktop") -ScreenshotName "packaged-canvas"
    Assert-LaunchWindow -Id "packaged_classic_gui_visible" -Title "Ritualist" -LaunchArguments @("--classic-gui") -ScreenshotName "packaged-classic-gui"
    Invoke-CanvasStaticActions
    Invoke-CanvasRunControls
    Invoke-CanvasRunDecline
    Invoke-HardKillRecovery
    Invoke-PackSafetyChecks
    Invoke-PerformanceChecks
    Set-RemainingReviewChecks
}
catch {
    $errorPath = Join-Path $AcceptanceRoot "acceptance-error.txt"
    ($_ | Out-String) | Set-Content -Path $errorPath -Encoding UTF8
    Set-Check "harness_error" "FAIL" "Acceptance harness failed: $($_.Exception.Message)" @{ error = $errorPath }
}
finally {
    foreach ($process in $GeneratedProcesses) {
        Stop-AcceptanceProcess $process -Force
    }
    Stop-FakeExternalApps
    Write-Summaries
}

Write-Host "Acceptance summary JSON: $SummaryJson"
Write-Host "Acceptance summary Markdown: $SummaryMd"
exit (@($Results.Values | Where-Object { $_.status -eq "FAIL" }).Count)
