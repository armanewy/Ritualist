# Hero Rooms Packaged Dogfood

This document describes the v0.2.0-alpha.1 packaged acceptance harness for the current north-star scope. It is evidence documentation, not a release tag or a product feature.

Run from the repository root:

```powershell
.\scripts\setpiece_release_acceptance.ps1 -Packaged -RecordScreen
```

The harness writes:

- `artifacts\release-acceptance\acceptance-summary.json`
- `artifacts\release-acceptance\acceptance-summary.md`
- screenshots, frame sequences, process trees, window trees, z-order snapshots, command transcripts, fixture data, E2E JSONL, and copied run logs under `artifacts\release-acceptance\evidence`

## Scope

The harness covers exactly the three promoted hero Rooms:

- Gaming Room
- Project Room
- Support Desk

`minimal_desktop` remains available as a Desktop Work-Area fallback and release-acceptance fixture. It is not promoted by the Room picker and is not a fourth hero Room.

## Evidence

The acceptance suite records machine evidence for:

- Room picker: windowed Home, taskbar-preserving work area when observable, exactly three promoted Rooms, and no `minimal_desktop` promotion.
- Gaming Room: packaged render, expected components, Doctor, Dry Run, safe Run to explicit confirmation, target preview, status transitions, pause/resume/stop, recent activity, native confirmation z-order, declined Play, `show-run`, and hard-kill recovery.
- Project Room: packaged render, bundled Coding Mode Doctor and Dry Run command transcripts, a local fixture that rebinds folder/editor/terminal shortcuts to evidence-directory test targets so `Open Folder`, `Launch App`, and `Open URL` controls can be observed without installed apps, folder shortcut dry-run with no run log, and ritual status/controller fixture data.
- Support Desk: packaged render, five runbook cards, diagnostics/audio dry-run command transcripts, VPN/New Hire placeholder scans, status/controller/recent activity/log evidence.
- State UI: ready, running, waiting, confirming, paused, failed, and interrupted fixture states generated through the existing typed Canvas runtime model.

## Boundaries

The harness uses fake windows and source CLI probes for supplemental evidence. It does not require installed VS Code, Windows Terminal, Battle.net, VPN software, support portals, or a game login.

The harness does not add product capture or automation capabilities. It does not add Watch Me, recording, teach-by-watching, global hooks, OCR, keylogging, coordinate capture, browser history collection, Recall-like collection, arbitrary recipe-supplied Python/JavaScript/PowerShell/shell/QML/HTML, cloud sync, remote execution, marketplace behavior, password automation, gameplay automation, shell replacement, taskbar hiding, kiosk mode, or click-through automation.

`acceptance-summary.json` remains the source of truth for taggability. `v0.2.0-alpha.1` is not taggable unless the fresh packaged run has zero `FAIL` and zero `NEEDS_HUMAN_REVIEW` checks.
