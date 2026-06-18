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
$script:VisualArtifacts = @()

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

    [StructLayout(LayoutKind.Sequential)]
    public struct RECT {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }

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
    public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);

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
$RecordingSurfaceTerms = @(
    "Watch Me",
    "watch-me",
    "watch_me",
    "Create from what I do",
    "Stop Watch Me",
    "Create Draft",
    "recording",
    "recording mode",
    "observation session",
    "live observation",
    "teach by watching",
    "macro recording",
    "record/replay",
    "recorder",
    "screenshot",
    "screen capture",
    "screen recording",
    "OCR",
    "keylog",
    "keystroke",
    "preview capture",
    "preview-capture"
)
$FakeBattleNetTitle = "Battle.net Fixture"
$FakeWallpaperTitle = "Ritualist Wallpaper Fixture"

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

function Get-FrameTimingEvidence {
    param([object]$Frames, [int]$MaxAllowedGapMilliseconds = 1500)
    if (-not $Frames -or -not $Frames.manifest -or -not (Test-Path $Frames.manifest)) {
        return [ordered]@{
            available = $false
            reason = "frame manifest missing"
            max_allowed_gap_ms = $MaxAllowedGapMilliseconds
        }
    }
    $manifest = Get-Content -Path $Frames.manifest -Raw | ConvertFrom-Json
    $elapsed = @(
        $manifest.frames |
            ForEach-Object { [double]$_.elapsed_ms } |
            Sort-Object
    )
    $gaps = @()
    for ($index = 1; $index -lt $elapsed.Count; $index += 1) {
        $gaps += [Math]::Round(($elapsed[$index] - $elapsed[$index - 1]), 1)
    }
    $maxGap = if ($gaps.Count -gt 0) {
        [Math]::Round((($gaps | Measure-Object -Maximum).Maximum), 1)
    }
    else {
        $null
    }
    $passed = $elapsed.Count -ge 3 -and $null -ne $maxGap -and $maxGap -le $MaxAllowedGapMilliseconds
    return [ordered]@{
        available = $true
        manifest = $Frames.manifest
        directory = $Frames.directory
        frame_count = $elapsed.Count
        elapsed_ms = $elapsed
        gaps_ms = $gaps
        max_frame_gap_ms = $maxGap
        max_allowed_gap_ms = $MaxAllowedGapMilliseconds
        passed = $passed
    }
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
        $rect = New-Object RitualistAcceptanceWin32+RECT
        $bounds = $null
        if ([RitualistAcceptanceWin32]::GetWindowRect($handle, [ref]$rect)) {
            $bounds = [ordered]@{
                x = [int]$rect.Left
                y = [int]$rect.Top
                width = [int]($rect.Right - $rect.Left)
                height = [int]($rect.Bottom - $rect.Top)
            }
        }
        $rows += [ordered]@{
            z_index = $index
            hwnd = $handle.ToInt64()
            title = $title
            process_id = [int64]$processId
            is_foreground = ($handle -eq $foreground)
            bounds = $bounds
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

function Find-NamedElement {
    param([object]$Window, [string]$Name)
    if (-not $Window) {
        return $null
    }
    $condition = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::NameProperty,
        $Name
    )
    return $Window.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condition)
}

function Get-UiTextSnapshot {
    param([object]$Window)
    if (-not $Window) {
        return @()
    }
    $rows = @()
    $elements = $Window.FindAll(
        [System.Windows.Automation.TreeScope]::Descendants,
        [System.Windows.Automation.Condition]::TrueCondition
    )
    foreach ($element in $elements) {
        $name = $element.Current.Name
        $automationId = $element.Current.AutomationId
        if ([string]::IsNullOrWhiteSpace($name) -and [string]::IsNullOrWhiteSpace($automationId)) {
            continue
        }
        $rows += [ordered]@{
            name = $name
            automation_id = $automationId
            control_type = $element.Current.ControlType.ProgrammaticName
            is_enabled = [bool]$element.Current.IsEnabled
        }
    }
    return $rows
}

