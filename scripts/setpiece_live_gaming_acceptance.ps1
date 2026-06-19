param(
    [string]$EvidenceDir = "artifacts\live-gaming-acceptance",
    [ValidateSet(
        "all",
        "battlenet_absent",
        "login_required",
        "install_visible",
        "locate_game_visible",
        "update_visible",
        "play_visible_disabled",
        "play_enabled",
        "target_disappears_after_approval",
        "diablo_already_running",
        "approved_play_succeeds",
        "postcondition_fails",
        "native_browser_handoff",
        "managed_browser_selected",
        "managed_media_starts",
        "managed_media_stalls",
        "optional_ambience_failure",
        "no_premature_minimize"
    )]
    [string[]]$Case = @("all"),
    [switch]$Live,
    [switch]$IUnderstandThisIsLive,
    [switch]$RecordScreen,
    [string]$HumanNotes = ""
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$SpecPath = Join-Path $RepoRoot "tests\acceptance\live_gaming_v0_2_alpha_1.yaml"

$CaseDefinitions = @(
    [ordered]@{ id = "battlenet_absent"; label = "Battle.net absent"; branch = "launcher_not_running"; requires_human = $false },
    [ordered]@{ id = "login_required"; label = "Battle.net login required"; branch = "login_required"; requires_human = $true },
    [ordered]@{ id = "install_visible"; label = "Install visible"; branch = "install_available"; requires_human = $true },
    [ordered]@{ id = "locate_game_visible"; label = "Locate the game visible"; branch = "locate_game_available"; requires_human = $true },
    [ordered]@{ id = "update_visible"; label = "Update visible or updating"; branch = "update_available_or_updating"; requires_human = $true },
    [ordered]@{ id = "play_visible_disabled"; label = "Play visible but disabled"; branch = "play_visible_but_disabled"; requires_human = $true },
    [ordered]@{ id = "play_enabled"; label = "Play enabled"; branch = "play_available_enabled"; requires_human = $true },
    [ordered]@{ id = "target_disappears_after_approval"; label = "Target disappears after approval"; branch = "target_changed_after_approval"; requires_human = $true },
    [ordered]@{ id = "diablo_already_running"; label = "Diablo already running"; branch = "game_running"; requires_human = $false },
    [ordered]@{ id = "approved_play_succeeds"; label = "Approved Play succeeds"; branch = "approved_play_postcondition_pass"; requires_human = $true },
    [ordered]@{ id = "postcondition_fails"; label = "Postcondition fails"; branch = "approved_play_postcondition_fail"; requires_human = $true },
    [ordered]@{ id = "native_browser_handoff"; label = "Native browser handoff"; branch = "native_browser_handoff"; requires_human = $true },
    [ordered]@{ id = "managed_browser_selected"; label = "Managed browser explicitly selected"; branch = "managed_browser_selected"; requires_human = $true },
    [ordered]@{ id = "managed_media_starts"; label = "Managed media starts"; branch = "managed_media_starts"; requires_human = $true },
    [ordered]@{ id = "managed_media_stalls"; label = "Managed media stalls"; branch = "managed_media_stalls"; requires_human = $true },
    [ordered]@{ id = "optional_ambience_failure"; label = "Optional ambience failure"; branch = "optional_ambience_failure"; requires_human = $true },
    [ordered]@{ id = "no_premature_minimize"; label = "No premature ambience minimize"; branch = "no_premature_minimize"; requires_human = $true }
)

$EvidenceFieldContract = @(
    "confirmation_suppressed",
    "confirmation_shown",
    "resolved_target_identity",
    "approval_decision",
    "invocation_result",
    "process_window_postcondition",
    "run_json",
    "steps_jsonl",
    "screenshot_or_short_clip",
    "human_notes"
)

if (-not ($Live -and $IUnderstandThisIsLive)) {
    Write-Output "LIVE Gaming acceptance requires explicit user initiation. Re-run with -Live -IUnderstandThisIsLive after arranging the requested desktop state."
    Write-Output "Safety: this harness never enters credentials, installs, locates, updates, purchases, automates gameplay, uses coordinate clicks, or sends synthetic keyboard input."
    exit 2
}

function Resolve-AcceptanceRoot {
    param([string]$PathText)

    $candidate = if ([System.IO.Path]::IsPathRooted($PathText)) {
        $PathText
    }
    else {
        Join-Path $RepoRoot $PathText
    }

    $resolvedParent = Resolve-Path -Path (Split-Path -Parent $candidate) -ErrorAction SilentlyContinue
    if ($null -eq $resolvedParent) {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $candidate) | Out-Null
        $resolvedParent = Resolve-Path -Path (Split-Path -Parent $candidate)
    }
    $resolved = Join-Path $resolvedParent.Path (Split-Path -Leaf $candidate)
    $resolvedRepo = (Resolve-Path $RepoRoot).Path
    $resolvedArtifacts = Join-Path $resolvedRepo "artifacts"
    $artifactsWithSeparator = $resolvedArtifacts.TrimEnd("\", "/") + [System.IO.Path]::DirectorySeparatorChar
    $resolvedWithSeparator = $resolved.TrimEnd("\", "/") + [System.IO.Path]::DirectorySeparatorChar

    if ($resolvedWithSeparator.StartsWith($resolvedRepo + [System.IO.Path]::DirectorySeparatorChar) -and -not $resolvedWithSeparator.StartsWith($artifactsWithSeparator)) {
        throw "Live Gaming evidence must be written under the repository artifacts directory when using a repository subdirectory: $resolved"
    }
    return $resolved
}

function Test-IsWindowsHost {
    return [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform([System.Runtime.InteropServices.OSPlatform]::Windows)
}

function ConvertTo-PlainObject {
    param($Value)
    return $Value
}

function Save-Json {
    param(
        [string]$Path,
        $Value
    )
    $Value | ConvertTo-Json -Depth 12 | Set-Content -Path $Path -Encoding UTF8
}

function Get-ProcessSnapshot {
    $items = @()
    try {
        $items = Get-CimInstance Win32_Process -ErrorAction Stop | ForEach-Object {
            [ordered]@{
                process_id = $_.ProcessId
                parent_process_id = $_.ParentProcessId
                name = $_.Name
                command_line = $_.CommandLine
            }
        }
    }
    catch {
        $items = Get-Process | ForEach-Object {
            [ordered]@{
                process_id = $_.Id
                parent_process_id = $null
                name = $_.ProcessName
                command_line = $null
            }
        }
    }
    return @($items)
}

function Get-WindowSnapshot {
    if (-not (Test-IsWindowsHost)) {
        return [ordered]@{ status = "not_windows"; windows = @() }
    }

    Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public static class SetpieceLiveWindows {
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);
    [DllImport("user32.dll")] public static extern int GetClassName(IntPtr hWnd, StringBuilder lpClassName, int nMaxCount);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
}
"@ -ErrorAction SilentlyContinue | Out-Null

    $windows = New-Object System.Collections.Generic.List[object]
    $foreground = [SetpieceLiveWindows]::GetForegroundWindow()
    $callback = [SetpieceLiveWindows+EnumWindowsProc]{
        param([IntPtr]$hWnd, [IntPtr]$lParam)
        if ([SetpieceLiveWindows]::IsWindowVisible($hWnd)) {
            $titleBuilder = New-Object System.Text.StringBuilder 512
            $classBuilder = New-Object System.Text.StringBuilder 256
            [void][SetpieceLiveWindows]::GetWindowText($hWnd, $titleBuilder, $titleBuilder.Capacity)
            [void][SetpieceLiveWindows]::GetClassName($hWnd, $classBuilder, $classBuilder.Capacity)
            $pid = [uint32]0
            [void][SetpieceLiveWindows]::GetWindowThreadProcessId($hWnd, [ref]$pid)
            $title = $titleBuilder.ToString()
            if ($title.Trim().Length -gt 0) {
                $windows.Add([ordered]@{
                    handle = $hWnd.ToInt64()
                    process_id = [int]$pid
                    title = $title
                    class_name = $classBuilder.ToString()
                    is_foreground = ($hWnd -eq $foreground)
                }) | Out-Null
            }
        }
        return $true
    }
    [void][SetpieceLiveWindows]::EnumWindows($callback, [IntPtr]::Zero)
    return [ordered]@{ status = "captured"; windows = @($windows) }
}

function Get-ScopedUiaTree {
    param([string]$TitleContains = "Battle.net")

    if (-not (Test-IsWindowsHost)) {
        return [ordered]@{ status = "not_windows"; title_contains = $TitleContains; elements = @() }
    }

    Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
    $root = [System.Windows.Automation.AutomationElement]::RootElement
    $allWindows = $root.FindAll([System.Windows.Automation.TreeScope]::Children, [System.Windows.Automation.Condition]::TrueCondition)
    $matched = $null
    foreach ($window in $allWindows) {
        if ($window.Current.Name -like "*$TitleContains*") {
            $matched = $window
            break
        }
    }
    if ($null -eq $matched) {
        return [ordered]@{ status = "window_not_found"; title_contains = $TitleContains; elements = @() }
    }

    $elements = New-Object System.Collections.Generic.List[object]
    $descendants = $matched.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
    $limit = [Math]::Min($descendants.Count, 200)
    for ($i = 0; $i -lt $limit; $i++) {
        $item = $descendants.Item($i)
        $name = $item.Current.Name
        if ($null -ne $name -and $name.Trim().Length -gt 0) {
            $elements.Add([ordered]@{
                name = $name
                automation_id = $item.Current.AutomationId
                control_type = $item.Current.ControlType.ProgrammaticName
                is_enabled = $item.Current.IsEnabled
                is_offscreen = $item.Current.IsOffscreen
            }) | Out-Null
        }
    }
    return [ordered]@{
        status = "captured"
        title_contains = $TitleContains
        root_name = $matched.Current.Name
        elements = @($elements)
        truncated = ($descendants.Count -gt $limit)
    }
}

function Save-Screenshot {
    param(
        [string]$Path
    )
    if (-not $RecordScreen) {
        return $null
    }
    if (-not (Test-IsWindowsHost)) {
        return $null
    }
    Add-Type -AssemblyName System.Windows.Forms, System.Drawing
    $bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
    $bitmap = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    try {
        $graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
        $bitmap.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
        return $Path
    }
    finally {
        $graphics.Dispose()
        $bitmap.Dispose()
    }
}

function Invoke-SetpieceCommand {
    param(
        [string]$Id,
        [string[]]$Arguments
    )
    $outputPath = Join-Path $CommandRoot "$Id.txt"
    $errorPath = Join-Path $CommandRoot "$Id.err.txt"
    $process = Start-Process -FilePath "python" -ArgumentList $Arguments -WorkingDirectory $RepoRoot -NoNewWindow -PassThru -Wait -RedirectStandardOutput $outputPath -RedirectStandardError $errorPath
    return [ordered]@{
        id = $Id
        exit_code = $process.ExitCode
        stdout = $outputPath
        stderr = $errorPath
    }
}

function New-CaseRecord {
    param(
        [hashtable]$Definition,
        [array]$ProcessSnapshot,
        $WindowSnapshot,
        $UiaTree,
        [string]$ScreenshotPath,
        $RunsEvidence
    )

    $processNames = @($ProcessSnapshot | ForEach-Object { "$($_.name)" })
    $windowTitles = @($WindowSnapshot.windows | ForEach-Object { "$($_.title)" })
    $battleNetPresent = (@($processNames | Where-Object { $_ -match "Battle[.]?net|Battle.net" }).Count -gt 0) -or (@($windowTitles | Where-Object { $_ -like "*Battle.net*" }).Count -gt 0)
    $diabloPresent = (@($processNames | Where-Object { $_ -match "Diablo" }).Count -gt 0) -or (@($windowTitles | Where-Object { $_ -like "*Diablo*" }).Count -gt 0)

    $status = "NEEDS_HUMAN_REVIEW"
    $message = "Live evidence captured for human review. Compare the desktop state and Setpiece logs to the case pass_when rule."
    if ($Definition.id -eq "battlenet_absent") {
        if (-not $battleNetPresent) {
            $status = "PASS"
            $message = "No Battle.net process or window was observed; no confirmation or invocation was attempted."
        }
        else {
            $status = "FAIL"
            $message = "Battle.net was observed while checking the absent case."
        }
    }
    elseif ($Definition.id -eq "diablo_already_running" -and $diabloPresent) {
        $message = "Diablo process/window was observed; human review must confirm Setpiece completed without Play approval."
    }

    return [ordered]@{
        id = $Definition.id
        label = $Definition.label
        status = $status
        message = $message
        evidence_scope = "live_integration_only"
        selected_branch = $Definition.branch
        safety_observed = [ordered]@{
            no_credentials_entered_by_harness = $true
            no_install_or_update_by_harness = $true
            no_gameplay_automation_by_harness = $true
            no_coordinate_clicks_by_harness = $true
            no_synthetic_keyboard_input_by_harness = $true
        }
        evidence = [ordered]@{
            process_snapshot = "evidence/process-tree.json"
            window_snapshot = "evidence/window-tree.json"
            scoped_uia_tree = "evidence/battlenet-uia-tree.json"
            run_logs = $RunsEvidence
            screenshot_or_short_clip = $ScreenshotPath
            exact_app_window_state = [ordered]@{
                battlenet_present = $battleNetPresent
                diablo_present = $diabloPresent
            }
            human_notes = $HumanNotes
            requires_human_review = $Definition.requires_human
        }
    }
}

$AcceptanceRoot = Resolve-AcceptanceRoot $EvidenceDir
$EvidenceRoot = Join-Path $AcceptanceRoot "evidence"
$CommandRoot = Join-Path $EvidenceRoot "commands"
New-Item -ItemType Directory -Force -Path @($AcceptanceRoot, $EvidenceRoot, $CommandRoot) | Out-Null

$selectedCaseIds = if ($Case -contains "all") {
    @($CaseDefinitions | ForEach-Object { $_.id })
}
else {
    @($Case)
}

Write-Output "LIVE Gaming acceptance is running in read-only evidence mode."
Write-Output "Do not enter credentials for this harness. Do not install, locate, update, purchase, or play the game for this harness."
Write-Output "Selected cases: $($selectedCaseIds -join ', ')"

$processSnapshot = Get-ProcessSnapshot
$windowSnapshot = Get-WindowSnapshot
$uiaTree = Get-ScopedUiaTree -TitleContains "Battle.net"
$screenshotPath = Save-Screenshot -Path (Join-Path $EvidenceRoot "desktop.png")
$runsEvidence = Invoke-SetpieceCommand "runs-no-repair" @("-m", "setpiece", "runs", "--limit", "10", "--no-repair")

Save-Json -Path (Join-Path $EvidenceRoot "process-tree.json") -Value $processSnapshot
Save-Json -Path (Join-Path $EvidenceRoot "window-tree.json") -Value $windowSnapshot
Save-Json -Path (Join-Path $EvidenceRoot "battlenet-uia-tree.json") -Value $uiaTree

$caseRecords = @()
foreach ($definition in $CaseDefinitions) {
    if ($selectedCaseIds -notcontains $definition.id) {
        $caseRecords += [ordered]@{
            id = $definition.id
            label = $definition.label
            status = "NOT_RUN"
            message = "Case was not selected for this live pass."
            evidence_scope = "live_integration_only"
            selected_branch = $definition.branch
            evidence = [ordered]@{ human_notes = $HumanNotes }
        }
        continue
    }
    $record = New-CaseRecord -Definition $definition -ProcessSnapshot $processSnapshot -WindowSnapshot $windowSnapshot -UiaTree $uiaTree -ScreenshotPath $screenshotPath -RunsEvidence $runsEvidence
    Save-Json -Path (Join-Path $EvidenceRoot "$($definition.id).json") -Value $record
    $caseRecords += $record
}

$selectedRecords = @($caseRecords | Where-Object { $selectedCaseIds -contains $_.id })
$failures = @($selectedRecords | Where-Object { $_.status -eq "FAIL" })
$review = @($selectedRecords | Where-Object { $_.status -eq "NEEDS_HUMAN_REVIEW" })
$passes = @($selectedRecords | Where-Object { $_.status -eq "PASS" })
$overallStatus = if ($failures.Count -gt 0) {
    "FAIL"
}
elseif ($review.Count -gt 0) {
    "NEEDS_HUMAN_REVIEW"
}
elseif ($passes.Count -eq $selectedRecords.Count) {
    "PASS"
}
else {
    "NOT_RUN"
}

$summary = [ordered]@{
    schema = "setpiece.live_gaming_acceptance_summary.v1"
    release = "v0.2.0-alpha.1"
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
    repo_head = (git -C $RepoRoot rev-parse HEAD)
    acceptance_spec = $SpecPath
    evidence_root = $EvidenceRoot
    record_screen = [bool]$RecordScreen
    live_integration_pass = [ordered]@{
        status = $overallStatus
        passed = ($overallStatus -eq "PASS")
        basis = "Explicit live harness evidence only; fixture acceptance is not live integration."
    }
    selected_cases = $selectedCaseIds
    evidence_field_contract = $EvidenceFieldContract
    cases = $caseRecords
    safety_contract = [ordered]@{
        explicit_live_switch = [bool]$Live
        explicit_understanding_switch = [bool]$IUnderstandThisIsLive
        no_credentials = $true
        no_install_locate_update = $true
        no_gameplay_automation = $true
        no_coordinate_clicks = $true
        no_synthetic_keyboard_input = $true
    }
}

$summaryJson = Join-Path $AcceptanceRoot "live-gaming-summary.json"
$summaryMd = Join-Path $AcceptanceRoot "live-gaming-summary.md"
Save-Json -Path $summaryJson -Value $summary

$lines = @(
    "# Setpiece Live Gaming Acceptance",
    "",
    "- Release: v0.2.0-alpha.1",
    "- Scope: live_integration_only",
    "- Overall: $overallStatus",
    "- Evidence root: $EvidenceRoot",
    "- Fixture acceptance is not live integration.",
    "",
    "| Case | Status | Branch |",
    "| --- | --- | --- |"
)
foreach ($record in $caseRecords) {
    $lines += "| $($record.id) | $($record.status) | $($record.selected_branch) |"
}
$lines += ""
$lines += "Safety: this harness did not enter credentials, install, locate, update, purchase, automate gameplay, use coordinate clicks, or send synthetic keyboard input."
$lines | Set-Content -Path $summaryMd -Encoding UTF8

Write-Output "Wrote $summaryJson"
Write-Output "Wrote $summaryMd"
if ($overallStatus -eq "FAIL") {
    exit 1
}
exit 0
