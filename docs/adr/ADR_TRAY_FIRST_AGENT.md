# ADR: Tray-First Resident Agent And Quiet Instrument

Status: Accepted

Date: 2026-06-18

## Context

Ritualist currently launches into Home by default. Home remains visible and
spawns Room processes. Canvas Use Mode is implemented as a separate
`ApplicationWindow` and still carries everyday runtime responsibilities.

The functionality baseline is strong enough to preserve: Gaming recovery is
complete, including state-driven Gaming Mode, native browser handoff by
default, explicit managed browser automation, Battle.net readiness inspection
before Play approval, exact target resolution, postcondition verification,
scoped remembered approvals, recipe transparency, setup overrides, and the live
Gaming acceptance harness.

The release truth model is not complete. Live integration and human UX remain
`NOT_RUN`, so release readiness must not be claimed.

The design problem is structural, not a styling problem. A better Home or a
more polished Canvas shell would keep the same wrong ownership model: visible
application at rest, multiple runtime windows, and unclear close/exit behavior.

## Decision

Ritualist will be tray-first.

The accepted architecture is one resident per-user local Agent with:

- no visible application window at rest;
- one tray icon;
- local-only single-instance activation;
- left-click tray and `Win+Ctrl+R` invoking the same contextual surface;
- stable right-click shortcut menu;
- one contextual Picker;
- one Quiet Instrument for the active attended ritual;
- owned confirmation and review surfaces;
- normal Settings, Room Builder, Run Log, and Approval Review windows;
- optional Desktop Work-Area layer only when spatial context matters.

Quiet Instrument is the selected everyday runtime surface. Home and
Canvas-as-runtime-shell are current baseline surfaces to replace and remove
after acceptance, not equal alternatives and not permanent compatibility
targets.

## Binding Rules

- Tray left-click opens Picker when idle and the active Quiet Instrument or
  exact review state when a run requires attention.
- Tray right-click opens a stable menu: Open Ritualist, Active ritual when
  present, Rooms, Recent rituals, Run Log, Settings, and Exit Ritualist.
- `Win+Ctrl+R` matches tray left-click.
- Double-click has no unique action.
- Closing a surface hides or closes only that surface.
- Explicit Exit is the only Agent exit path.
- Exit during an active attended run requires a stop-and-exit confirmation.
- There is at most one attended ritual per Windows user.
- Notifications route to review. They never approve, run, stop, or mutate
  consequential state.

## Consequences

Implementation work must create Agent-owned domain models before product entry
changes:

- Agent state and one-run coordinator.
- Single-instance activation with narrow versioned intents.
- Tray, menu, and notification policy.
- Lazy Windows adapters for hotkey, tray geometry, monitor work area, and shell
  restart.
- Picker and Quiet Instrument presentation models.
- Normal Settings, Builder, Run Log, Approval Review, and Recipe Setup windows.
- Optional Desktop Work-Area and Spatial Field only after the core Agent flow is
  proven.

The default entry migration is not complete until:

- manual launch opens Picker through the Agent;
- startup is silent with tray only;
- no Home window appears at rest;
- no Canvas runtime window appears at rest;
- Agent-started runs use the Quiet Instrument;
- Home is removed from the release path after replacement surfaces pass.

The UI release gate is not complete until live integration and human usability
evidence are explicitly recorded. Machine structure tests and screenshots
cannot turn human UX into `PASS`.

## Non-Selected Paths

These paths are rejected for the canonical product direction:

- Home as the default launch surface.
- Home as a permanent compatibility shell.
- Canvas `ApplicationWindow` as the everyday runtime shell.
- A generic dashboard with a wall of cards.
- A permanent runtime sidebar.
- A visible application window at rest.
- Multiple independent attended runtime windows.
- Notification approval or notification-run actions.
- Desktop Work-Area as the default shell.

## Safety Constraints

This decision adds no new automation capability.

The migration must not add arbitrary recipe Python, JavaScript, PowerShell,
shell snippets, QML, or HTML; coordinate clicks; recording, Watch Me, OCR,
keylogging, screenshots, macro replay, browser-history collection, cloud sync,
remote execution, network command channels, gameplay automation, password
automation, shell replacement, taskbar hiding, kiosk mode, Wallpaper Engine
replacement, marketplace behavior, or new mutating primitive families.

Imported or shared behavior never auto-runs. Consequential actions remain
behind explicit confirmation gates.
