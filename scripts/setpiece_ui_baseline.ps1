param(
    [switch]$Packaged,
    [switch]$IUnderstandThisCapturesDesktop,
    [string]$EvidenceDir = "artifacts\ui-migration-baseline",
    [string]$ExecutablePath = "",
    [int]$ScenarioDwellSeconds = 5,
    [string[]]$Scales = @("100", "125", "150")
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$ExpectedBaselineHead = "4789b4c1b1795b89d91d109050c9153b9e41f13a"
$SummarySchema = "setpiece.ui_migration_baseline_summary.v1"
$GeneratedProcesses = New-Object System.Collections.Generic.List[object]
$Win32TypesLoaded = $false

$RequestedSurfaceDefinitions = @(
    [ordered]@{ id = "home"; label = "Home"; required = $true },
    [ordered]@{ id = "gaming_room"; label = "Gaming Room"; required = $true },
    [ordered]@{ id = "active_running"; label = "Active running"; required = $true },
    [ordered]@{ id = "waiting"; label = "Waiting"; required = $true },
    [ordered]@{ id = "confirmation"; label = "Confirmation"; required = $true },
    [ordered]@{ id = "blocked"; label = "Blocked"; required = $true },
    [ordered]@{ id = "failed"; label = "Failed"; required = $true },
    [ordered]@{ id = "interrupted_history"; label = "Interrupted history"; required = $true },
    [ordered]@{ id = "settings_privacy_disclosure"; label = "Settings/privacy disclosure"; required = $false }
)

$InternalIdPatterns = @(
    "\b[a-z][a-z0-9]+_[a-z0-9_]+\b",
    "\b[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}\b",
    "\b[A-Z]:\\[^`r`n]+",
    "\b/[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+"
)

function Resolve-BaselineRoot {
    param([string]$PathText)

    $candidate = if ([System.IO.Path]::IsPathRooted($PathText)) {
        $PathText
    }
    else {
        Join-Path $RepoRoot $PathText
    }

    $parent = Split-Path -Parent $candidate
    if (-not (Test-Path $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }

    $resolvedParent = (Resolve-Path -LiteralPath $parent).Path
    $resolved = [System.IO.Path]::GetFullPath((Join-Path $resolvedParent (Split-Path -Leaf $candidate)))
    $resolvedRepo = (Resolve-Path -LiteralPath $RepoRoot).Path
    $resolvedArtifacts = [System.IO.Path]::GetFullPath((Join-Path $resolvedRepo "artifacts"))
    $repoWithSeparator = $resolvedRepo.TrimEnd("\", "/") + [System.IO.Path]::DirectorySeparatorChar
    $artifactsWithSeparator = $resolvedArtifacts.TrimEnd("\", "/") + [System.IO.Path]::DirectorySeparatorChar
    $resolvedWithSeparator = $resolved.TrimEnd("\", "/") + [System.IO.Path]::DirectorySeparatorChar

    if ($resolvedWithSeparator.StartsWith($repoWithSeparator, [System.StringComparison]::OrdinalIgnoreCase) -and
        -not $resolvedWithSeparator.StartsWith($artifactsWithSeparator, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "UI baseline artifacts inside the repository must be written under artifacts/: $resolved"
    }
    return $resolved
}

function Clear-BaselineRoot {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    $resolved = [System.IO.Path]::GetFullPath($Path)
    $resolvedRepo = (Resolve-Path -LiteralPath $RepoRoot).Path
    $resolvedArtifacts = [System.IO.Path]::GetFullPath((Join-Path $resolvedRepo "artifacts"))
    $tempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
    $artifactsWithSeparator = $resolvedArtifacts.TrimEnd("\", "/") + [System.IO.Path]::DirectorySeparatorChar
    $tempWithSeparator = $tempRoot.TrimEnd("\", "/") + [System.IO.Path]::DirectorySeparatorChar
    $resolvedWithSeparator = $resolved.TrimEnd("\", "/") + [System.IO.Path]::DirectorySeparatorChar

    $isSafeArtifactsPath = $resolvedWithSeparator.StartsWith($artifactsWithSeparator, [System.StringComparison]::OrdinalIgnoreCase)
    $isSafeTempPath = $resolvedWithSeparator.StartsWith($tempWithSeparator, [System.StringComparison]::OrdinalIgnoreCase)
    if (-not ($isSafeArtifactsPath -or $isSafeTempPath)) {
        throw "Refusing to clear UI baseline evidence outside artifacts/ or the OS temp directory: $resolved"
    }
    if ($resolved.Length -lt 12 -or [string]::IsNullOrWhiteSpace((Split-Path -Leaf $resolved))) {
        throw "Refusing to clear suspicious UI baseline evidence path: $resolved"
    }

    Remove-Item -LiteralPath $resolved -Recurse -Force
}

function Write-JsonFile {
    param([string]$Path, [object]$Value, [int]$Depth = 12)

    $json = $Value | ConvertTo-Json -Depth $Depth
    Write-Utf8NoBomFile $Path ($json + [System.Environment]::NewLine)
    return $Path
}

function Write-Utf8NoBomFile {
    param([string]$Path, [string]$Text)

    $encoding = New-Object System.Text.UTF8Encoding -ArgumentList $false
    [System.IO.File]::WriteAllText($Path, $Text, $encoding)
}

function Get-GitText {
    param([string[]]$Arguments)

    try {
        $output = & git @Arguments 2>$null
        if ($LASTEXITCODE -eq 0) {
            return ($output -join "`n").Trim()
        }
    }
    catch {
    }
    return ""
}

function Test-IsWindowsHost {
    return [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform(
        [System.Runtime.InteropServices.OSPlatform]::Windows
    )
}

function Initialize-WindowsObservation {
    if ($script:Win32TypesLoaded) {
        return
    }

    Add-Type -AssemblyName System.Drawing
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName UIAutomationClient
    Add-Type -AssemblyName UIAutomationTypes
    Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;

public static class SetpieceUiBaselineWin32 {
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
    public static extern int GetClassName(IntPtr hWnd, StringBuilder lpClassName, int nMaxCount);

    [DllImport("user32.dll")]
    public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);

    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);

    [DllImport("user32.dll", EntryPoint="GetWindowLong")]
    private static extern IntPtr GetWindowLongPtr32(IntPtr hWnd, int nIndex);

    [DllImport("user32.dll", EntryPoint="GetWindowLongPtr")]
    private static extern IntPtr GetWindowLongPtr64(IntPtr hWnd, int nIndex);

    public static IntPtr GetWindowLongPtr(IntPtr hWnd, int nIndex) {
        return IntPtr.Size == 8 ? GetWindowLongPtr64(hWnd, nIndex) : GetWindowLongPtr32(hWnd, nIndex);
    }
}
"@ -ErrorAction SilentlyContinue | Out-Null

    $script:Win32TypesLoaded = $true
}

function Get-HostScalePercent {
    if (-not (Test-IsWindowsHost)) {
        return $null
    }
    Initialize-WindowsObservation
    $graphics = [System.Drawing.Graphics]::FromHwnd([System.IntPtr]::Zero)
    try {
        return [int][Math]::Round(($graphics.DpiX / 96.0) * 100.0)
    }
    finally {
        $graphics.Dispose()
    }
}

function New-ScalePlan {
    param($HostScale)

    $requested = @($Scales | ForEach-Object { [int]$_ })
    $hasHostScale = $null -ne $HostScale
    return @($requested | ForEach-Object {
        $scale = [int]$_
        if ($hasHostScale -and $scale -eq [int]$HostScale) {
            [ordered]@{
                scale_percent = $scale
                status = "CAPTURED"
                capture_status = "CAPTURED"
                reason = "Matches current host DPI scale."
            }
        }
        else {
            [ordered]@{
                scale_percent = $scale
                status = "NEEDS_HUMAN_REVIEW"
                capture_status = "NOT_CAPTURED"
                reason = "The harness does not change Windows display scale. Capture this scale manually or rerun on a host configured to this scale."
            }
        }
    })
}

function Get-ProcessSnapshotRows {
    try {
        return @(Get-CimInstance Win32_Process -ErrorAction Stop | ForEach-Object {
            [ordered]@{
                process_id = [int]$_.ProcessId
                parent_process_id = [int]$_.ParentProcessId
                name = $_.Name
                command_line = $_.CommandLine
            }
        })
    }
    catch {
        return @(Get-Process -ErrorAction SilentlyContinue | ForEach-Object {
            [ordered]@{
                process_id = [int]$_.Id
                parent_process_id = $null
                name = $_.ProcessName
                command_line = $null
            }
        })
    }
}

function Get-DescendantProcessIds {
    param([int[]]$RootProcessIds)

    $all = Get-ProcessSnapshotRows
    $ids = New-Object System.Collections.Generic.HashSet[int]
    foreach ($id in $RootProcessIds) {
        if ($id -gt 0) {
            [void]$ids.Add($id)
        }
    }
    $changed = $true
    while ($changed) {
        $changed = $false
        foreach ($process in $all) {
            if ($null -ne $process.parent_process_id -and
                $ids.Contains([int]$process.parent_process_id) -and
                -not $ids.Contains([int]$process.process_id)) {
                [void]$ids.Add([int]$process.process_id)
                $changed = $true
            }
        }
    }
    return @($ids)
}

function Get-ProcessTreeRows {
    param([int[]]$RootProcessIds)

    $ids = Get-DescendantProcessIds $RootProcessIds
    return @(Get-ProcessSnapshotRows | Where-Object { $ids -contains [int]$_.process_id })
}

function Get-TopLevelWindows {
    if (-not (Test-IsWindowsHost)) {
        return @()
    }

    Initialize-WindowsObservation
    $rows = New-Object System.Collections.Generic.List[object]
    $callback = [SetpieceUiBaselineWin32+EnumWindowsProc]{
        param([IntPtr]$hWnd, [IntPtr]$lParam)
        if (-not [SetpieceUiBaselineWin32]::IsWindowVisible($hWnd)) {
            return $true
        }

        $titleBuilder = New-Object System.Text.StringBuilder 512
        $classBuilder = New-Object System.Text.StringBuilder 256
        [void][SetpieceUiBaselineWin32]::GetWindowText($hWnd, $titleBuilder, $titleBuilder.Capacity)
        [void][SetpieceUiBaselineWin32]::GetClassName($hWnd, $classBuilder, $classBuilder.Capacity)
        $title = $titleBuilder.ToString()
        if ([string]::IsNullOrWhiteSpace($title)) {
            return $true
        }

        [uint32]$processId = 0
        [void][SetpieceUiBaselineWin32]::GetWindowThreadProcessId($hWnd, [ref]$processId)
        $rect = New-Object SetpieceUiBaselineWin32+RECT
        $bounds = $null
        if ([SetpieceUiBaselineWin32]::GetWindowRect($hWnd, [ref]$rect)) {
            $bounds = [ordered]@{
                x = [int]$rect.Left
                y = [int]$rect.Top
                width = [int]($rect.Right - $rect.Left)
                height = [int]($rect.Bottom - $rect.Top)
            }
        }

        $exStyle = [SetpieceUiBaselineWin32]::GetWindowLongPtr($hWnd, -20).ToInt64()
        $isToolWindow = (($exStyle -band 0x00000080) -ne 0)
        $isAppWindow = (($exStyle -band 0x00040000) -ne 0)
        $altTabCandidate = (-not $isToolWindow) -or $isAppWindow

        $rows.Add([ordered]@{
            z_index = 0
            hwnd = $hWnd.ToInt64()
            title = $title
            class_name = $classBuilder.ToString()
            process_id = [int]$processId
            bounds = $bounds
            taskbar_candidate_observable = $true
            taskbar_candidate = $altTabCandidate
            alt_tab_candidate_observable = $true
            alt_tab_candidate = $altTabCandidate
        }) | Out-Null
        return $true
    }

    [void][SetpieceUiBaselineWin32]::EnumWindows($callback, [IntPtr]::Zero)
    for ($i = 0; $i -lt $rows.Count; $i += 1) {
        $rows[$i]["z_index"] = $i
    }
    return @($rows.ToArray())
}

function Convert-BoundingRectangle {
    param($Rectangle)

    if ($null -eq $Rectangle -or $Rectangle.IsEmpty) {
        return $null
    }
    return [ordered]@{
        x = [int][Math]::Round($Rectangle.X)
        y = [int][Math]::Round($Rectangle.Y)
        width = [int][Math]::Round($Rectangle.Width)
        height = [int][Math]::Round($Rectangle.Height)
    }
}

function Get-UiaWindowTrees {
    param([int[]]$ProcessIds, [int]$ElementLimit = 400)

    if (-not (Test-IsWindowsHost)) {
        return @()
    }

    Initialize-WindowsObservation
    $pidSet = New-Object System.Collections.Generic.HashSet[int]
    foreach ($processIdValue in $ProcessIds) {
        [void]$pidSet.Add([int]$processIdValue)
    }

    $root = [System.Windows.Automation.AutomationElement]::RootElement
    $windows = $root.FindAll(
        [System.Windows.Automation.TreeScope]::Children,
        [System.Windows.Automation.Condition]::TrueCondition
    )
    $trees = @()
    for ($i = 0; $i -lt $windows.Count; $i += 1) {
        $window = $windows.Item($i)
        $windowProcessId = [int]$window.Current.ProcessId
        if (-not $pidSet.Contains($windowProcessId)) {
            continue
        }

        $items = @()
        $descendants = $window.FindAll(
            [System.Windows.Automation.TreeScope]::Descendants,
            [System.Windows.Automation.Condition]::TrueCondition
        )
        $limit = [Math]::Min($descendants.Count, $ElementLimit)
        for ($j = 0; $j -lt $limit; $j += 1) {
            $element = $descendants.Item($j)
            $items += [ordered]@{
                name = $element.Current.Name
                automation_id = $element.Current.AutomationId
                control_type = $element.Current.ControlType.ProgrammaticName
                class_name = $element.Current.ClassName
                process_id = [int]$element.Current.ProcessId
                enabled = [bool]$element.Current.IsEnabled
                offscreen = [bool]$element.Current.IsOffscreen
                bounds = Convert-BoundingRectangle $element.Current.BoundingRectangle
            }
        }

        $trees += [ordered]@{
            name = $window.Current.Name
            automation_id = $window.Current.AutomationId
            control_type = $window.Current.ControlType.ProgrammaticName
            class_name = $window.Current.ClassName
            process_id = $windowProcessId
            bounds = Convert-BoundingRectangle $window.Current.BoundingRectangle
            element_limit = $ElementLimit
            element_count_observed = $limit
            elements = @($items)
        }
    }
    return @($trees)
}

function Invoke-FirstNamedButton {
    param([int[]]$ProcessIds, [string[]]$Names, [int]$TimeoutSeconds = 10)

    if (-not (Test-IsWindowsHost)) {
        return [ordered]@{ invoked = $false; reason = "not_windows" }
    }

    Initialize-WindowsObservation
    $pidSet = New-Object System.Collections.Generic.HashSet[int]
    foreach ($processIdValue in $ProcessIds) {
        [void]$pidSet.Add([int]$processIdValue)
    }
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $root = [System.Windows.Automation.AutomationElement]::RootElement
        $windows = $root.FindAll(
            [System.Windows.Automation.TreeScope]::Children,
            [System.Windows.Automation.Condition]::TrueCondition
        )
        for ($i = 0; $i -lt $windows.Count; $i += 1) {
            $window = $windows.Item($i)
            if (-not $pidSet.Contains([int]$window.Current.ProcessId)) {
                continue
            }
            foreach ($name in $Names) {
                $nameCondition = New-Object System.Windows.Automation.PropertyCondition(
                    [System.Windows.Automation.AutomationElement]::NameProperty,
                    $name
                )
                $typeCondition = New-Object System.Windows.Automation.PropertyCondition(
                    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
                    [System.Windows.Automation.ControlType]::Button
                )
                $condition = New-Object System.Windows.Automation.AndCondition($nameCondition, $typeCondition)
                $button = $window.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condition)
                if ($button -and $button.Current.IsEnabled) {
                    $pattern = $button.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
                    $pattern.Invoke()
                    return [ordered]@{
                        invoked = $true
                        name = $name
                        process_id = [int]$button.Current.ProcessId
                    }
                }
            }
        }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $deadline)

    return [ordered]@{ invoked = $false; reason = "named_button_not_found"; names = $Names }
}

function Start-BaselineProcess {
    param([string]$FilePath, [string[]]$Arguments = @())

    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $FilePath
    foreach ($argument in $Arguments) {
        [void]$startInfo.ArgumentList.Add($argument)
    }
    $startInfo.UseShellExecute = $false
    $startInfo.EnvironmentVariables["SETPIECE_E2E"] = "1"
    $startInfo.EnvironmentVariables["SETPIECE_E2E_ARTIFACT_DIR"] = $script:E2ERoot
    $startInfo.EnvironmentVariables["SETPIECE_E2E_APP_DATA_DIR"] = $script:AppDataRoot
    $startInfo.EnvironmentVariables["LOCALAPPDATA"] = $script:LocalAppDataRoot
    $process = [System.Diagnostics.Process]::Start($startInfo)
    $GeneratedProcesses.Add($process) | Out-Null
    return $process
}

function Stop-BaselineProcess {
    param([object]$Process)

    if (-not $Process) {
        return
    }
    try {
        $Process.Refresh()
        if ($Process.HasExited) {
            return
        }
        [void]$Process.CloseMainWindow()
        Start-Sleep -Milliseconds 750
        $Process.Refresh()
        if (-not $Process.HasExited) {
            Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
        }
    }
    catch {
        try {
            Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
        }
        catch {
        }
    }
}

function Wait-NewDescendantProcess {
    param([int]$RootProcessId, [int[]]$BeforeProcessIds, [int]$TimeoutSeconds = 12)

    $beforeSet = New-Object System.Collections.Generic.HashSet[int]
    foreach ($id in $BeforeProcessIds) {
        [void]$beforeSet.Add([int]$id)
    }
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $descendants = @(Get-DescendantProcessIds @($RootProcessId))
        $newIds = @($descendants | Where-Object { -not $beforeSet.Contains([int]$_) })
        if ($newIds.Count -gt 0) {
            $newProcessId = [int]($newIds | Select-Object -First 1)
            return Get-Process -Id $newProcessId -ErrorAction SilentlyContinue
        }
        Start-Sleep -Milliseconds 300
    } while ((Get-Date) -lt $deadline)
    return $null
}

function Save-Screenshot {
    param([string]$Name, [string]$ScaleLabel)

    if (-not (Test-IsWindowsHost)) {
        return $null
    }

    Initialize-WindowsObservation
    $bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
    $bitmap = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    try {
        $graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
        $path = Join-Path $script:ScreenshotRoot "$Name-$ScaleLabel.png"
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

    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) {
        return $false
    }
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

function Get-E2EEvents {
    if (-not (Test-Path -LiteralPath $script:E2ERoot)) {
        return @()
    }
    $events = @()
    Get-ChildItem -LiteralPath $script:E2ERoot -Filter "setpiece-e2e-*.jsonl" -ErrorAction SilentlyContinue |
        ForEach-Object {
            Get-Content -LiteralPath $_.FullName -ErrorAction SilentlyContinue | ForEach-Object {
                if ([string]::IsNullOrWhiteSpace($_)) {
                    return
                }
                try {
                    $script:parsedEvent = $_ | ConvertFrom-Json
                    $events += $script:parsedEvent
                }
                catch {
                }
            }
        }
    return @($events)
}

function Get-ThemeEvidence {
    $ready = @(Get-E2EEvents | Where-Object { $_.event -eq "canvas.ready" })
    return [ordered]@{
        status = if ($ready.Count -gt 0) { "CAPTURED" } else { "NOT_CAPTURED" }
        selected_theme_ids = @($ready | ForEach-Object { $_.payload.theme_id } | Where-Object { $_ } | Select-Object -Unique)
        theme_sources = @($ready | ForEach-Object { $_.payload.theme_source } | Where-Object { $_ } | Select-Object -Unique)
        invalid_theme_event_count = @($ready | Where-Object { $_.payload.theme_valid -eq $false }).Count
        source_event_count = $ready.Count
    }
}

function Test-RectOverlap {
    param($A, $B)

    if (-not $A -or -not $B) {
        return 0
    }
    if ($A.width -le 0 -or $A.height -le 0 -or $B.width -le 0 -or $B.height -le 0) {
        return 0
    }
    $left = [Math]::Max([int]$A.x, [int]$B.x)
    $top = [Math]::Max([int]$A.y, [int]$B.y)
    $right = [Math]::Min([int]$A.x + [int]$A.width, [int]$B.x + [int]$B.width)
    $bottom = [Math]::Min([int]$A.y + [int]$A.height, [int]$B.y + [int]$B.height)
    if ($right -le $left -or $bottom -le $top) {
        return 0
    }
    return [int](($right - $left) * ($bottom - $top))
}

function Get-LayoutFindings {
    param([object[]]$WindowTrees)

    $clipped = @()
    $overlaps = @()
    foreach ($window in $WindowTrees) {
        $windowBounds = $window.bounds
        $elements = @($window.elements | Where-Object {
            $_.bounds -and -not $_.offscreen -and -not [string]::IsNullOrWhiteSpace($_.name)
        })
        foreach ($element in $elements) {
            $bounds = $element.bounds
            if ($windowBounds -and (
                    [int]$bounds.x -lt ([int]$windowBounds.x - 2) -or
                    [int]$bounds.y -lt ([int]$windowBounds.y - 2) -or
                    ([int]$bounds.x + [int]$bounds.width) -gt ([int]$windowBounds.x + [int]$windowBounds.width + 2) -or
                    ([int]$bounds.y + [int]$bounds.height) -gt ([int]$windowBounds.y + [int]$windowBounds.height + 2)
                )) {
                $clipped += [ordered]@{
                    window = $window.name
                    name = $element.name
                    control_type = $element.control_type
                    bounds = $bounds
                }
            }
        }

        $limit = [Math]::Min($elements.Count, 120)
        for ($i = 0; $i -lt $limit; $i += 1) {
            for ($j = $i + 1; $j -lt $limit; $j += 1) {
                $a = $elements[$i]
                $b = $elements[$j]
                if ($a.name -eq $b.name -and $a.control_type -eq $b.control_type) {
                    continue
                }
                $area = Test-RectOverlap $a.bounds $b.bounds
                if ($area -le 0) {
                    continue
                }
                $smaller = [Math]::Min(
                    [int]$a.bounds.width * [int]$a.bounds.height,
                    [int]$b.bounds.width * [int]$b.bounds.height
                )
                if ($smaller -gt 0 -and ($area / $smaller) -gt 0.65) {
                    $overlaps += [ordered]@{
                        window = $window.name
                        first = [ordered]@{ name = $a.name; control_type = $a.control_type; bounds = $a.bounds }
                        second = [ordered]@{ name = $b.name; control_type = $b.control_type; bounds = $b.bounds }
                        overlap_area = $area
                    }
                }
                if ($overlaps.Count -ge 40) {
                    break
                }
            }
            if ($overlaps.Count -ge 40) {
                break
            }
        }
    }

    return [ordered]@{
        status = "NEEDS_HUMAN_REVIEW"
        clipped_or_outside_window_controls = @($clipped | Select-Object -First 80)
        overlapping_control_candidates = @($overlaps | Select-Object -First 40)
        note = "Bounds heuristics identify candidates only; visual overlap and clipping require human review."
    }
}

function Get-LeakedInternalIds {
    param([object[]]$WindowTrees)

    $matches = @()
    foreach ($window in $WindowTrees) {
        foreach ($element in @($window.elements)) {
            $name = [string]$element.name
            if ([string]::IsNullOrWhiteSpace($name)) {
                continue
            }
            foreach ($pattern in $InternalIdPatterns) {
                if ([regex]::IsMatch($name, $pattern, [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)) {
                    $matches += [ordered]@{
                        window = $window.name
                        text = $name
                        control_type = $element.control_type
                        pattern = $pattern
                    }
                    break
                }
            }
        }
    }

    return [ordered]@{
        status = "NEEDS_HUMAN_REVIEW"
        visible_text_matches = @($matches | Select-Object -First 80)
        note = "Pattern matches are candidates only; human review decides whether text is an internal ID leak."
    }
}

function New-SurfaceObservation {
    param(
        [string]$Id,
        [string]$Label,
        [string]$Status,
        [string]$ReviewStatus,
        [string]$Reason,
        [hashtable]$Evidence = @{}
    )

    return [ordered]@{
        id = $Id
        label = $Label
        status = $Status
        review_status = $ReviewStatus
        reason = $Reason
        evidence = $Evidence
    }
}

function New-NotCapturedSurfaces {
    param([string]$Reason, [string]$ReviewStatus = "NEEDS_HUMAN_REVIEW")

    return @($RequestedSurfaceDefinitions | ForEach-Object {
        New-SurfaceObservation $_.id $_.label "NOT_CAPTURED" $ReviewStatus $Reason @{}
    })
}

function Write-SummaryMarkdown {
    param([string]$Path, [object]$Summary)

    $lines = @()
    $lines += "# Setpiece UI migration baseline"
    $lines += ""
    $lines += "- Schema: ``$($Summary.schema_version)``"
    $lines += "- Baseline HEAD: ``$($Summary.git.head)``"
    $lines += "- Expected baseline HEAD: ``$($Summary.git.expected_baseline_head)``"
    $lines += "- Packaged executable: ``$($Summary.packaged.executable_path)``"
    $lines += "- UX pass assigned: ``false``"
    $lines += "- Human UX pass: ``NOT_RUN``"
    $lines += ""
    $lines += "## Surfaces"
    foreach ($surface in $Summary.surfaces) {
        $lines += "- ``$($surface.id)``: $($surface.status) / $($surface.review_status) - $($surface.reason)"
    }
    $lines += ""
    $lines += "## DPI scale capture"
    foreach ($scale in $Summary.dpi.scale_plan) {
        $lines += "- $($scale.scale_percent)%: $($scale.capture_status) - $($scale.reason)"
    }
    $lines += ""
    $lines += "## Observations"
    $lines += "- Visible Setpiece window count: ``$($Summary.observations.visible_window_count)``"
    $lines += "- Taskbar entries observable: ``$($Summary.observations.taskbar_entries_observable)``"
    $lines += "- Alt+Tab entries observable: ``$($Summary.observations.alt_tab_entries_observable)``"
    $lines += "- Home remains open after Room launch: ``$($Summary.observations.home_remains_open_after_room_launch.status)``"
    $lines += "- Spawned process count: ``$($Summary.observations.spawned_process_count)``"
    $lines += ""
    $lines += "## Limitations"
    foreach ($limitation in $Summary.limitations) {
        $lines += "- $limitation"
    }
    $lines += ""
    $lines += "No release, UX, visual, DPI, accessibility, or human-usability pass is assigned by this baseline."
    Write-Utf8NoBomFile $Path (($lines -join [System.Environment]::NewLine) + [System.Environment]::NewLine)
}

if (-not ($Packaged -and $IUnderstandThisCapturesDesktop)) {
    Write-Output "UI migration baseline capture requires explicit packaged desktop evidence opt-in."
    Write-Output "Re-run with -Packaged -IUnderstandThisCapturesDesktop after arranging a safe desktop session."
    Write-Output "Safety: this harness does not use coordinate clicks, optical character recognition, keystroke capture, replay automation, remote command channels, game control automation, credential automation, or arbitrary recipe code."
    exit 2
}

$BaselineRoot = Resolve-BaselineRoot $EvidenceDir
Clear-BaselineRoot $BaselineRoot

$ScreenshotRoot = Join-Path $BaselineRoot "screenshots"
$SnapshotRoot = Join-Path $BaselineRoot "snapshots"
$E2ERoot = Join-Path $BaselineRoot "e2e-events"
$AppDataRoot = Join-Path $BaselineRoot "app-data"
$LocalAppDataRoot = Join-Path $BaselineRoot "local-app-data"
$SummaryJson = Join-Path $BaselineRoot "baseline-summary.json"
$SummaryMd = Join-Path $BaselineRoot "baseline-summary.md"
$ProcessTreeJson = Join-Path $BaselineRoot "process-tree.json"
$WindowTreeJson = Join-Path $BaselineRoot "window-tree.json"

New-Item -ItemType Directory -Force -Path @(
    $BaselineRoot,
    $ScreenshotRoot,
    $SnapshotRoot,
    $E2ERoot,
    $AppDataRoot,
    $LocalAppDataRoot
) | Out-Null

$resolvedExecutable = if ([string]::IsNullOrWhiteSpace($ExecutablePath)) {
    Join-Path $RepoRoot "dist\Setpiece\Setpiece.exe"
}
elseif ([System.IO.Path]::IsPathRooted($ExecutablePath)) {
    $ExecutablePath
}
else {
    Join-Path $RepoRoot $ExecutablePath
}
$resolvedExecutable = [System.IO.Path]::GetFullPath($resolvedExecutable)
$executableExists = Test-Path -LiteralPath $resolvedExecutable
$head = Get-GitText @("rev-parse", "HEAD")
$branch = Get-GitText @("branch", "--show-current")
$hostScale = Get-HostScalePercent
$scalePlan = New-ScalePlan $hostScale
$surfaces = @()
$limitations = @()
$processRows = @()
$topLevelWindows = @()
$windowTrees = @()
$homeProcess = $null
$roomProcess = $null
$roomLaunchEvidence = [ordered]@{
    method = "not_attempted"
    status = "NOT_CAPTURED"
}

try {
    if (-not $executableExists) {
        $limitations += "Packaged executable was not present; run .\scripts\build_windows_app.ps1 before capturing packaged UI evidence."
        $surfaces = New-NotCapturedSurfaces "Packaged executable was not present at $resolvedExecutable."
        Write-JsonFile $ProcessTreeJson ([ordered]@{
            status = "NOT_CAPTURED"
            reason = "packaged_executable_missing"
            root_process_ids = @()
            processes = @()
        }) | Out-Null
        Write-JsonFile $WindowTreeJson ([ordered]@{
            status = "NOT_CAPTURED"
            reason = "packaged_executable_missing"
            top_level_windows = @()
            uia_windows = @()
        }) | Out-Null
    }
    elseif (-not (Test-IsWindowsHost)) {
        $limitations += "Host is not Windows; packaged desktop windows and screenshots were not captured."
        $surfaces = New-NotCapturedSurfaces "Host is not Windows."
        Write-JsonFile $ProcessTreeJson ([ordered]@{
            status = "NOT_CAPTURED"
            reason = "not_windows"
            root_process_ids = @()
            processes = @()
        }) | Out-Null
        Write-JsonFile $WindowTreeJson ([ordered]@{
            status = "NOT_CAPTURED"
            reason = "not_windows"
            top_level_windows = @()
            uia_windows = @()
        }) | Out-Null
    }
    else {
        Initialize-WindowsObservation
        $hostScaleLabel = if ($hostScale) { "scale-$hostScale" } else { "scale-unknown" }

        $homeProcess = Start-BaselineProcess $resolvedExecutable @()
        Start-Sleep -Seconds $ScenarioDwellSeconds
        $homeProcessIdsBeforeRoom = @(Get-DescendantProcessIds @($homeProcess.Id))
        $homeTopWindows = @(Get-TopLevelWindows | Where-Object { $homeProcessIdsBeforeRoom -contains [int]$_.process_id })
        $homeWindowTrees = @(Get-UiaWindowTrees $homeProcessIdsBeforeRoom)
        $homeScreenshot = Save-Screenshot "home" $hostScaleLabel
        $homeNonBlank = Test-ScreenshotNonBlank $homeScreenshot
        $homeVisible = [bool]($homeTopWindows | Where-Object { $_.title -like "*Setpiece*" } | Select-Object -First 1)

        if ($homeVisible -and $homeScreenshot) {
            $surfaces += New-SurfaceObservation "home" "Home" "CAPTURED" "NEEDS_HUMAN_REVIEW" "Home before-state screenshot and window tree captured." @{
                screenshot = $homeScreenshot
                screenshot_nonblank = $homeNonBlank
                top_level_windows = @($homeTopWindows)
            }
        }
        else {
            $surfaces += New-SurfaceObservation "home" "Home" "NOT_CAPTURED" "NEEDS_HUMAN_REVIEW" "Home window was not observable after launch." @{
                screenshot = $homeScreenshot
                top_level_windows = @($homeTopWindows)
            }
        }

        $invokeResult = Invoke-FirstNamedButton @($homeProcess.Id) @("Open in Window") 12
        if ($invokeResult.invoked) {
            $roomProcess = Wait-NewDescendantProcess $homeProcess.Id $homeProcessIdsBeforeRoom 12
            $roomLaunchEvidence = [ordered]@{
                method = "home_uia_open_in_window"
                status = if ($roomProcess) { "CAPTURED" } else { "NOT_CAPTURED" }
                invoke_result = $invokeResult
                spawned_process_id = if ($roomProcess) { [int]$roomProcess.Id } else { $null }
            }
        }
        else {
            $roomProcess = Start-BaselineProcess $resolvedExecutable @("--room", "gaming", "--host", "windowed")
            $roomLaunchEvidence = [ordered]@{
                method = "direct_packaged_room_argument"
                status = "CAPTURED"
                invoke_result = $invokeResult
                spawned_process_id = [int]$roomProcess.Id
                note = "Home UIA launch was not available; the Room was launched through the packaged --room entry point."
            }
        }

        Start-Sleep -Seconds $ScenarioDwellSeconds
        $rootProcessIds = @($homeProcess.Id)
        if ($roomProcess) {
            $rootProcessIds += [int]$roomProcess.Id
        }
        $setpieceProcessIds = @(Get-DescendantProcessIds $rootProcessIds)
        $processRows = @(Get-ProcessTreeRows $rootProcessIds)
        $topLevelWindows = @(Get-TopLevelWindows | Where-Object { $setpieceProcessIds -contains [int]$_.process_id })
        $windowTrees = @(Get-UiaWindowTrees $setpieceProcessIds)
        $roomTopWindows = @($topLevelWindows | Where-Object { $_.title -like "*Canvas*" -or $_.title -like "*Room*" -or ($roomProcess -and $_.process_id -eq [int]$roomProcess.Id) })
        $roomScreenshot = Save-Screenshot "gaming-room" $hostScaleLabel
        $roomNonBlank = Test-ScreenshotNonBlank $roomScreenshot
        $roomVisible = [bool]($roomTopWindows | Select-Object -First 1)

        if ($roomVisible -and $roomScreenshot) {
            $surfaces += New-SurfaceObservation "gaming_room" "Gaming Room" "CAPTURED" "NEEDS_HUMAN_REVIEW" "Gaming Room before-state screenshot and window tree captured." @{
                screenshot = $roomScreenshot
                screenshot_nonblank = $roomNonBlank
                launch = $roomLaunchEvidence
                top_level_windows = @($roomTopWindows)
            }
        }
        else {
            $surfaces += New-SurfaceObservation "gaming_room" "Gaming Room" "NOT_CAPTURED" "NEEDS_HUMAN_REVIEW" "Gaming Room window was not observable after launch." @{
                screenshot = $roomScreenshot
                launch = $roomLaunchEvidence
                top_level_windows = @($roomTopWindows)
            }
        }

        $homeStillVisible = [bool]($topLevelWindows | Where-Object { $_.process_id -eq [int]$homeProcess.Id -and $_.title -like "*Setpiece*" } | Select-Object -First 1)
        $roomVisibleAfterLaunch = [bool]($topLevelWindows | Where-Object { $roomProcess -and $_.process_id -eq [int]$roomProcess.Id } | Select-Object -First 1)

        $privacyTexts = @(
            $homeWindowTrees |
                ForEach-Object { $_.elements } |
                ForEach-Object { $_.name } |
                Where-Object { $_ -and ($_ -match "Privacy|Local Learning|screenshots|keystrokes|review before creation") }
        )
        if ($privacyTexts.Count -gt 0) {
            $privacyScreenshot = Save-Screenshot "settings-privacy-disclosure" $hostScaleLabel
            $surfaces += New-SurfaceObservation "settings_privacy_disclosure" "Settings/privacy disclosure" "CAPTURED" "NEEDS_HUMAN_REVIEW" "Privacy disclosure text was visible or discoverable in the Home window tree." @{
                screenshot = $privacyScreenshot
                visible_text = @($privacyTexts | Select-Object -Unique)
            }
        }
        else {
            $surfaces += New-SurfaceObservation "settings_privacy_disclosure" "Settings/privacy disclosure" "NOT_CAPTURED" "NEEDS_HUMAN_REVIEW" "No Settings/privacy disclosure surface was observable without additional UI interaction." @{}
        }

        foreach ($definition in $RequestedSurfaceDefinitions) {
            if (@($surfaces | Where-Object { $_.id -eq $definition.id }).Count -gt 0) {
                continue
            }
            $surfaces += New-SurfaceObservation $definition.id $definition.label "NOT_CAPTURED" "NEEDS_HUMAN_REVIEW" "No safe packaged baseline trigger exists for this state in the current harness; do not infer a pass from missing visual evidence." @{}
        }

        Write-JsonFile $ProcessTreeJson ([ordered]@{
            status = "CAPTURED"
            root_process_ids = @($rootProcessIds)
            process_count = $processRows.Count
            processes = @($processRows)
        }) | Out-Null
        Write-JsonFile $WindowTreeJson ([ordered]@{
            status = "CAPTURED"
            visible_top_level_window_count = $topLevelWindows.Count
            top_level_windows = @($topLevelWindows)
            uia_windows = @($windowTrees)
        }) | Out-Null

        $script:HomeRemainsOpenObservation = [ordered]@{
            status = if ($homeStillVisible -and $roomVisibleAfterLaunch) { "CAPTURED" } else { "NOT_CAPTURED" }
            home_visible_after_room_launch = $homeStillVisible
            room_visible_after_launch = $roomVisibleAfterLaunch
            room_launch = $roomLaunchEvidence
        }
    }
}
finally {
    foreach ($process in @($GeneratedProcesses | Sort-Object Id -Descending)) {
        Stop-BaselineProcess $process
    }
}

if (-not $script:HomeRemainsOpenObservation) {
    $script:HomeRemainsOpenObservation = [ordered]@{
        status = "NOT_CAPTURED"
        home_visible_after_room_launch = $false
        room_visible_after_launch = $false
        room_launch = $roomLaunchEvidence
    }
}

$windowTreePayload = if (Test-Path -LiteralPath $WindowTreeJson) {
    Get-Content -LiteralPath $WindowTreeJson -Raw | ConvertFrom-Json
}
else {
    [pscustomobject]@{ uia_windows = @(); top_level_windows = @() }
}
$allUiaWindows = @($windowTreePayload.uia_windows)
$allTopWindows = @($windowTreePayload.top_level_windows)
$layoutFindings = Get-LayoutFindings $allUiaWindows
$leakedIds = Get-LeakedInternalIds $allUiaWindows
$themeEvidence = Get-ThemeEvidence

$taskbarEntries = @($allTopWindows | Where-Object { $_.taskbar_candidate })
$altTabEntries = @($allTopWindows | Where-Object { $_.alt_tab_candidate })
$actualWindowSizes = @($allTopWindows | ForEach-Object {
    [ordered]@{
        title = $_.title
        process_id = $_.process_id
        bounds = $_.bounds
    }
})

$summary = [ordered]@{
    schema_version = $SummarySchema
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
    scope = "current_before_state_only"
    product_goal_note = "Legacy surfaces are recorded factually as before-state only; this baseline does not retain legacy UI as a product goal."
    git = [ordered]@{
        branch = $branch
        head = $head
        expected_baseline_head = $ExpectedBaselineHead
        baseline_head_matches_expected = ($head -eq $ExpectedBaselineHead)
    }
    packaged = [ordered]@{
        requested = [bool]$Packaged
        executable_path = $resolvedExecutable
        executable_exists = $executableExists
    }
    safety = [ordered]@{
        no_ux_pass_assigned = $true
        screenshot_capture_scope = "Opt-in acceptance evidence only; no product screenshot capability is added."
        no_coordinate_clicks = $true
        no_ocr = $true
        no_keylogging = $true
        no_macro_replay = $true
        no_remote_execution = $true
        no_gameplay_automation = $true
        no_password_automation = $true
        no_arbitrary_recipe_code = $true
    }
    truth_model = [ordered]@{
        shell_architecture_pass = "NOT_RUN"
        visual_contract_pass = "NOT_RUN"
        dpi_pass = "NOT_RUN"
        keyboard_accessibility_pass = "NOT_RUN"
        narrator_pass = "NOT_RUN"
        focus_lifecycle_pass = "NOT_RUN"
        human_usability_pass = "NOT_RUN"
        release_pass = $false
    }
    dpi = [ordered]@{
        host_scale_percent = $hostScale
        requested_scale_percents = @($Scales | ForEach-Object { [int]$_ })
        scale_plan = @($scalePlan)
        switching_attempted = $false
    }
    artifacts = [ordered]@{
        baseline_summary_json = $SummaryJson
        baseline_summary_md = $SummaryMd
        screenshots_dir = $ScreenshotRoot
        process_tree_json = $ProcessTreeJson
        window_tree_json = $WindowTreeJson
    }
    surfaces = @($surfaces)
    observations = [ordered]@{
        visible_window_count = $allTopWindows.Count
        taskbar_entries_observable = $allTopWindows.Count -gt 0
        taskbar_entries = @($taskbarEntries | ForEach-Object { [ordered]@{ title = $_.title; process_id = $_.process_id; bounds = $_.bounds } })
        alt_tab_entries_observable = $allTopWindows.Count -gt 0
        alt_tab_entries = @($altTabEntries | ForEach-Object { [ordered]@{ title = $_.title; process_id = $_.process_id; bounds = $_.bounds } })
        home_remains_open_after_room_launch = $script:HomeRemainsOpenObservation
        spawned_process_count = [Math]::Max(0, $processRows.Count - 1)
        clipped_or_overlapping_controls = $layoutFindings
        leaked_internal_ids = $leakedIds
        selected_theme = $themeEvidence
        actual_window_sizes = @($actualWindowSizes)
        minimum_window_sizes = [ordered]@{
            status = "NOT_CAPTURED"
            reason = "Minimum track sizes are not exposed by the current packaged surface observation path."
        }
    }
    limitations = @($limitations)
}

Write-JsonFile $SummaryJson $summary 16 | Out-Null
Write-SummaryMarkdown $SummaryMd $summary

Write-Output "Wrote UI migration baseline summary: $SummaryJson"
Write-Output "No UX pass was assigned."
