# Setpiece North Star Contract

This file is the canonical product contract for Setpiece. Tests may assert the
rules here, so edits should be factual, intentional, and coordinated with the
product boundary documents.

## Product Statement

Setpiece is a local ritual/runbook engine with a desktop-native body.
Recipes and rituals are the center of gravity. Rooms, Canvas, shortcuts,
Suggestions, packs, logs, and recovery surfaces exist to make rituals more
visible, useful, reviewable, and trustworthy.

Setpiece is not a shell replacement, generic RPA suite, macro recorder,
Recall-like capture tool, marketplace, cloud automation service, remote
execution service, password automation tool, gameplay automation tool, kiosk
mode, or taskbar-hiding desktop replacement.

## Hero Rooms

Setpiece has exactly three promoted hero Rooms:

- Gaming Room
- Project Room
- Support Desk

Do not promote a fourth Room. The `minimal_desktop` Canvas must not be deleted;
it remains an internal Desktop Work-Area fallback and release validation fixture,
not a promoted Room.

### Gaming Room

Gaming Room centers the `gaming_mode` ritual. It must make Doctor, Dry Run, and
Run available as explicit user actions, show runtime status and controller
state, preview the Diablo target before any risky Play action, show recent
activity, and expose confirmation and recovery surfaces when the ritual is
waiting, paused, failed, interrupted, or requires confirmation.

### Project Room

Project Room centers a coding/project setup ritual. It must surface folder,
editor, terminal, and documentation shortcuts as local handoffs, show ritual
status and controller state, and show recent activity. Shortcuts may prepare the
workspace, but imported or shared behavior must never auto-run or auto-create
rituals.

### Support Desk

Support Desk centers support triage runbooks. It must include collect
diagnostics, meeting audio troubleshooting, a VPN Repair placeholder, and a New
Hire Setup draft. It must expose Doctor, status, and controller state, show
recent runs, and provide access to local evidence and logs. Evidence defaults
must remain local and limited to safe run metadata, statuses, window titles, and
operator notes unless a future explicit policy says otherwise.

## Ritual State Contract

Every Room that presents a ritual must be able to represent these states and
surfaces without relying on a desktop session in tests:

- Doctor status
- dry-run status
- current step
- waiting state
- confirmation required state
- paused state
- failed state
- interrupted recovery
- last run summary
- logs and artifacts access

Risky desktop actions require explicit confirmation gates. Recovery must be
visible after an interrupted run. Logs and artifacts are local run outputs, not
remote telemetry.

## Suggestions Contract

Suggestions are local and opt-in. A Suggestion may propose a recipe or ritual
change, but it must use review-before-create and must never auto-create or
auto-run a ritual. Suggestions must not implement Watch Me, recording, OCR,
screenshots, keylogging, coordinate capture, browser history ingestion, cloud
sync, remote execution, marketplace behavior, password automation, gameplay
automation, shell replacement, taskbar hiding, kiosk mode, click-through
automation, arbitrary recipe-supplied Python, arbitrary recipe-supplied
JavaScript, arbitrary recipe-supplied PowerShell, arbitrary shell snippets,
arbitrary QML, or arbitrary HTML.

## Entry Contract

Setpiece opens into a taskbar-preserving Room picker and is never fullscreen by
default. The entry surface promotes exactly three Rooms: Gaming Room, Project
Room, and Support Desk. The recipe library is secondary: it remains available
for review, Doctor, dry-run, run, logs, and editing, but it must not displace the
three promoted Rooms as the primary entry model.

Imported and shared packs, recipes, canvases, Suggestions, and templates must
never run automatically and must never create local rituals automatically. They
may be reviewed, validated, doctored, dry-run, imported into quarantine, or
enabled only through explicit user action and the existing safety policy.

## Implementation Constraints

Workflow parsing and execution must stay cross-platform. Windows UI Automation
imports must remain lazy and inside adapter methods. Tests must use fake
adapters where runtime behavior is involved and must not require a Windows
desktop session.

Recipes must expose only structured actions. Do not add recipe actions that
execute arbitrary Python, JavaScript, PowerShell, shell snippets, QML, or HTML.
Do not add Watch Me, recording, OCR, screenshots, keylogging, coordinate
capture, cloud sync, remote execution, marketplace behavior, password
automation, gameplay automation, true Windows shell replacement, taskbar hiding,
kiosk mode, click-through automation, or browser history ingestion.