function Find-TermMatches {
    param([string]$Text, [string[]]$Terms)
    $termMatches = @()
    foreach ($term in $Terms) {
        if ([regex]::IsMatch($Text, [regex]::Escape($term), [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)) {
            $termMatches += $term
        }
    }
    return @($termMatches | Select-Object -Unique)
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

function Get-PrimaryScreenGeometry {
    $screen = [System.Windows.Forms.Screen]::PrimaryScreen
    return [ordered]@{
        bounds = [ordered]@{
            x = [int]$screen.Bounds.X
            y = [int]$screen.Bounds.Y
            width = [int]$screen.Bounds.Width
            height = [int]$screen.Bounds.Height
        }
        work_area = [ordered]@{
            x = [int]$screen.WorkingArea.X
            y = [int]$screen.WorkingArea.Y
            width = [int]$screen.WorkingArea.Width
            height = [int]$screen.WorkingArea.Height
        }
    }
}

function Test-BoundsMatch {
    param([object]$Actual, [object]$Expected, [int]$Tolerance = 3)
    if (-not $Actual -or -not $Expected) {
        return $false
    }
    foreach ($key in @("x", "y", "width", "height")) {
        $actualValue = if ($Actual -is [hashtable]) { $Actual[$key] } else { $Actual.$key }
        $expectedValue = if ($Expected -is [hashtable]) { $Expected[$key] } else { $Expected.$key }
        if ([Math]::Abs(([int]$actualValue) - ([int]$expectedValue)) -gt $Tolerance) {
            return $false
        }
    }
    return $true
}

function Start-AcceptanceProcess {
    param([string]$FilePath, [string[]]$Arguments = @(), [hashtable]$ExtraEnv = @{})
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
    foreach ($key in $ExtraEnv.Keys) {
        $startInfo.EnvironmentVariables[$key] = [string]$ExtraEnv[$key]
    }
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

function Stop-FakeWallpaperFixture {
    $fakeScript = Join-Path $FixtureRoot "fake-wallpaper.ps1"
    $windows = @(Get-TopLevelWindows | Where-Object { $_.title -eq $FakeWallpaperTitle })
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

function Start-FakeWallpaperFixture {
    Stop-FakeWallpaperFixture
    $fakeScript = Join-Path $FixtureRoot "fake-wallpaper.ps1"
    $process = Start-AcceptanceProcess "powershell.exe" @(
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-STA",
        "-File",
        $fakeScript
    )
    [void](Get-WindowByName $FakeWallpaperTitle 20)
    return $process
}

function Get-WallpaperCompatibilityProcesses {
    $names = @("wallpaper32", "wallpaper64", "wallpaper_engine", "Lively", "Lively.UI.WinUI")
    return @(
        Get-Process -ErrorAction SilentlyContinue |
            Where-Object { $names -contains $_.ProcessName } |
            ForEach-Object {
                [ordered]@{
                    process_id = [int]$_.Id
                    name = $_.ProcessName
                    observed_only = $true
                }
            }
    )
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
                    theme_warning_count = $_.payload.theme_warning_count
                    accessibility_warning_count = $_.payload.theme_accessibility_warning_count
                    accessibility_warnings = $_.payload.theme_accessibility_warnings
                }
            }
    )
    return [ordered]@{
        canvas_ready = $ready
        selected_theme_ids = @($ready | ForEach-Object { $_.theme_id } | Where-Object { $_ } | Select-Object -Unique)
        invalid_theme_events = @($ready | Where-Object { $_.theme_valid -eq $false })
        accessibility_warning_count = @($ready | Measure-Object -Property accessibility_warning_count -Sum).Sum
        accessibility_warnings = @($ready | ForEach-Object { $_.accessibility_warnings } | Where-Object { $_ })
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

function Get-UiHeartbeatEvents {
    param([int]$ProcessId = 0)
    $events = Get-E2EEvents | Where-Object { $_.event -eq "canvas.ui_heartbeat" }
    if ($ProcessId -gt 0) {
        $events = $events | Where-Object { [int]$_.process_id -eq $ProcessId }
    }
    return @($events | Sort-Object { [double]$_.payload.monotonic_ms })
}

function Get-UiHeartbeatTimingEvidence {
    param([int]$ProcessId, [int]$MaxAllowedGapMilliseconds = 1500)
    $events = Get-UiHeartbeatEvents $ProcessId
    $elapsed = @($events | ForEach-Object { [double]$_.payload.monotonic_ms })
    $gaps = @()
    for ($index = 1; $index -lt $elapsed.Count; $index += 1) {
        $gaps += [Math]::Round(($elapsed[$index] - $elapsed[$index - 1]), 1)
    }
    $maxGap = if ($gaps.Count -gt 0) {
        [Math]::Round((($gaps | Measure-Object -Maximum).Maximum), 1)
    }
    else {
        $null
    }
    $passed = $elapsed.Count -ge 3 -and $null -ne $maxGap -and $maxGap -le $MaxAllowedGapMilliseconds
    return [ordered]@{
        available = $events.Count -gt 0
        process_id = $ProcessId
        event_count = $events.Count
        elapsed_ms = $elapsed
        gaps_ms = $gaps
        max_app_heartbeat_gap_ms = $maxGap
        max_allowed_gap_ms = $MaxAllowedGapMilliseconds
        passed = $passed
    }
}

function Get-RecentActivityModelEvidence {
    param([int]$ProcessId, [string]$RunId)
    $events = Get-UiHeartbeatEvents $ProcessId
    $matching = @(
        $events |
            Where-Object {
                @($_.payload.recent_activity_run_ids) -contains $RunId
            }
    )
    $latest = if ($matching.Count -gt 0) { $matching[-1] } else { $null }
    return [ordered]@{
        process_id = $ProcessId
        run_id = $RunId
        heartbeat_event_count = $events.Count
        matching_event_count = $matching.Count
        contains_run = $matching.Count -gt 0
        latest_matching_event = $latest
    }
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

    $fakeWallpaper = Join-Path $FixtureRoot "fake-wallpaper.ps1"
    @'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$screen = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
$form = New-Object System.Windows.Forms.Form
$form.Text = "Ritualist Wallpaper Fixture"
$form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::None
$form.ShowInTaskbar = $false
$form.StartPosition = "Manual"
$form.Location = $screen.Location
$form.Size = $screen.Size
$form.BackColor = [System.Drawing.Color]::FromArgb(35, 58, 92)
$label = New-Object System.Windows.Forms.Label
$label.Text = "Fake animated wallpaper fixture"
$label.ForeColor = [System.Drawing.Color]::White
$label.BackColor = [System.Drawing.Color]::Transparent
$label.Font = New-Object System.Drawing.Font("Segoe UI", 20, [System.Drawing.FontStyle]::Bold)
$label.AutoSize = $true
$label.Location = New-Object System.Drawing.Point(36, 36)
$form.Controls.Add($label)
$script:tick = 0
$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 250
$timer.Add_Tick({
    $script:tick = ($script:tick + 1) % 6
    $colors = @(
        [System.Drawing.Color]::FromArgb(35, 58, 92),
        [System.Drawing.Color]::FromArgb(47, 83, 64),
        [System.Drawing.Color]::FromArgb(78, 58, 103),
        [System.Drawing.Color]::FromArgb(91, 68, 43),
        [System.Drawing.Color]::FromArgb(42, 88, 101),
        [System.Drawing.Color]::FromArgb(64, 72, 88)
    )
    $form.BackColor = $colors[$script:tick]
})
$timer.Start()
[System.Windows.Forms.Application]::EnableVisualStyles()
[System.Windows.Forms.Application]::Run($form)
'@ | Set-Content -Path $fakeWallpaper -Encoding UTF8

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

function Add-VisualArtifact {
    param(
        [string]$Id,
        [string]$CanvasId,
        [string]$State,
        [bool]$NonBlank,
        [hashtable]$Evidence
    )
    $script:VisualArtifacts += [ordered]@{
        id = $Id
        canvas_id = $CanvasId
        state = $State
        non_blank = $NonBlank
        evidence = $Evidence
    }
}

function Capture-CanvasVisualArtifact {
    param(
        [string]$CanvasId,
        [string]$ArtifactId,
        [string]$State = "ready"
    )
    $process = Start-AcceptanceProcess $script:RitualistExe @("--canvas", $CanvasId)
    try {
        Start-Sleep -Seconds $ScenarioDwellSeconds
        $window = Get-WindowByName "Ritualist Canvas" 10
        $screenshot = Save-Screenshot "ui-refresh-$ArtifactId"
        $frames = Capture-ScreenFrames "ui-refresh-$ArtifactId" 2
        $processTree = Save-ProcessTree "ui-refresh-$ArtifactId" $process.Id
        $windowTree = Save-WindowTree "ui-refresh-$ArtifactId" $window
        $zOrder = Save-ZOrderSnapshot "ui-refresh-$ArtifactId"
        Add-VisualArtifact -Id $ArtifactId -CanvasId $CanvasId -State $State -NonBlank (Test-ScreenshotNonBlank $screenshot) -Evidence @{
            screenshot = $screenshot
            frames = $frames
            process_tree = $processTree
            window_tree = $windowTree
            z_order = $zOrder
        }
    }
    finally {
        Stop-AcceptanceProcess $process
    }
}

function Capture-DesktopWorkAreaCanvasArtifact {
    $wallpaperProcessesBefore = @()
    $fakeWallpaperProcess = $null
    $process = $null
    try {
        $wallpaperProcessesBefore = Get-WallpaperCompatibilityProcesses
        $fakeWallpaperProcess = Start-FakeWallpaperFixture
        $process = Start-AcceptanceProcess $script:RitualistExe @("--canvas", "minimal_desktop", "--host", "desktop-work-area")
        Start-Sleep -Seconds $ScenarioDwellSeconds
        $window = Get-WindowByName "Ritualist Canvas" 10
        $fakeWallpaperWindow = Get-WindowByName $FakeWallpaperTitle 2
        $screenshot = Save-Screenshot "desktop-work-area-canvas"
        $frames = Capture-ScreenFrames "desktop-work-area-canvas" 2
        $processTree = Save-ProcessTree "desktop-work-area-canvas" $process.Id
        $windowTree = Save-WindowTree "desktop-work-area-canvas" $window
        $zOrderPath = Save-ZOrderSnapshot "desktop-work-area-canvas"
        $zOrder = Get-Content -Path $zOrderPath -Raw | ConvertFrom-Json
        $screen = Get-PrimaryScreenGeometry
        $windowRow = @($zOrder | Where-Object { [int64]$_.process_id -eq [int64]$process.Id -and $_.title -eq "Ritualist Canvas" } | Select-Object -First 1)
        $fakeWallpaperRow = @($zOrder | Where-Object { $_.title -eq $FakeWallpaperTitle } | Select-Object -First 1)
        $exitControl = Find-NamedElement $window "Exit Desktop Canvas"
        $events = Get-E2EEvents
        $hostReady = @(
            $events |
                Where-Object { $_.event -eq "canvas.host.ready" -and [int]$_.process_id -eq $process.Id } |
                Select-Object -Last 1
        )
        $boundsMatch = Test-BoundsMatch $windowRow.bounds $screen.work_area
        $exitInvoked = if ($window) { Invoke-NamedButton $window "Exit Desktop Canvas" 5 } else { $false }
        Start-Sleep -Seconds 2
        $exitClean = $process.HasExited
        $wallpaperProcessesAfter = Get-WallpaperCompatibilityProcesses
        Add-VisualArtifact -Id "desktop-work-area-canvas" -CanvasId "minimal_desktop" -State "desktop_work_area" -NonBlank (Test-ScreenshotNonBlank $screenshot) -Evidence @{
            screenshot = $screenshot
            frames = $frames
            process_tree = $processTree
            window_tree = $windowTree
            z_order = $zOrderPath
            fake_wallpaper_fixture = [ordered]@{
                title = $FakeWallpaperTitle
                process_id = if ($fakeWallpaperProcess) { $fakeWallpaperProcess.Id } else { $null }
                window_present = [bool]$fakeWallpaperWindow
                bounds = if ($fakeWallpaperRow) { $fakeWallpaperRow.bounds } else { $null }
                running_during_capture = [bool]$fakeWallpaperWindow
            }
            wallpaper_app_processes = [ordered]@{
                observed_only = $true
                before = $wallpaperProcessesBefore
                after = $wallpaperProcessesAfter
                controlled_by_ritualist = $false
            }
            screen_geometry = $screen
            window_bounds = $windowRow.bounds
            bounds_match_work_area = $boundsMatch
            exit_control_present = [bool]$exitControl
            exit_invoked = $exitInvoked
            exit_clean = $exitClean
            host_ready = if ($hostReady.Count -gt 0) { $hostReady[-1] } else { $null }
            background_passthrough = if ($hostReady.Count -gt 0) { $hostReady[-1].payload.background_passthrough } else { $null }
            background_mode = if ($hostReady.Count -gt 0) { $hostReady[-1].payload.background_mode } else { $null }
            input_policy = if ($hostReady.Count -gt 0) { $hostReady[-1].payload.input_policy } else { $null }
            click_through_implemented = if ($hostReady.Count -gt 0) { $hostReady[-1].payload.click_through_implemented } else { $null }
            blank_area_click_through_status = if ($hostReady.Count -gt 0) { $hostReady[-1].payload.blank_area_click_through_status } else { "NEEDS_HUMAN_REVIEW" }
            blank_area_click_through_machine_verified = if ($hostReady.Count -gt 0) { $hostReady[-1].payload.blank_area_click_through_machine_verified } else { $false }
            blank_area_click_through_review = [ordered]@{
                status = if ($hostReady.Count -gt 0) { $hostReady[-1].payload.blank_area_click_through_status } else { "NEEDS_HUMAN_REVIEW" }
                machine_verified = if ($hostReady.Count -gt 0) { $hostReady[-1].payload.blank_area_click_through_machine_verified } else { $false }
                reason = "Desktop Work-Area Use Mode still captures blank areas; native per-component hit testing is not implemented."
                no_coordinate_click_automation = $true
            }
            component_click_evidence = [ordered]@{
                status = if ($exitInvoked) { "PASS" } else { "NEEDS_HUMAN_REVIEW" }
                basis = "Visible exit control was invoked; ritual cards and Canvas controls are covered by packaged action checks."
                exit_control_invoked = $exitInvoked
            }
            interactive_wallpaper_fixture_input = [ordered]@{
                status = "NEEDS_HUMAN_REVIEW"
                machine_tested = $false
                fixture_visible = [bool]$fakeWallpaperWindow
                reason = "The harness records fixture visibility but does not synthesize blank-area mouse input because coordinate-click automation is out of scope."
            }
            edit_mode_input_capture = [ordered]@{
                status = "NEEDS_HUMAN_REVIEW"
                machine_tested = $false
                basis = "Edit Mode visual/control evidence is captured separately; blank-area edit input was not synthesized."
            }
            monitor = if ($hostReady.Count -gt 0) { $hostReady[-1].payload.monitor } else { $null }
            dpi = if ($hostReady.Count -gt 0) { $hostReady[-1].payload.dpi } else { $null }
            recovery = if ($hostReady.Count -gt 0) { $hostReady[-1].payload.recovery } else { $null }
            taskbar_policy = "respect"
        }
    }
    finally {
        Stop-AcceptanceProcess $process
        Stop-AcceptanceProcess $fakeWallpaperProcess -Force
        Stop-FakeWallpaperFixture
    }
}

function Capture-DesktopWorkAreaWindowedFallbackArtifact {
    $process = Start-AcceptanceProcess $script:RitualistExe @("--canvas", "minimal_desktop", "--host", "desktop-work-area") @{
        RITUALIST_CANVAS_FORCE_WINDOWED = "1"
    }
    try {
        Start-Sleep -Seconds $ScenarioDwellSeconds
        $window = Get-WindowByName "Ritualist Canvas" 10
        $screenshot = Save-Screenshot "desktop-work-area-windowed-fallback"
        $processTree = Save-ProcessTree "desktop-work-area-windowed-fallback" $process.Id
        $windowTree = Save-WindowTree "desktop-work-area-windowed-fallback" $window
        $zOrderPath = Save-ZOrderSnapshot "desktop-work-area-windowed-fallback"
        $events = Get-E2EEvents
        $hostReady = @(
            $events |
                Where-Object { $_.event -eq "canvas.host.ready" -and [int]$_.process_id -eq $process.Id } |
                Select-Object -Last 1
        )
        Add-VisualArtifact -Id "desktop-work-area-windowed-fallback" -CanvasId "minimal_desktop" -State "forced_windowed" -NonBlank (Test-ScreenshotNonBlank $screenshot) -Evidence @{
            screenshot = $screenshot
            process_tree = $processTree
            window_tree = $windowTree
            z_order = $zOrderPath
            force_windowed_env = "RITUALIST_CANVAS_FORCE_WINDOWED"
            host_ready = if ($hostReady.Count -gt 0) { $hostReady[-1] } else { $null }
            forced_windowed = if ($hostReady.Count -gt 0) { $hostReady[-1].payload.forced_windowed } else { $false }
            requested_mode = if ($hostReady.Count -gt 0) { $hostReady[-1].payload.requested_mode } else { "" }
            applied = if ($hostReady.Count -gt 0) { $hostReady[-1].payload.applied } else { "" }
            background_passthrough = if ($hostReady.Count -gt 0) { $hostReady[-1].payload.background_passthrough } else { $null }
            background_mode = if ($hostReady.Count -gt 0) { $hostReady[-1].payload.background_mode } else { $null }
        }
    }
    finally {
        Stop-AcceptanceProcess $process
    }
}

function Capture-CanvasEditModeVisualArtifact {
    $process = Start-AcceptanceProcess $script:RitualistExe @("--canvas", "gaming_desktop")
    try {
        Start-Sleep -Seconds $ScenarioDwellSeconds
        $window = Get-WindowByName "Ritualist Canvas" 10
        $editInvoked = if ($window) { Invoke-NamedButton $window "Edit Room" 10 } else { $false }
        Start-Sleep -Seconds $ScenarioDwellSeconds
        $editWindow = Get-WindowByName "Ritualist Canvas" 5
        $screenshot = Save-Screenshot "edit-mode-builder"
        $frames = Capture-ScreenFrames "edit-mode-builder" 2
        $processTree = Save-ProcessTree "edit-mode-builder" $process.Id
        $windowTree = Save-WindowTree "edit-mode-builder" $editWindow
        $zOrder = Save-ZOrderSnapshot "edit-mode-builder"
        $nonBlank = Test-ScreenshotNonBlank $screenshot
        $expectedEditControls = @("Done", "Cancel", "Ritual Card", "Save", "Undo")
        $foundEditControls = @($expectedEditControls | Where-Object { Find-NamedElement $editWindow $_ })
        $missingEditControls = @($expectedEditControls | Where-Object { $foundEditControls -notcontains $_ })
        $state = "edit-unverified"
        $status = "NEEDS_HUMAN_REVIEW"
        $message = "Edit Mode screenshot captured, but the Edit Room control was not invoked through UIA."
        if ($editInvoked -and $nonBlank -and $missingEditControls.Count -eq 0) {
            $state = "edit"
            $status = "PASS"
            $message = "Packaged Canvas Edit Mode opened with nonblank visual evidence and expected builder controls."
        }
        elseif (-not $nonBlank) {
            $status = "FAIL"
            $message = "Edit Mode artifact screenshot was blank."
        }
        elseif ($editInvoked) {
            $message = "Edit Mode screenshot captured, but builder-specific UIA controls were missing: $($missingEditControls -join ', ')."
        }
        Add-VisualArtifact -Id "edit-mode-builder" -CanvasId "gaming_desktop" -State $state -NonBlank $nonBlank -Evidence @{
            screenshot = $screenshot
            frames = $frames
            process_tree = $processTree
            window_tree = $windowTree
            z_order = $zOrder
            edit_invoked = $editInvoked
            expected_controls = $expectedEditControls
            found_controls = $foundEditControls
            missing_controls = $missingEditControls
            control_basis = "UIA-visible Edit Mode controls: top bar, palette, and properties panel action buttons."
            review_status = $status
        }
        Set-Check "edit_mode_builder_visible" $status $message @{
            screenshot = $screenshot
            frames = $frames
            process_tree = $processTree
            window_tree = $windowTree
            z_order = $zOrder
            edit_invoked = $editInvoked
            non_blank = $nonBlank
            expected_controls = $expectedEditControls
            found_controls = $foundEditControls
            missing_controls = $missingEditControls
            control_basis = "UIA-visible Edit Mode controls: top bar, palette, and properties panel action buttons."
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
        $readyEvents = @(
            Get-E2EEvents |
                Where-Object {
                    $_.event -eq "canvas.ready" -and
                    $_.payload.canvas -eq "gaming_desktop" -and
                    @($_.payload.recent_activity_component_ids) -contains "recent_activity"
                }
        )
        $recentActivityVisible = Test-WindowTreeContainsText $tree "Recent Activity"
        $buttons = @("run", "dry_run", "doctor", "preview_plan") | Where-Object {
            $window -and (Find-Button $window $_)
        }
        $rendered = $window -and (Test-ScreenshotNonBlank $initial) -and $buttons.Count -ge 4
        $componentsPresent = $rendered -and ($readyEvents.Count -gt 0)
        if ($rendered) {
            Set-Check "gaming_desktop_renders" "PASS" "gaming_desktop rendered with expected controls." @{
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
        }
        if ($componentsPresent) {
            Set-Check "expected_canvas_components_appear" "PASS" "Expected Canvas action controls and recent.activity component evidence were present." @{
                screenshot = $initial
                window_tree = $tree
                controls = $buttons
                theme = $themeEvidence
                recent_activity_ready_event = $readyEvents[0]
                recent_activity_title_visible = $recentActivityVisible
            }
        }
        else {
            Set-Check "expected_canvas_components_appear" "FAIL" "Expected Canvas controls or recent.activity component evidence were not available." @{
                screenshot = $initial
                window_tree = $tree
                controls = $buttons
                theme = $themeEvidence
                recent_activity_ready_event_count = $readyEvents.Count
                recent_activity_title_visible = $recentActivityVisible
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

        $rootHelp = Invoke-CapturedCommand "cli-help-no-recording-surface" "python" @("-m", "ritualist", "--help")
        $canvasHelp = Invoke-CapturedCommand "canvas-help-no-recording-surface" "python" @("-m", "ritualist", "canvas", "--help")
        $helpText = "$($rootHelp.stdout_text)`n$($rootHelp.stderr_text)`n$($canvasHelp.stdout_text)`n$($canvasHelp.stderr_text)"
        $helpMatches = Find-TermMatches $helpText $RecordingSurfaceTerms

        $uiRows = Get-UiTextSnapshot $window
        $uiSnapshot = Join-Path $SnapshotRoot "no-recording-ui-text.json"
        Write-JsonFile $uiSnapshot $uiRows 8 | Out-Null
        $uiText = ($uiRows | ForEach-Object { "$($_.name)`n$($_.automation_id)" }) -join "`n"
        $uiMatches = Find-TermMatches $uiText $RecordingSurfaceTerms

        $captureDataRoot = Join-Path $script:FixtureAppData "watch-me"
        $captureSessionDirs = if (Test-Path $captureDataRoot) {
            @(Get-ChildItem -Path $captureDataRoot -Directory -ErrorAction SilentlyContinue)
        }
        else {
            @()
        }
        $captureFiles = if (Test-Path $captureDataRoot) {
            @(Get-ChildItem -Path $captureDataRoot -Recurse -File -ErrorAction SilentlyContinue)
        }
        else {
            @()
        }
        $forbiddenDataMatches = @()
        if ($captureFiles.Count -gt 0) {
            foreach ($marker in $ForbiddenMarkers) {
                $match = Select-String -Path @($captureFiles | ForEach-Object { $_.FullName }) -Pattern $marker -CaseSensitive:$false -ErrorAction SilentlyContinue
                if ($match) {
                    $forbiddenDataMatches += $marker
                }
            }
        }

        $surfaceAbsent = (
            $rootHelp.exit_code -eq 0 -and
            $canvasHelp.exit_code -eq 0 -and
            $helpMatches.Count -eq 0 -and
            $uiMatches.Count -eq 0 -and
            $captureSessionDirs.Count -eq 0 -and
            $forbiddenDataMatches.Count -eq 0
        )
        if ($surfaceAbsent) {
            Set-Check "no_recording_or_preview_capture" "PASS" "No recording or preview-capture creation surface was exposed." @{
                cli_help_no_recording_surface = [ordered]@{
                    root_help_stdout = $rootHelp.stdout
                    root_help_stderr = $rootHelp.stderr
                    canvas_help_stdout = $canvasHelp.stdout
                    canvas_help_stderr = $canvasHelp.stderr
                    matches = $helpMatches
                }
                visible_text_scan_no_recording_surface = [ordered]@{
                    ui_text_snapshot = $uiSnapshot
                    matches = $uiMatches
                }
                forbidden_marker_scan = [ordered]@{
                    capture_data_root = $captureDataRoot
                    session_dirs = @($captureSessionDirs | ForEach-Object { $_.FullName })
                    files_scanned = @($captureFiles | ForEach-Object { $_.FullName })
                    matches = $forbiddenDataMatches
                }
            }
        }
        else {
            Set-Check "no_recording_or_preview_capture" "FAIL" "Recording or preview-capture surface evidence is still present." @{
                cli_help_no_recording_surface = [ordered]@{
                    root_help_stdout = $rootHelp.stdout
                    root_help_stderr = $rootHelp.stderr
                    canvas_help_stdout = $canvasHelp.stdout
                    canvas_help_stderr = $canvasHelp.stderr
                    matches = $helpMatches
                }
                visible_text_scan_no_recording_surface = [ordered]@{
                    ui_text_snapshot = $uiSnapshot
                    matches = $uiMatches
                }
                forbidden_marker_scan = [ordered]@{
                    capture_data_root = $captureDataRoot
                    session_dirs = @($captureSessionDirs | ForEach-Object { $_.FullName })
                    files_scanned = @($captureFiles | ForEach-Object { $_.FullName })
                    matches = $forbiddenDataMatches
                }
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
        $runningShot = Save-Screenshot "ui-refresh-running-state"
        $pause = Invoke-NamedButton $window "Pause" 15
        Start-Sleep -Seconds 1
        $pausedShot = Save-Screenshot "ui-refresh-paused-state"
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
            Add-VisualArtifact -Id "running-state" -CanvasId "gaming_desktop" -State "running" -NonBlank (Test-ScreenshotNonBlank $runningShot) -Evidence @{
                screenshot = $runningShot
                run_id = $run.Name
            }
            Add-VisualArtifact -Id "paused-state" -CanvasId "gaming_desktop" -State "paused" -NonBlank (Test-ScreenshotNonBlank $pausedShot) -Evidence @{
                screenshot = $pausedShot
                run_id = $run.Name
            }
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
        Add-VisualArtifact -Id "confirmation-state" -CanvasId "gaming_desktop" -State "confirmation" -NonBlank (Test-ScreenshotNonBlank $confirmationShot) -Evidence @{
            screenshot = $confirmationShot
            window_tree = $confirmationTree
            z_order = $zOrder
        }
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
        $activityShot = Save-Screenshot "recent-activity-after-decline"
        $activityTree = Save-WindowTree "recent-activity-after-decline" $window
        $activityTitleVisible = Test-WindowTreeContainsText $activityTree "Recent Activity"
        $readyEvents = @(
            Get-E2EEvents |
                Where-Object {
                    $_.event -eq "canvas.ready" -and
                    $_.payload.canvas -eq "gaming_desktop" -and
                    @($_.payload.recent_activity_component_ids) -contains "recent_activity"
                }
        )
        $runsCommand = if ($run) {
            Invoke-CapturedCommand "runs-after-decline" "python" @("-m", "ritualist", "runs", "--limit", "5", "--no-repair")
        }
        else {
            $null
        }
        $runHistoryContainsRun = $false
        if ($run -and $runsCommand) {
            $runHistoryContainsRun = $runsCommand.stdout_text -match ([regex]::Escape($run.Name))
        }
        $recentActivityModel = if ($run) {
            Get-RecentActivityModelEvidence -ProcessId $process.Id -RunId $run.Name
        }
        else {
            [ordered]@{
                process_id = $process.Id
                run_id = $null
                heartbeat_event_count = 0
                matching_event_count = 0
                contains_run = $false
            }
        }
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
            if ($readyEvents.Count -gt 0 -and $runHistoryContainsRun -and $recentActivityModel.contains_run) {
                Set-Check "recent_activity_updates" "PASS" "Packaged Canvas recent.activity model and fixture run history record the declined stopped run." @{
                    run_id = $run.Name
                    run_log = $runEvidence
                    screenshot = $activityShot
                    window_tree = $activityTree
                    activity_title_visible = $activityTitleVisible
                    canvas_ready_event = $readyEvents[0]
                    recent_activity_model = $recentActivityModel
                    runs_stdout = $runsCommand.stdout
                    runs_stderr = $runsCommand.stderr
                }
            }
            else {
                Set-Check "recent_activity_updates" "NEEDS_HUMAN_REVIEW" "Run history exists, but packaged recent.activity model evidence was incomplete." @{
                    run_id = $run.Name
                    run_log = $runEvidence
                    screenshot = $activityShot
                    window_tree = $activityTree
                    activity_title_visible = $activityTitleVisible
                    canvas_ready_event_count = $readyEvents.Count
                    recent_activity_model = $recentActivityModel
                    run_history_contains_run = $runHistoryContainsRun
                    runs_stdout = if ($runsCommand) { $runsCommand.stdout } else { $null }
                    runs_stderr = if ($runsCommand) { $runsCommand.stderr } else { $null }
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
            Set-Check "recent_activity_updates" "FAIL" "Recent activity could not be asserted because the declined run log was missing or did not stop cleanly." @{
                run_id = if ($run) { $run.Name } else { $null }
                run_log = $runEvidence
                screenshot = $activityShot
                window_tree = $activityTree
                activity_title_visible = $activityTitleVisible
                canvas_ready_event_count = $readyEvents.Count
                recent_activity_model = $recentActivityModel
                run_history_contains_run = $runHistoryContainsRun
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
    $heartbeatProcess = Start-AcceptanceProcess $script:RitualistExe @("--canvas", "gaming_desktop")
    $heartbeatWindow = $null
    $heartbeatShot = $null
    $heartbeatTree = $null
    $frames = $null
    $frameTiming = $null
    $appHeartbeatTiming = $null
    try {
        Start-Sleep -Seconds 5
        $heartbeatWindow = Get-WindowByName "Ritualist Canvas" 15
        $heartbeatShot = Save-Screenshot "perf-heartbeat-canvas"
        $heartbeatTree = Save-WindowTree "perf-heartbeat-canvas" $heartbeatWindow
        $frames = Capture-ScreenFrames "perf-heartbeat-sample" 3
        Start-Sleep -Milliseconds 500
        $frameTiming = Get-FrameTimingEvidence $frames
        $appHeartbeatTiming = Get-UiHeartbeatTimingEvidence -ProcessId $heartbeatProcess.Id
    }
    finally {
        Stop-AcceptanceProcess $heartbeatProcess
    }
    $ok = $perf100.exit_code -eq 0 -and $perf300.exit_code -eq 0
    if ($ok) {
            Set-Check "component_perf_100_300_recorded" "PASS" "Source CLI 100/300 component perf outputs were recorded." @{
            perf_100_stdout = $perf100.stdout
            perf_300_stdout = $perf300.stdout
            heartbeat_screenshot = $heartbeatShot
            heartbeat_window_tree = $heartbeatTree
            frames = $frames
            frame_timing = $frameTiming
            app_heartbeat_timing = $appHeartbeatTiming
        }
        $heartbeatNonBlank = $heartbeatShot -and (Test-ScreenshotNonBlank $heartbeatShot)
        if (
            $heartbeatWindow -and
            $heartbeatNonBlank -and
            $frameTiming.available -and
            $frameTiming.passed -and
            $appHeartbeatTiming.available -and
            $appHeartbeatTiming.passed
        ) {
            Set-Check "ui_heartbeat_no_obvious_freeze" "PASS" "Packaged Canvas emitted bounded QML heartbeat events while frame timing captured no long gap." @{
                heartbeat_screenshot = $heartbeatShot
                heartbeat_window_tree = $heartbeatTree
                frames = $frames
                frame_timing = $frameTiming
                app_heartbeat_timing = $appHeartbeatTiming
                e2e_dir = $E2ERoot
            }
        }
        else {
            Set-Check "ui_heartbeat_no_obvious_freeze" "NEEDS_HUMAN_REVIEW" "Canvas heartbeat or frame timing evidence was missing or exceeded the conservative gap threshold." @{
                heartbeat_screenshot = $heartbeatShot
                heartbeat_window_tree = $heartbeatTree
                heartbeat_nonblank = $heartbeatNonBlank
                frames = $frames
                frame_timing = $frameTiming
                app_heartbeat_timing = $appHeartbeatTiming
                e2e_dir = $E2ERoot
            }
        }
    }
    else {
        Set-Check "component_perf_100_300_recorded" "FAIL" "Perf commands failed." @{
            perf_100_stdout = $perf100.stdout
            perf_100_stderr = $perf100.stderr
            perf_300_stdout = $perf300.stdout
            perf_300_stderr = $perf300.stderr
        }
        Set-Check "ui_heartbeat_no_obvious_freeze" "FAIL" "Perf command failure prevents heartbeat/render timing confidence." @{
            frame_timing = $frameTiming
            app_heartbeat_timing = $appHeartbeatTiming
        }
    }
}

function Set-RemainingReviewChecks {
    if (-not $Results.Contains("recent_activity_updates")) {
        $runsCommand = Invoke-CapturedCommand "runs-after-acceptance" "python" @("-m", "ritualist", "runs", "--limit", "5", "--no-repair")
        Set-Check "recent_activity_updates" "NEEDS_HUMAN_REVIEW" "Source CLI run history was captured, but packaged recent.activity evidence was not produced." @{
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
        visual_artifacts = @($script:VisualArtifacts)
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
    if ($script:VisualArtifacts.Count -gt 0) {
        $lines += ""
        $lines += "## Visual Artifacts"
        foreach ($artifact in $script:VisualArtifacts) {
            $shot = $artifact.evidence.screenshot
            $lines += "- ``$($artifact.id)`` ($($artifact.canvas_id), $($artifact.state)): ``$shot``"
        }
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
    Capture-CanvasVisualArtifact -CanvasId "minimal_desktop" -ArtifactId "minimal-room"
    Capture-CanvasVisualArtifact -CanvasId "gaming_desktop" -ArtifactId "gaming-room"
    Capture-CanvasVisualArtifact -CanvasId "helpdesk_desktop" -ArtifactId "support-desk"
    Capture-DesktopWorkAreaCanvasArtifact
    Capture-DesktopWorkAreaWindowedFallbackArtifact
    Capture-CanvasEditModeVisualArtifact
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
    Stop-FakeWallpaperFixture
    Write-Summaries
}

Write-Host "Acceptance summary JSON: $SummaryJson"
Write-Host "Acceptance summary Markdown: $SummaryMd"
exit (@($Results.Values | Where-Object { $_.status -eq "FAIL" }).Count)
