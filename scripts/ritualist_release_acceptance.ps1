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

function Set-ForegroundProcessWindow {
    param(
        [System.Diagnostics.Process]$Process,
        [string]$Title
    )
    if (-not $Process) {
        return $false
    }
    for ($attempt = 0; $attempt -lt 10; $attempt += 1) {
        $Process.Refresh()
        $handle = $Process.MainWindowHandle
        if ($handle -eq [System.IntPtr]::Zero) {
            $row = @(
                Get-TopLevelWindows |
                    Where-Object {
                        [int64]$_.process_id -eq [int64]$Process.Id -and
                        ([string]::IsNullOrWhiteSpace($Title) -or $_.title -eq $Title)
                    } |
                    Select-Object -First 1
            )
            if ($row.Count -gt 0) {
                $handle = [System.IntPtr]::new([int64]$row[0].hwnd)
            }
        }
        if ($handle -ne [System.IntPtr]::Zero) {
            [void][RitualistAcceptanceWin32]::ShowWindow($handle, 9)
            [void][RitualistAcceptanceWin32]::SetForegroundWindow($handle)
            Start-Sleep -Milliseconds 500
            return $true
        }
        Start-Sleep -Milliseconds 250
    }
    return $false
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

function Find-AnyButton {
    param([object]$Window, [string[]]$Names)
    foreach ($name in $Names) {
        $button = Find-Button $Window $name
        if ($button) {
            return $button
        }
    }
    return $null
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

function Invoke-AnyNamedButton {
    param([object]$Window, [string[]]$Names, [int]$TimeoutSeconds = 15)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $button = Find-AnyButton $Window $Names
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

function Wait-ProcessExit {
    param([int]$ProcessId, [int]$TimeoutSeconds = 10)
    if ($ProcessId -le 0) {
        return $true
    }
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
        if (-not $process) {
            return $true
        }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $deadline)
    return -not [bool](Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)
}

function Stop-RunOwnerProcess {
    param([string]$RunId)
    $metadata = if ($RunId) { Read-RunJson $RunId } else { $null }
    $runProcessId = 0
    if ($metadata -and $metadata.process_id) {
        $runProcessId = [int]$metadata.process_id
    }
    $wasRunning = if ($runProcessId -gt 0) { [bool](Get-Process -Id $runProcessId -ErrorAction SilentlyContinue) } else { $false }
    if ($wasRunning) {
        Stop-Process -Id $runProcessId -Force -ErrorAction SilentlyContinue
    }
    $exited = if ($runProcessId -gt 0) { Wait-ProcessExit $runProcessId 10 } else { $false }
    return [ordered]@{
        run_id = $RunId
        process_id = $runProcessId
        process_was_running = $wasRunning
        process_exited = $exited
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

function Wait-RunStatus {
    param([string]$RunId, [string]$Status, [int]$TimeoutSeconds = 20)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $metadata = Read-RunJson $RunId
        if ($metadata -and $metadata.status -eq $Status) {
            return $metadata
        }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    return Read-RunJson $RunId
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

function Wait-CanvasStatusEvent {
    param(
        [string]$ComponentId,
        [string]$MessagePattern,
        [string]$Status = "success",
        [int]$TimeoutSeconds = 15
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $event = Get-CanvasStatusEvents $ComponentId |
            Where-Object {
                $_.payload.status -eq $Status -and
                $_.payload.message -match $MessagePattern
            } |
            Select-Object -First 1
        if ($event) {
            return $event
        }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $deadline)
    return $null
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

function Convert-CommandJson {
    param([object]$Command)
    if (-not $Command -or [string]::IsNullOrWhiteSpace($Command.stdout_text)) {
        return $null
    }
    try {
        return $Command.stdout_text | ConvertFrom-Json -ErrorAction Stop
    }
    catch {
        return $null
    }
}

function Get-RunDirectoryNames {
    $runs = Join-Path $script:FixtureAppData "runs"
    if (-not (Test-Path $runs)) {
        return @()
    }
    return @(Get-ChildItem -Path $runs -Directory | ForEach-Object { $_.Name })
}

function Test-StringContainsAny {
    param([string]$Text, [string[]]$Terms)
    foreach ($term in $Terms) {
        if ($Text -match [regex]::Escape($term)) {
            return $true
        }
    }
    return $false
}

function New-ProjectRoomShortcutFixture {
    $fixtureProject = Join-Path $FixtureRoot "project-room-fixture"
    $fixtureApps = Join-Path $FixtureRoot "project-room-apps"
    New-Item -ItemType Directory -Force -Path @($fixtureProject, $fixtureApps) | Out-Null
    $fakeEditor = Join-Path $fixtureApps "Code.exe"
    $fakeTerminal = Join-Path $fixtureApps "wt.exe"
    if (-not (Test-Path $fakeEditor)) {
        "" | Set-Content -Path $fakeEditor -Encoding UTF8
    }
    if (-not (Test-Path $fakeTerminal)) {
        "" | Set-Content -Path $fakeTerminal -Encoding UTF8
    }

    $source = Join-Path $RepoRoot "ritualist\sample_canvases\project_room.yaml"
    $fixtureCanvas = Join-Path $FixtureRoot "project_room_shortcuts_ready.yaml"
    $text = Get-Content -Path $source -Raw
    $text = $text.Replace("'~/Documents/Project'", "'$fixtureProject'")
    $text = $text.Replace("'C:\Program Files\Microsoft VS Code\Code.exe'", "'$fakeEditor'")
    $text = $text.Replace("'C:\Program Files\Windows Terminal\wt.exe'", "'$fakeTerminal'")
    $text | Set-Content -Path $fixtureCanvas -Encoding UTF8
    $script:ProjectRoomShortcutFixtureCanvas = $fixtureCanvas
    return [ordered]@{
        canvas = $fixtureCanvas
        project_folder = $fixtureProject
        fake_editor = $fakeEditor
        fake_terminal = $fakeTerminal
    }
}

function Invoke-RoomPickerEvidence {
    $process = Start-AcceptanceProcess $script:RitualistExe @()
    try {
        Start-Sleep -Seconds $ScenarioDwellSeconds
        $window = Get-WindowByName "Ritualist Home" 10
        $screenshot = Save-Screenshot "room-picker"
        $frames = Capture-ScreenFrames "room-picker" 2
        $windowTree = Save-WindowTree "room-picker" $window
        $processTree = Save-ProcessTree "room-picker" $process.Id
        $zOrderPath = Save-ZOrderSnapshot "room-picker"
        $zRows = Get-Content -Path $zOrderPath -Raw | ConvertFrom-Json
        $screen = Get-PrimaryScreenGeometry
        $homeRow = $zRows | Where-Object { [int64]$_.process_id -eq [int64]$process.Id -and $_.title -eq "Ritualist Home" } | Select-Object -First 1
        $notFullscreen = if ($homeRow) { -not (Test-BoundsMatch $homeRow.bounds $screen.bounds 3) } else { $false }
        $taskbarVisibleByWorkArea = (
            [int]$screen.work_area.width -lt [int]$screen.bounds.width -or
            [int]$screen.work_area.height -lt [int]$screen.bounds.height
        )

        $roomList = Invoke-CapturedCommand "room-list" "python" @("-m", "ritualist", "room", "list", "--json")
        $roomPayload = Convert-CommandJson $roomList
        $roomIds = @()
        $roomNames = @()
        $canvasIds = @()
        if ($roomPayload) {
            $roomIds = @($roomPayload.rooms | ForEach-Object { $_.id })
            $roomNames = @($roomPayload.rooms | ForEach-Object { $_.name })
            $canvasIds = @($roomPayload.rooms | ForEach-Object { $_.canvas_id })
        }
        $expectedIds = @("gaming", "project", "support_desk")
        $expectedNames = @("Gaming Room", "Project Room", "Support Desk")
        $exactRooms = (
            ($roomIds -join "|") -eq ($expectedIds -join "|") -and
            ($roomNames -join "|") -eq ($expectedNames -join "|") -and
            ($canvasIds -notcontains "minimal_desktop")
        )
        $namesVisible = @($expectedNames | Where-Object { Test-WindowTreeContainsText $windowTree $_ })
        $nonBlank = Test-ScreenshotNonBlank $screenshot
        $evidence = @{
            screenshot = $screenshot
            frames = $frames
            process_tree = $processTree
            window_tree = $windowTree
            z_order = $zOrderPath
            screen_geometry = $screen
            window_bounds = if ($homeRow) { $homeRow.bounds } else { $null }
            not_fullscreen = $notFullscreen
            taskbar_visible_by_work_area = $taskbarVisibleByWorkArea
            room_list_stdout = $roomList.stdout
            room_list_stderr = $roomList.stderr
            promoted_room_ids = $roomIds
            promoted_room_names = $roomNames
            promoted_canvas_ids = $canvasIds
            exact_three_promoted_rooms = $exactRooms
            minimal_desktop_promoted = ($canvasIds -contains "minimal_desktop")
            visible_room_names = $namesVisible
            non_blank = $nonBlank
        }
        if ($exactRooms -and $notFullscreen -and $taskbarVisibleByWorkArea -and $nonBlank) {
            Set-Check "room_picker_three_heroes_taskbar_visible" "PASS" "Packaged Home Room picker is windowed, taskbar-preserving, and promotes exactly three hero Rooms." $evidence
        }
        elseif (-not $exactRooms -or -not $notFullscreen -or -not $nonBlank) {
            Set-Check "room_picker_three_heroes_taskbar_visible" "FAIL" "Room picker contract failed machine checks." $evidence
        }
        else {
            Set-Check "room_picker_three_heroes_taskbar_visible" "NEEDS_HUMAN_REVIEW" "Room picker contract passed except taskbar visibility was not machine-observable, usually because the OS work area matches the screen bounds." $evidence
        }
    }
    finally {
        Stop-AcceptanceProcess $process
    }
}

function Invoke-StateUiFixtureEvidence {
    $probe = Join-Path $CommandRoot "state_ui_fixture_probe.py"
    $output = Join-Path $SnapshotRoot "state-ui-fixtures.json"
    @'
import json
import sys

from ritualist.canvas import CanvasRuntimeContext, build_canvas_runtime_model, load_bundled_canvas


def component_state(canvas_id, recipe_id, runtime_state):
    canvas = load_bundled_canvas(canvas_id)
    model = build_canvas_runtime_model(
        canvas,
        context=CanvasRuntimeContext(
            recipe_ids={recipe_id},
            target_ids={"diablo_iv"},
            runtime_state={recipe_id: runtime_state} if runtime_state else {},
            recent_runs=(),
        ),
    )
    component_id = "run_status" if canvas_id != "project_room" else "coding_status"
    controller_id = "run_controller" if canvas_id != "project_room" else "coding_controller"
    status_state = model.component_state(component_id).to_dict()
    controller_state = model.component_state(controller_id).to_dict()
    return {
        "status": status_state,
        "controller": controller_state,
        "ritual_state": status_state["data"].get("ritual_state", {}),
    }


def active_state(state, **extra):
    payload = {
        "run_id": f"fixture-{state}",
        "state": state,
        "message": extra.pop("message", state),
        "current_step": extra.pop("current_step", state.title()),
        "current_step_state": state,
    }
    payload.update(extra)
    return payload


fixtures = {
    "ready": component_state("gaming_desktop", "gaming_mode", {}),
    "running": component_state(
        "gaming_desktop",
        "gaming_mode",
        active_state("running", message="opening local setup", current_step="Open references"),
    ),
    "waiting": component_state(
        "gaming_desktop",
        "gaming_mode",
        active_state(
            "waiting",
            message="waiting for operator",
            current_step="Wait for manual readiness",
            wait={"target": "operator confirmation", "elapsed_seconds": 2.0, "timeout_seconds": 60.0},
        ),
    ),
    "confirming": component_state(
        "gaming_desktop",
        "gaming_mode",
        active_state(
            "confirming",
            message="native confirmation required",
            current_step="Ask before clicking Play",
            confirmation={
                "required": True,
                "step_index": 3,
                "step_name": "Ask before clicking Play",
                "action": "desktop.click_text",
                "target": "Play",
                "target_type": "button",
                "message": "Confirm before clicking Play",
            },
        ),
    ),
    "paused": component_state(
        "gaming_desktop",
        "gaming_mode",
        active_state(
            "paused",
            message="paused by operator",
            current_step="Control checkpoint",
            paused={"active": True, "reason": "operator requested pause"},
        ),
    ),
    "failed": component_state(
        "project_room",
        "coding_mode",
        active_state("failed", message="fixture failure", current_step="Open documentation"),
    ),
    "interrupted": component_state(
        "helpdesk_desktop",
        "support_triage_workspace",
        active_state("interrupted", message="fixture interrupted", current_step="Open Logs / Evidence"),
    ),
}
states = sorted(fixtures)
payload = {
    "schema": "ritualist.acceptance.state_ui_fixture.v1",
    "states": states,
    "fixtures": fixtures,
    "forbidden_capture": {
        "screenshots": False,
        "ocr": False,
        "keylogging": False,
        "coordinate_capture": False,
        "browser_history": False,
    },
}
with open(sys.argv[1], "w", encoding="utf-8") as fh:
    json.dump(payload, fh, indent=2)
print(json.dumps({"path": sys.argv[1], "states": states}))
'@ | Set-Content -Path $probe -Encoding UTF8

    $command = Invoke-CapturedCommand "state-ui-fixture" "python" @($probe, $output)
    $payload = if (Test-Path $output) { Get-Content -Path $output -Raw | ConvertFrom-Json } else { $null }
    $expectedStates = @("ready", "running", "waiting", "confirming", "paused", "failed", "interrupted")
    $observedStates = if ($payload) { @($payload.states) } else { @() }
    $hasStates = (($observedStates | Sort-Object) -join "|") -eq (($expectedStates | Sort-Object) -join "|")
    $hasRitualState = $false
    if ($payload) {
        $hasRitualState = [bool](
            $payload.fixtures.ready.status.data.ritual_state.schema_version -and
            $payload.fixtures.confirming.status.data.ritual_state.active_run.confirmation.required -and
            $payload.fixtures.paused.status.data.ritual_state.active_run.paused.active
        )
    }
    $script:StateUiFixturePath = $output
    if ($command.exit_code -eq 0 -and $hasStates -and $hasRitualState) {
        Set-Check "state_ui_fixture_evidence" "PASS" "State UI fixture recorded ready, running, waiting, confirming, paused, failed, and interrupted states." @{
            state_fixture_json = $output
            command_stdout = $command.stdout
            command_stderr = $command.stderr
            observed_states = $observedStates
            visual_artifact_references = @($script:VisualArtifacts | ForEach-Object { $_.id })
        }
    }
    else {
        Set-Check "state_ui_fixture_evidence" "FAIL" "State UI fixture evidence was missing expected states or ritual_state data." @{
            state_fixture_json = $output
            command_stdout = $command.stdout
            command_stderr = $command.stderr
            exit_code = $command.exit_code
            observed_states = $observedStates
            has_ritual_state = $hasRitualState
        }
    }
}

function Invoke-HeroRoomEvidence {
    $projectFixture = New-ProjectRoomShortcutFixture
    $projectProcess = Start-AcceptanceProcess $script:RitualistExe @("--canvas", $script:ProjectRoomShortcutFixtureCanvas)
    $projectEvidence = @{}
    try {
        Start-Sleep -Seconds $ScenarioDwellSeconds
        $window = Get-WindowByName "Ritualist Canvas" 10
        $screenshot = Save-Screenshot "project-room"
        $windowTree = Save-WindowTree "project-room" $window
        $processTree = Save-ProcessTree "project-room" $projectProcess.Id
        $zOrder = Save-ZOrderSnapshot "project-room"
        $roomShow = Invoke-CapturedCommand "project-room-show" "python" @("-m", "ritualist", "room", "show", "project", "--json")
        $doctor = Invoke-CapturedCommand "coding-mode-doctor" "python" @("-m", "ritualist", "doctor", "ritualist\sample_recipes\coding_mode.yaml", "--json", "--no-strict")
        $dryRun = Invoke-CapturedCommand "coding-mode-dry-run" "python" @("-m", "ritualist", "dry-run", "ritualist\sample_recipes\coding_mode.yaml")
        $beforeRuns = Get-RunDirectoryNames
        $folderDryRun = Invoke-CapturedCommand "project-folder-shortcut-dry-run" "python" @("-m", "ritualist", "canvas", "action", $script:ProjectRoomShortcutFixtureCanvas, "project_folder", "open", "--dry-run", "--json")
        $afterRuns = Get-RunDirectoryNames
        $roomPayload = Convert-CommandJson $roomShow
        $componentIds = if ($roomPayload) { @($roomPayload.canvas.components | ForEach-Object { $_.id }) } else { @() }
        $componentTypes = @{}
        $componentTitles = @{}
        if ($roomPayload) {
            foreach ($component in $roomPayload.canvas.components) {
                $componentTypes[$component.id] = $component.type
                $componentTitles[$component.id] = $component.props.title
            }
        }
        $requiredShortcutIds = @("project_folder", "editor_shortcut", "terminal_shortcut", "docs_shortcut")
        $shortcutsPresent = @($requiredShortcutIds | Where-Object { $componentIds -contains $_ })
        $shortcutControls = @($requiredShortcutIds | ForEach-Object { $componentTitles[$_] } | Where-Object { $_ })
        $expectedShortcutTitles = @("Project Folder", "Editor", "Terminal", "Docs")
        $shortcutTitlesPresent = @($expectedShortcutTitles | Where-Object { $shortcutControls -contains $_ })
        $requiredActionControls = @("Open Folder", "Launch App", "Open URL")
        $shortcutActionControls = @($requiredActionControls | Where-Object { Test-WindowTreeContainsText $windowTree $_ })
        $folderShortcutNoRunLog = (($afterRuns -join "|") -eq ($beforeRuns -join "|"))
        $projectEvidence = @{
            screenshot = $screenshot
            window_tree = $windowTree
            process_tree = $processTree
            z_order = $zOrder
            shortcut_fixture = $projectFixture
            room_show_stdout = $roomShow.stdout
            room_show_stderr = $roomShow.stderr
            coding_mode_doctor_json = $doctor.stdout
            coding_mode_doctor_stderr = $doctor.stderr
            coding_mode_dry_run_output = $dryRun.stdout
            coding_mode_dry_run_stderr = $dryRun.stderr
            project_folder_shortcut_dry_run_stdout = $folderDryRun.stdout
            project_folder_shortcut_dry_run_stderr = $folderDryRun.stderr
            shortcut_component_ids = $shortcutsPresent
            shortcut_control_names = $shortcutControls
            expected_shortcut_control_names = $expectedShortcutTitles
            shortcut_action_controls = $shortcutActionControls
            required_shortcut_action_controls = $requiredActionControls
            component_types = $componentTypes
            folder_shortcut_no_run_log = $folderShortcutNoRunLog
            run_dirs_before_shortcut = $beforeRuns
            run_dirs_after_shortcut = $afterRuns
            runtime_state_fixture = $script:StateUiFixturePath
        }
        if (
            $window -and
            (Test-ScreenshotNonBlank $screenshot) -and
            $roomShow.exit_code -eq 0 -and
            $doctor.exit_code -eq 0 -and
            $dryRun.exit_code -eq 0 -and
            $folderDryRun.exit_code -eq 0 -and
            $shortcutsPresent.Count -eq $requiredShortcutIds.Count -and
            $shortcutTitlesPresent.Count -eq $expectedShortcutTitles.Count -and
            $shortcutActionControls.Count -eq $requiredActionControls.Count -and
            $folderShortcutNoRunLog
        ) {
            Set-Check "project_room_acceptance" "PASS" "Project Room packaged evidence, Coding Mode Doctor/Dry Run, shortcuts, and no-run-log folder shortcut evidence were recorded." $projectEvidence
        }
        else {
            Set-Check "project_room_acceptance" "FAIL" "Project Room acceptance evidence was incomplete." $projectEvidence
        }
    }
    finally {
        Stop-AcceptanceProcess $projectProcess
    }

    $supportProcess = Start-AcceptanceProcess $script:RitualistExe @("--canvas", "helpdesk_desktop")
    try {
        Start-Sleep -Seconds $ScenarioDwellSeconds
        $window = Get-WindowByName "Ritualist Canvas" 10
        $screenshot = Save-Screenshot "support-desk"
        $windowTree = Save-WindowTree "support-desk" $window
        $processTree = Save-ProcessTree "support-desk" $supportProcess.Id
        $zOrder = Save-ZOrderSnapshot "support-desk"
        $roomShow = Invoke-CapturedCommand "support-desk-show" "python" @("-m", "ritualist", "room", "show", "support_desk", "--json")
        $diagnosticsDryRun = Invoke-CapturedCommand "support-diagnostics-dry-run" "python" @("-m", "ritualist", "dry-run", "ritualist\sample_recipes\collect_basic_diagnostics.yaml")
        $audioDryRun = Invoke-CapturedCommand "support-audio-dry-run" "python" @("-m", "ritualist", "dry-run", "ritualist\sample_recipes\meeting_audio_troubleshooting.yaml")
        $roomPayload = Convert-CommandJson $roomShow
        $runbookCards = @()
        if ($roomPayload) {
            $runbookCards = @(
                $roomPayload.canvas.components |
                    Where-Object { $_.type -eq "ritual.card" } |
                    ForEach-Object { $_.props.title }
            )
        }
        $expectedCards = @("Support Triage", "Collect Basic Diagnostics", "Meeting Audio Troubleshooting", "VPN Repair", "New Hire Setup")
        $cardsPresent = @($expectedCards | Where-Object { $runbookCards -contains $_ })
        $vpnText = Get-Content -Path (Join-Path $RepoRoot "ritualist\sample_recipes\vpn_repair_placeholder.yaml") -Raw
        $newHireText = Get-Content -Path (Join-Path $RepoRoot "ritualist\sample_recipes\new_hire_setup_draft.yaml") -Raw
        $forbiddenPlaceholderTerms = @("netsh", "ipconfig", "rasdial", "remove-vpnconnection", "set-vpnconnection", "password", "credential", "winget", "msiexec", "choco", "install-package", "new-aduser", "dsadd")
        $placeholderStaticScan = [ordered]@{
            vpn_mentions_placeholder = ($vpnText -match "placeholder")
            new_hire_mentions_draft = ($newHireText -match "draft")
            forbidden_terms_present = Test-StringContainsAny (($vpnText + "`n" + $newHireText).ToLowerInvariant()) $forbiddenPlaceholderTerms
            forbidden_terms = $forbiddenPlaceholderTerms
        }
        $supportEvidence = @{
            screenshot = $screenshot
            window_tree = $windowTree
            process_tree = $processTree
            z_order = $zOrder
            room_show_stdout = $roomShow.stdout
            room_show_stderr = $roomShow.stderr
            five_runbook_cards = $runbookCards
            expected_runbook_cards = $expectedCards
            diagnostics_dry_run_output = $diagnosticsDryRun.stdout
            diagnostics_dry_run_stderr = $diagnosticsDryRun.stderr
            audio_dry_run_output = $audioDryRun.stdout
            audio_dry_run_stderr = $audioDryRun.stderr
            placeholder_static_scan = $placeholderStaticScan
            runtime_state_fixture = $script:StateUiFixturePath
            log_evidence_basis = "Dry-run command transcripts and runtime-state fixture; no support portal or VPN dependency."
        }
        if (
            $window -and
            (Test-ScreenshotNonBlank $screenshot) -and
            $roomShow.exit_code -eq 0 -and
            $diagnosticsDryRun.exit_code -eq 0 -and
            $audioDryRun.exit_code -eq 0 -and
            $cardsPresent.Count -eq $expectedCards.Count -and
            $placeholderStaticScan.vpn_mentions_placeholder -and
            $placeholderStaticScan.new_hire_mentions_draft -and
            -not $placeholderStaticScan.forbidden_terms_present
        ) {
            Set-Check "support_desk_acceptance" "PASS" "Support Desk packaged evidence, five runbook cards, dry-runs, placeholder scans, and log evidence were recorded." $supportEvidence
        }
        else {
            Set-Check "support_desk_acceptance" "FAIL" "Support Desk acceptance evidence was incomplete." $supportEvidence
        }
    }
    finally {
        Stop-AcceptanceProcess $supportProcess
    }
}

function Set-GamingRoomAggregateEvidence {
    $roomShow = Invoke-CapturedCommand "gaming-room-show" "python" @("-m", "ritualist", "room", "show", "gaming", "--json")
    $required = @(
        "gaming_desktop_renders",
        "expected_canvas_components_appear",
        "ritual_card_doctor",
        "ritual_card_dry_run",
        "safe_ritual_card_run",
        "ritual_status_updates",
        "ritual_controller_pause_resume_stop",
        "target_card_preview",
        "recent_activity_updates",
        "native_confirmation_z_order",
        "declining_play_stopped",
        "show_run_declined_confirmation",
        "hard_kill_repairs_interrupted"
    )
    $checkStates = [ordered]@{}
    foreach ($id in $required) {
        if ($Results.Contains($id)) {
            $checkStates[$id] = $Results[$id].status
        }
        else {
            $checkStates[$id] = "MISSING"
        }
    }
    $hasFailure = @($checkStates.Values | Where-Object { $_ -eq "FAIL" -or $_ -eq "MISSING" }).Count -gt 0
    $hasReview = @($checkStates.Values | Where-Object { $_ -eq "NEEDS_HUMAN_REVIEW" }).Count -gt 0
    $status = if ($hasFailure) { "FAIL" } elseif ($hasReview) { "NEEDS_HUMAN_REVIEW" } else { "PASS" }
    $message = if ($status -eq "PASS") {
        "Gaming Room hero flow evidence is complete across packaged render, Doctor, Dry Run, Run, status, controls, preview, confirmation, recovery, and recent activity checks."
    }
    elseif ($status -eq "NEEDS_HUMAN_REVIEW") {
        "Gaming Room hero flow has machine evidence but one or more checks still need human review."
    }
    else {
        "Gaming Room hero flow evidence has failing or missing required checks."
    }
    Set-Check "gaming_room_acceptance" $status $message @{
        room_show_stdout = $roomShow.stdout
        room_show_stderr = $roomShow.stderr
        required_check_statuses = $checkStates
        visual_artifact_references = @($script:VisualArtifacts | Where-Object { $_.canvas_id -eq "gaming_desktop" } | ForEach-Object { $_.id })
    }
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
        $focusedCanvas = Set-ForegroundProcessWindow $process "Ritualist Canvas"
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
            canvas_focused_before_capture = $focusedCanvas
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

function Capture-HeroDesktopWorkAreaArtifacts {
    $heroes = @(
        [ordered]@{ room_id = "gaming"; canvas_id = "gaming_desktop"; artifact_id = "gaming-room-desktop-work-area" },
        [ordered]@{ room_id = "project"; canvas_id = $script:ProjectRoomShortcutFixtureCanvas; artifact_id = "project-room-desktop-work-area" },
        [ordered]@{ room_id = "support_desk"; canvas_id = "helpdesk_desktop"; artifact_id = "support-desk-desktop-work-area" }
    )
    $fakeWallpaperProcess = $null
    $entries = @()
    try {
        $fakeWallpaperProcess = Start-FakeWallpaperFixture
        foreach ($hero in $heroes) {
            $process = Start-AcceptanceProcess $script:RitualistExe @("--canvas", $hero.canvas_id, "--host", "desktop-work-area")
            try {
                Start-Sleep -Seconds $ScenarioDwellSeconds
                $window = Get-WindowByName "Ritualist Canvas" 10
                $fakeWallpaperWindow = Get-WindowByName $FakeWallpaperTitle 2
                $focusedCanvas = Set-ForegroundProcessWindow $process "Ritualist Canvas"
                $screenshot = Save-Screenshot $hero.artifact_id
                $frames = Capture-ScreenFrames $hero.artifact_id 2
                $processTree = Save-ProcessTree $hero.artifact_id $process.Id
                $windowTree = Save-WindowTree $hero.artifact_id $window
                $zOrderPath = Save-ZOrderSnapshot $hero.artifact_id
                $zOrder = Get-Content -Path $zOrderPath -Raw | ConvertFrom-Json
                $screen = Get-PrimaryScreenGeometry
                $windowRow = @($zOrder | Where-Object { [int64]$_.process_id -eq [int64]$process.Id -and $_.title -eq "Ritualist Canvas" } | Select-Object -First 1)
                $events = Get-E2EEvents
                $hostReady = @(
                    $events |
                        Where-Object { $_.event -eq "canvas.host.ready" -and [int]$_.process_id -eq $process.Id } |
                        Select-Object -Last 1
                )
                $entry = [ordered]@{
                    room_id = $hero.room_id
                    canvas_id = $hero.canvas_id
                    artifact_id = $hero.artifact_id
                    screenshot = $screenshot
                    frames = $frames
                    process_tree = $processTree
                    window_tree = $windowTree
                    z_order = $zOrderPath
                    screen_geometry = $screen
                    window_bounds = if ($windowRow) { $windowRow.bounds } else { $null }
                    bounds_match_work_area = if ($windowRow) { Test-BoundsMatch $windowRow.bounds $screen.work_area } else { $false }
                    non_blank = Test-ScreenshotNonBlank $screenshot
                    canvas_focused_before_capture = $focusedCanvas
                    fake_wallpaper_fixture_visible = [bool]$fakeWallpaperWindow
                    taskbar_visible_by_work_area = (
                        [int]$screen.work_area.width -lt [int]$screen.bounds.width -or
                        [int]$screen.work_area.height -lt [int]$screen.bounds.height
                    )
                    host_ready = if ($hostReady.Count -gt 0) { $hostReady[-1] } else { $null }
                    background_passthrough = if ($hostReady.Count -gt 0) { $hostReady[-1].payload.background_passthrough } else { $null }
                    background_mode = if ($hostReady.Count -gt 0) { $hostReady[-1].payload.background_mode } else { $null }
                    click_through_implemented = if ($hostReady.Count -gt 0) { $hostReady[-1].payload.click_through_implemented } else { $null }
                    blank_area_click_through_status = if ($hostReady.Count -gt 0) { $hostReady[-1].payload.blank_area_click_through_status } else { "NEEDS_HUMAN_REVIEW" }
                    blank_area_click_through_machine_verified = if ($hostReady.Count -gt 0) { $hostReady[-1].payload.blank_area_click_through_machine_verified } else { $false }
                }
                $entries += $entry
                Add-VisualArtifact -Id $hero.artifact_id -CanvasId $hero.canvas_id -State "desktop_work_area" -NonBlank $entry.non_blank -Evidence $entry
            }
            finally {
                Stop-AcceptanceProcess $process
            }
        }
    }
    finally {
        Stop-AcceptanceProcess $fakeWallpaperProcess -Force
    }

    $allOpened = @($entries | Where-Object { $_.non_blank -and $_.bounds_match_work_area -and $_.fake_wallpaper_fixture_visible }).Count -eq $heroes.Count
    $backgroundOk = @($entries | Where-Object { $_.background_passthrough -eq $true -or $_.background_mode -eq "passthrough" }).Count -eq $heroes.Count
    $taskbarObservable = @($entries | Where-Object { $_.taskbar_visible_by_work_area }).Count -gt 0
    $clickThroughHonest = @(
        $entries |
            Where-Object {
                $_.click_through_implemented -eq $false -and
                $_.blank_area_click_through_machine_verified -eq $false -and
                $_.blank_area_click_through_status -eq "NEEDS_HUMAN_REVIEW"
            }
    ).Count -eq $heroes.Count
    $evidence = @{
        hero_desktop_work_area = $entries
        opened_hero_count = $entries.Count
        expected_hero_count = $heroes.Count
        all_opened_nonblank_on_work_area = $allOpened
        wallpaper_passthrough_confirmed = $backgroundOk
        taskbar_visible_by_work_area = $taskbarObservable
        click_through_honest_unimplemented = $clickThroughHonest
    }
    if ($allOpened -and $backgroundOk -and $taskbarObservable -and $clickThroughHonest) {
        Set-Check "desktop_work_area_hero_passthrough" "PASS" "All three hero Rooms opened on Desktop Work-Area with taskbar-preserving bounds, wallpaper passthrough, and honest click-through limitation evidence." $evidence
    }
    elseif ($allOpened -and $backgroundOk -and $clickThroughHonest) {
        Set-Check "desktop_work_area_hero_passthrough" "NEEDS_HUMAN_REVIEW" "Hero Desktop Work-Area evidence was captured, but taskbar visibility was not machine-observable on this host." $evidence
    }
    else {
        Set-Check "desktop_work_area_hero_passthrough" "FAIL" "Hero Desktop Work-Area evidence was incomplete." $evidence
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
        $requiredButtons = @(
            @{ id = "doctor"; names = @("doctor", "Doctor") },
            @{ id = "dry_run"; names = @("dry_run", "Dry Run") },
            @{ id = "run"; names = @("run", "Run") },
            @{ id = "preview_plan"; names = @("preview_plan", "Preview Plan") }
        )
        $buttons = @($requiredButtons | Where-Object {
            $window -and (Find-AnyButton $window $_.names)
        } | ForEach-Object { $_.id })
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

        $previewTree = Save-WindowTree "target-card-preview-before" $window
        $previewInvoked = Invoke-AnyNamedButton $window @("preview_plan", "Preview Plan") 15
        $previewStatus = Wait-CanvasStatusEvent "diablo_target" "target plan preview completed" "success" 15
        $previewShot = Save-Screenshot "target-card-preview-after"
        $previewCommand = Invoke-CapturedCommand "target-preview" "python" @(
            "-m", "ritualist", "canvas", "action", "gaming_desktop", "diablo_target", "preview_plan", "--json"
        )
        if ($previewInvoked -and $previewStatus -and $previewCommand.exit_code -eq 0 -and $previewCommand.stdout_text -match "target_plan") {
            Set-Check "target_card_preview" "PASS" "Packaged Canvas preview completed and source CLI returned structured target plan JSON." @{
                screenshot = $previewShot
                window_tree = $previewTree
                command_stdout = $previewCommand.stdout
                command_stderr = $previewCommand.stderr
                packaged_e2e_event = $previewStatus
            }
        }
        else {
            Set-Check "target_card_preview" "FAIL" "Target plan preview did not return expected evidence." @{
                invoked = $previewInvoked
                packaged_e2e_event = $previewStatus
                screenshot = $previewShot
                window_tree = $previewTree
                command_stdout = $previewCommand.stdout
                command_stderr = $previewCommand.stderr
            }
        }

        $doctorInvoked = Invoke-AnyNamedButton $window @("doctor", "Doctor") 10
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

        $dryRunInvoked = Invoke-AnyNamedButton $window @("dry_run", "Dry Run") 10
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

        $rootHelp = Invoke-CapturedCommand "cli-help-no-recording-surface" "python" @("-m", "ritualist", "--help")
        $canvasHelp = Invoke-CapturedCommand "canvas-help-no-recording-surface" "python" @("-m", "ritualist", "canvas", "--help")
        $helpText = "$($rootHelp.stdout_text)`n$($rootHelp.stderr_text)`n$($canvasHelp.stdout_text)`n$($canvasHelp.stderr_text)"
        $helpMatches = Find-TermMatches $helpText $RecordingSurfaceTerms

        $uiRows = @(Get-UiTextSnapshot $window | ForEach-Object {
                $_ | Add-Member -NotePropertyName surface -NotePropertyValue "canvas-live" -Force -PassThru
            })
        $savedSurfaceSnapshots = @(
            "packaged-home-window-tree.json",
            "packaged-canvas-window-tree.json",
            "packaged-classic-gui-window-tree.json",
            "canvas-initial-window-tree.json",
            "target-card-preview-before-window-tree.json"
        )
        foreach ($snapshotName in $savedSurfaceSnapshots) {
            $snapshotPath = Join-Path $SnapshotRoot $snapshotName
            if (Test-Path $snapshotPath) {
                $surfaceName = $snapshotName -replace "-window-tree\.json$", ""
                $snapshotRows = @(Get-Content -Path $snapshotPath -Raw | ConvertFrom-Json)
                foreach ($row in $snapshotRows) {
                    $row | Add-Member -NotePropertyName surface -NotePropertyValue $surfaceName -Force
                    $uiRows += $row
                }
            }
        }
        $uiSnapshot = Join-Path $SnapshotRoot "no-recording-ui-text.json"
        Write-JsonFile $uiSnapshot $uiRows 8 | Out-Null
        $uiText = ($uiRows | ForEach-Object { "$($_.surface)`n$($_.name)`n$($_.automation_id)" }) -join "`n"
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
        [void](Invoke-AnyNamedButton $window @("run", "Run") 10)
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
        [void](Invoke-AnyNamedButton $window @("run", "Run") 10)
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
        [void](Invoke-AnyNamedButton $window @("run", "Run") 10)
        $confirmation = Get-WindowByName "Ritualist Confirmation Required" 35
        Start-Sleep -Seconds 1
        $newRun = Get-ChildItem -Path $runs -Directory |
            Where-Object { $before -notcontains $_.Name } |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1
        if ($newRun) {
            $runId = $newRun.Name
        }
        $runOwnerKill = Stop-RunOwnerProcess $runId
        Stop-AcceptanceProcess $process -Force
        $process = $null
        Start-Sleep -Seconds 2
        $homeProcess = Start-AcceptanceProcess $script:RitualistExe @()
        Start-Sleep -Seconds 5
        $runJson = if ($runId) { Wait-RunStatus $runId "interrupted" 20 } else { $null }
        $homeShot = Save-Screenshot "hard-kill-relaunch-home"
        Stop-AcceptanceProcess $homeProcess
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
                run_owner_kill = $runOwnerKill
                relaunch_home_screenshot = $homeShot
                show_run_stdout = $show.stdout
            }
        }
        else {
            Set-Check "hard_kill_repairs_interrupted" "FAIL" "Hard-kill recovery evidence was missing or not interrupted." @{
                run_id = $runId
                run_log = $runEvidence
                run_owner_kill = $runOwnerKill
                observed_status = if ($runJson) { $runJson.status } else { $null }
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

function Invoke-LocalLearningSuggestionsEvidence {
    $journalProbe = Join-Path $CommandRoot "north_star_journal_events.py"
    $journalOutput = Join-Path $SnapshotRoot "north-star-journal-events.json"
    $suggestionProbe = Join-Path $CommandRoot "north_star_suggestions_scan.py"
    $suggestionOutput = Join-Path $SnapshotRoot "north-star-suggestions-scan.json"
    $draftProbe = Join-Path $CommandRoot "north_star_suggestion_drafts.py"
    $draftOutput = Join-Path $SnapshotRoot "north-star-suggestion-drafts.json"
    $reviewedFolder = Join-Path $FixtureRoot "north-star-reviewed-folder"
    New-Item -ItemType Directory -Force -Path $reviewedFolder | Out-Null

    @'
import json
import sys

from ritualist.activity_journal import ActivityJournal

journal = ActivityJournal(enabled=True)
events = [
    ("shortcut_opened", {"folder_label": "North Star Project Folder"}),
    ("shortcut_opened", {"folder_label": "North Star Project Folder"}),
    (
        "recipe_run_finished",
        {
            "recipe_id": "support_shift",
            "recipe_name": "Support Shift",
            "shortcut_id": "ticket_queue",
            "context_id": "support-shift",
        },
    ),
    (
        "recipe_run_finished",
        {
            "recipe_id": "support_shift",
            "recipe_name": "Support Shift",
            "shortcut_id": "ticket_queue",
            "context_id": "support-shift",
        },
    ),
]
written = []
for event_type, payload in events:
    if not journal.write(event_type, **payload):
        raise SystemExit(f"failed to write journal event: {event_type}")
    written.append({"event_type": event_type, "payload": payload})
payload = {
    "schema": "ritualist.acceptance.north_star_journal_events.v1",
    "written_count": len(written),
    "events": written,
}
with open(sys.argv[1], "w", encoding="utf-8") as fh:
    json.dump(payload, fh, indent=2)
print(json.dumps({"path": sys.argv[1], "written_count": len(written)}))
'@ | Set-Content -Path $journalProbe -Encoding UTF8

    @'
import json
import sys
from pathlib import Path

from ritualist.activity_collectors import FakeActivityCollector
from ritualist.activity_signals import journal_event_signal, recent_reference_signal
from ritualist.suggestions.service import scan_suggestions_payload

signals = (
    recent_reference_signal(
        reference_type="folder",
        label="North Star Project Folder",
        target="North Star Project Folder",
    ),
    recent_reference_signal(
        reference_type="folder",
        label="North Star Project Folder",
        target="North Star Project Folder",
    ),
    journal_event_signal(
        label="Support Shift",
        value="recipe_run_finished",
        metadata={
            "event_type": "recipe_run_finished",
            "recipe_id": "support_shift",
            "recipe_name": "Support Shift",
            "shortcut_id": "ticket_queue",
            "context_id": "support-shift",
        },
    ),
    journal_event_signal(
        label="Support Shift",
        value="recipe_run_finished",
        metadata={
            "event_type": "recipe_run_finished",
            "recipe_id": "support_shift",
            "recipe_name": "Support Shift",
            "shortcut_id": "ticket_queue",
            "context_id": "support-shift",
        },
    ),
)
payload = scan_suggestions_payload(
    collectors=(FakeActivityCollector(collector_id="north_star_acceptance", signals=signals),),
)
Path(sys.argv[1]).write_text(json.dumps(payload, indent=2), encoding="utf-8")
print(json.dumps(payload))
'@ | Set-Content -Path $suggestionProbe -Encoding UTF8

    @'
import json
import sys
from pathlib import Path

from ritualist.paths import recipes_path
from ritualist.suggestions.drafts_recipe import build_draft_recipe
from ritualist.suggestions.drafts_shortcut import build_shortcut_draft
from ritualist.suggestions.review import approve_suggestion
from ritualist.suggestions.storage import SuggestionStore

out = Path(sys.argv[1])
reviewed_folder = Path(sys.argv[2])
store = SuggestionStore()
suggestions = store.list()
shortcut = next((item for item in suggestions if item.kind.value == "shortcut_component"), None)
ritual = next((item for item in suggestions if item.kind.value == "ritual_recipe"), None)
if shortcut is None or ritual is None:
    raise SystemExit("expected shortcut_component and ritual_recipe suggestions")

recipes_before = sorted(path.name for path in recipes_path().glob("*.yaml")) if recipes_path().exists() else []
approved_shortcut = approve_suggestion(
    store,
    shortcut.id,
    reviewed_by="acceptance_operator",
    reviewed_at="2026-06-18T00:00:00Z",
)
shortcut_draft = build_shortcut_draft(
    approved_shortcut,
    reviewed_inputs={"folder_path": str(reviewed_folder)},
)
approved_ritual = approve_suggestion(
    store,
    ritual.id,
    reviewed_by="acceptance_operator",
    reviewed_at="2026-06-18T00:01:00Z",
)
recipe_draft = build_draft_recipe(approved_ritual)
recipes_after = sorted(path.name for path in recipes_path().glob("*.yaml")) if recipes_path().exists() else []

payload = {
    "schema": "ritualist.acceptance.north_star_suggestion_drafts.v1",
    "suggestion_count": len(suggestions),
    "suggestion_kinds": sorted({item.kind.value for item in suggestions}),
    "shortcut_suggestion_id": shortcut.id,
    "ritual_suggestion_id": ritual.id,
    "shortcut_approval": approved_shortcut.approval.to_dict() if approved_shortcut.approval else None,
    "ritual_approval": approved_ritual.approval.to_dict() if approved_ritual.approval else None,
    "shortcut_draft": shortcut_draft,
    "recipe_draft": recipe_draft,
    "recipes_before": recipes_before,
    "recipes_after": recipes_after,
    "recipes_written": recipes_before != recipes_after,
}
out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
print(json.dumps({"path": str(out), "suggestion_kinds": payload["suggestion_kinds"]}))
'@ | Set-Content -Path $draftProbe -Encoding UTF8

    $runsBefore = Get-RunDirectoryNames
    $enable = Invoke-CapturedCommand "north-star-learning-enable" "python" @("-m", "ritualist", "learning", "enable", "--source", "ritualist_journal", "--source", "recent_items", "--json")
    $journalWrite = Invoke-CapturedCommand "north-star-journal-events" "python" @($journalProbe, $journalOutput)
    $journal = Invoke-CapturedCommand "north-star-learning-journal" "python" @("-m", "ritualist", "learning", "journal", "--json")
    $learningScan = Invoke-CapturedCommand "north-star-learning-scan" "python" @("-m", "ritualist", "learning", "scan", "--json")
    $suggestionScan = Invoke-CapturedCommand "north-star-suggestions-scan" "python" @($suggestionProbe, $suggestionOutput)
    $suggestionList = Invoke-CapturedCommand "north-star-suggestions-list" "python" @("-m", "ritualist", "suggestions", "list", "--json")
    $drafts = Invoke-CapturedCommand "north-star-suggestion-drafts" "python" @($draftProbe, $draftOutput, $reviewedFolder)
    $delete = Invoke-CapturedCommand "north-star-learning-delete-data" "python" @("-m", "ritualist", "learning", "delete-data", "--yes", "--json")
    $runsAfter = Get-RunDirectoryNames

    $enablePayload = Convert-CommandJson $enable
    $journalPayload = Convert-CommandJson $journal
    $learningScanPayload = Convert-CommandJson $learningScan
    $suggestionScanPayload = Convert-CommandJson $suggestionScan
    $suggestionListPayload = Convert-CommandJson $suggestionList
    $deletePayload = Convert-CommandJson $delete
    $draftPayload = if (Test-Path $draftOutput) { Get-Content -Path $draftOutput -Raw | ConvertFrom-Json } else { $null }
    $journalEventPayload = if (Test-Path $journalOutput) { Get-Content -Path $journalOutput -Raw | ConvertFrom-Json } else { $null }

    $suggestionKinds = if ($suggestionScanPayload) { @($suggestionScanPayload.suggestions | ForEach-Object { $_.kind } | Select-Object -Unique) } else { @() }
    $hasShortcutSuggestion = $suggestionKinds -contains "shortcut_component"
    $hasRitualSuggestion = $suggestionKinds -contains "ritual_recipe"
    $shortcutDraftOk = (
        $draftPayload -and
        $draftPayload.shortcut_draft.schema_version -eq "ritualist.shortcut_draft.v1" -and
        $draftPayload.shortcut_draft.component_type -eq "shortcut.folder" -and
        $draftPayload.shortcut_draft.shortcut.target_configured -eq $true
    )
    $recipeDraftOk = (
        $draftPayload -and
        $draftPayload.recipe_draft.schema_version -eq "ritualist.suggestion.recipe_draft.v1" -and
        $draftPayload.recipe_draft.status -eq "disabled" -and
        $draftPayload.recipe_draft.creation_side_effects.installed -eq $false -and
        $draftPayload.recipe_draft.creation_side_effects.enabled -eq $false -and
        $draftPayload.recipe_draft.creation_side_effects.ran -eq $false -and
        $draftPayload.recipe_draft.creation_side_effects.wrote_files -eq $false
    )
    $noAutoRun = (($runsBefore -join "|") -eq ($runsAfter -join "|"))
    $deletedLearningData = (
        $deletePayload -and
        $deletePayload.deleted_count -ge 2 -and
        $deletePayload.paths.journal.deleted -eq $true -and
        $deletePayload.paths.suggestions.deleted -eq $true
    )
    $evidence = @{
        enable_stdout = $enable.stdout
        enable_stderr = $enable.stderr
        journal_event_fixture = $journalOutput
        journal_write_stdout = $journalWrite.stdout
        journal_write_stderr = $journalWrite.stderr
        learning_journal_stdout = $journal.stdout
        learning_scan_stdout = $learningScan.stdout
        suggestions_scan_json = $suggestionOutput
        suggestions_scan_stdout = $suggestionScan.stdout
        suggestions_list_stdout = $suggestionList.stdout
        suggestion_drafts_json = $draftOutput
        suggestion_drafts_stdout = $drafts.stdout
        suggestion_drafts_stderr = $drafts.stderr
        delete_learning_stdout = $delete.stdout
        delete_learning_stderr = $delete.stderr
        enabled_sources = if ($enablePayload) { $enablePayload.enabled_sources } else { @() }
        journal_event_count = if ($journalPayload) { $journalPayload.count } else { $null }
        written_journal_event_count = if ($journalEventPayload) { $journalEventPayload.written_count } else { $null }
        learning_scan_signal_count = if ($learningScanPayload) { $learningScanPayload.collection.signals.Count } else { $null }
        suggestion_scan_count = if ($suggestionScanPayload) { $suggestionScanPayload.suggestion_count } else { $null }
        suggestion_list_count = if ($suggestionListPayload) { $suggestionListPayload.count } else { $null }
        suggestion_kinds = $suggestionKinds
        has_shortcut_suggestion = $hasShortcutSuggestion
        has_ritual_suggestion = $hasRitualSuggestion
        shortcut_draft_ok = $shortcutDraftOk
        recipe_draft_ok = $recipeDraftOk
        recipes_written_by_draft_probe = if ($draftPayload) { $draftPayload.recipes_written } else { $null }
        runs_before = $runsBefore
        runs_after = $runsAfter
        no_auto_run = $noAutoRun
        delete_payload = $deletePayload
    }
    if (
        $enable.exit_code -eq 0 -and
        $journalWrite.exit_code -eq 0 -and
        $journal.exit_code -eq 0 -and
        $learningScan.exit_code -eq 0 -and
        $suggestionScan.exit_code -eq 0 -and
        $suggestionList.exit_code -eq 0 -and
        $drafts.exit_code -eq 0 -and
        $delete.exit_code -eq 0 -and
        $enablePayload.enabled -eq $true -and
        $enablePayload.background_collection -eq $false -and
        $journalPayload.count -ge 4 -and
        $hasShortcutSuggestion -and
        $hasRitualSuggestion -and
        $shortcutDraftOk -and
        $recipeDraftOk -and
        -not $draftPayload.recipes_written -and
        $noAutoRun -and
        $deletedLearningData
    ) {
        Set-Check "local_learning_suggestions_review_drafts" "PASS" "Local Learning enabled with explicit consent, journal events produced suggestions, reviewed shortcut and ritual drafts were created without installing/enabling/running, and learning data was deleted." $evidence
    }
    else {
        Set-Check "local_learning_suggestions_review_drafts" "FAIL" "Local Learning, Suggestions, draft review, no-auto-run, or deletion evidence was incomplete." $evidence
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

function Invoke-SuitePackQuarantineEvidence {
    $suiteCanvasOut = Join-Path $CommandRoot "north_star_suite_canvas.ritualistcanvas"
    $suiteThemeOut = Join-Path $CommandRoot "north_star_suite_theme.ritualisttheme"
    $suiteRitualRecipe = Join-Path $CommandRoot "north_star_suite_wait.yaml"
    $suiteRitualOut = Join-Path $CommandRoot "north_star_suite_wait.ritualistpack"
    $suiteOut = Join-Path $CommandRoot "north_star_suite.ritualistsuite"
    $readme = Join-Path $CommandRoot "north_star_suite_README.md"
    @"
version: "0.1"
id: north_star_suite_wait
name: North Star Suite Wait
description: Acceptance fixture ritual pack for suite quarantine checks.
steps:
  - action: wait.seconds
    seconds: 0.1
"@ | Set-Content -Path $suiteRitualRecipe -Encoding UTF8
    "# North Star Suite`n" | Set-Content -Path $readme -Encoding UTF8

    $runsBefore = Get-RunDirectoryNames
    $canvasExport = Invoke-CapturedCommand "north-star-suite-canvas-export" "python" @("-m", "ritualist", "canvas", "pack", "export", (Join-Path $script:FixtureAppData "canvases\visual_acceptance.yaml"), "--out", $suiteCanvasOut, "--json")
    $themeExport = Invoke-CapturedCommand "north-star-suite-theme-export" "python" @("-m", "ritualist", "canvas", "theme", "export", (Join-Path $script:FixtureAppData "themes\minimal_theme.yaml"), "--out", $suiteThemeOut, "--json")
    $ritualExport = Invoke-CapturedCommand "north-star-suite-ritual-export" "python" @("-m", "ritualist", "pack", "export", $suiteRitualRecipe, "--out", $suiteRitualOut)
    $suiteExport = Invoke-CapturedCommand "north-star-suite-export" "python" @("-m", "ritualist", "suite", "export", "--canvas-pack", $suiteCanvasOut, "--theme-pack", $suiteThemeOut, "--ritual-pack", $suiteRitualOut, "--out", $suiteOut, "--id", "north_star_suite", "--name", "North Star Suite", "--readme", $readme, "--json")
    $suiteValidate = Invoke-CapturedCommand "north-star-suite-validate" "python" @("-m", "ritualist", "suite", "validate", $suiteOut, "--json")
    $suiteImport = Invoke-CapturedCommand "north-star-suite-import" "python" @("-m", "ritualist", "suite", "import", $suiteOut, "--json")
    $suiteList = Invoke-CapturedCommand "north-star-suite-list-imports" "python" @("-m", "ritualist", "suite", "list-imports", "--json")
    $runsAfter = Get-RunDirectoryNames

    $validatePayload = Convert-CommandJson $suiteValidate
    $importPayload = Convert-CommandJson $suiteImport
    $listPayload = Convert-CommandJson $suiteList
    $ritualImports = if ($importPayload) { @($importPayload.ritual_imports) } else { @() }
    $listRows = if ($listPayload) { @($listPayload) } else { @() }
    $noAutoRun = (($runsBefore -join "|") -eq ($runsAfter -join "|"))
    $quarantined = (
        $validatePayload.validation.auto_run -eq $false -and
        $validatePayload.validation.auto_enable -eq $false -and
        $importPayload.status -eq "quarantined" -and
        $importPayload.auto_run -eq $false -and
        $importPayload.auto_enable -eq $false -and
        $importPayload.canvas_import.status -eq "quarantined" -and
        $importPayload.theme_import.status -eq "quarantined" -and
        $ritualImports.Count -eq 1 -and
        $ritualImports[0].status -eq "disabled" -and
        $listRows.Count -ge 1
    )
    $evidence = @{
        canvas_export_stdout = $canvasExport.stdout
        theme_export_stdout = $themeExport.stdout
        ritual_export_stdout = $ritualExport.stdout
        suite_export_stdout = $suiteExport.stdout
        suite_validate_stdout = $suiteValidate.stdout
        suite_import_stdout = $suiteImport.stdout
        suite_list_stdout = $suiteList.stdout
        validate_payload = $validatePayload
        import_payload = $importPayload
        list_payload = $listPayload
        runs_before = $runsBefore
        runs_after = $runsAfter
        no_auto_run = $noAutoRun
        quarantined = $quarantined
    }
    if (
        $canvasExport.exit_code -eq 0 -and
        $themeExport.exit_code -eq 0 -and
        $ritualExport.exit_code -eq 0 -and
        $suiteExport.exit_code -eq 0 -and
        $suiteValidate.exit_code -eq 0 -and
        $suiteImport.exit_code -eq 0 -and
        $suiteList.exit_code -eq 0 -and
        $quarantined -and
        $noAutoRun
    ) {
        Set-Check "suite_pack_quarantine_no_auto_enable" "PASS" "Suite Pack import placed visual and ritual contents into quarantine/disabled storage without auto-enable or auto-run." $evidence
    }
    else {
        Set-Check "suite_pack_quarantine_no_auto_enable" "FAIL" "Suite Pack quarantine or no-auto-enable evidence was incomplete." $evidence
    }
}

function Set-NorthStarAggregateEvidence {
    $required = @(
        "room_picker_three_heroes_taskbar_visible",
        "desktop_work_area_hero_passthrough",
        "edit_mode_builder_visible",
        "gaming_room_acceptance",
        "project_room_acceptance",
        "support_desk_acceptance",
        "local_learning_suggestions_review_drafts",
        "suite_pack_quarantine_no_auto_enable",
        "canvas_theme_pack_import_export_no_autorun",
        "no_recording_or_preview_capture"
    )
    $states = [ordered]@{}
    foreach ($id in $required) {
        if ($Results.Contains($id)) {
            $states[$id] = $Results[$id].status
        }
        else {
            $states[$id] = "MISSING"
        }
    }
    $desktopArtifacts = @(
        $script:VisualArtifacts |
            Where-Object { $_.state -eq "desktop_work_area" -and $_.id -match "desktop-work-area" }
    )
    $clickThroughHonest = @(
        $desktopArtifacts |
            Where-Object {
                $_.evidence.click_through_implemented -eq $false -and
                $_.evidence.blank_area_click_through_machine_verified -eq $false -and
                $_.evidence.blank_area_click_through_status -eq "NEEDS_HUMAN_REVIEW"
            }
    ).Count -ge 3
    $hasFailure = @($states.Values | Where-Object { $_ -eq "FAIL" -or $_ -eq "MISSING" }).Count -gt 0
    $hasReview = @($states.Values | Where-Object { $_ -eq "NEEDS_HUMAN_REVIEW" }).Count -gt 0
    $status = if ($hasFailure -or -not $clickThroughHonest) { "FAIL" } elseif ($hasReview) { "NEEDS_HUMAN_REVIEW" } else { "PASS" }
    $message = if ($status -eq "PASS") {
        "Packaged north-star acceptance flow has structured evidence across hero Rooms, Desktop Work-Area, Local Learning/Suggestions, Suite Pack quarantine, no auto-run, and honest click-through limitation checks."
    }
    elseif ($status -eq "NEEDS_HUMAN_REVIEW") {
        "Packaged north-star acceptance flow has structured evidence but at least one host-observable visual/taskbar item needs human review."
    }
    else {
        "Packaged north-star acceptance flow has failing or missing structured evidence."
    }
    Set-Check "north_star_packaged_acceptance" $status $message @{
        required_check_statuses = $states
        visual_artifact_references = @($desktopArtifacts | ForEach-Object { $_.id })
        click_through_honest_unimplemented = $clickThroughHonest
        flow_steps = @(
            "Open non-fullscreen Room picker",
            "Open each hero on Desktop Work-Area",
            "Confirm taskbar and wallpaper passthrough",
            "Exercise Gaming state lifecycle",
            "Exercise Project ritual and shortcuts",
            "Exercise Support Desk dry-run workflows",
            "Enable Local Learning",
            "Produce journal events",
            "Scan Suggestions",
            "Confirm folder-only -> shortcut",
            "Confirm multi-step -> ritual draft",
            "Review and create drafts",
            "Confirm nothing auto-runs",
            "Delete learning data",
            "Import a Suite Pack into quarantine",
            "Confirm no behavior auto-enables",
            "Confirm click-through remains honestly unimplemented"
        )
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
    Invoke-RoomPickerEvidence
    Assert-LaunchWindow -Id "packaged_canvas_visible" -Title "Ritualist Canvas" -LaunchArguments @("--canvas", "gaming_desktop") -ScreenshotName "packaged-canvas"
    Assert-LaunchWindow -Id "packaged_classic_gui_visible" -Title "Ritualist" -LaunchArguments @("--classic-gui") -ScreenshotName "packaged-classic-gui"
    Capture-CanvasVisualArtifact -CanvasId "minimal_desktop" -ArtifactId "minimal-room"
    Capture-CanvasVisualArtifact -CanvasId "gaming_desktop" -ArtifactId "gaming-room"
    Capture-CanvasVisualArtifact -CanvasId "helpdesk_desktop" -ArtifactId "support-desk"
    Invoke-StateUiFixtureEvidence
    Invoke-HeroRoomEvidence
    Capture-DesktopWorkAreaCanvasArtifact
    Capture-DesktopWorkAreaWindowedFallbackArtifact
    Capture-HeroDesktopWorkAreaArtifacts
    Capture-CanvasEditModeVisualArtifact
    Invoke-CanvasStaticActions
    Invoke-CanvasRunControls
    Invoke-CanvasRunDecline
    Invoke-HardKillRecovery
    Set-GamingRoomAggregateEvidence
    Invoke-LocalLearningSuggestionsEvidence
    Invoke-PackSafetyChecks
    Invoke-SuitePackQuarantineEvidence
    Invoke-PerformanceChecks
    Set-RemainingReviewChecks
    Set-NorthStarAggregateEvidence
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
