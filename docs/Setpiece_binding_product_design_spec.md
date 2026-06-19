# Setpiece Binding Product Design

This document is the canonical repository contract for the accepted Setpiece
binding UI/UX direction. Where this document conflicts with older Home, Canvas,
or compatibility language, this document wins.

Quiet Instrument is the selected direction. The product is tray-first, local,
attended, and calm. It is not a dashboard shell, a desktop replacement, a
widget platform, or a second automation framework.

## Current Baseline

The current functionality baseline is commit
`4789b4c1b1795b89d91d109050c9153b9e41f13a` or later.

Current product state:

- `Setpiece.exe` opens Home by default.
- Home remains visible while the user chooses work.
- Home launches Room surfaces by spawning separate Room processes.
- Canvas Use Mode is still a separate `ApplicationWindow`.
- Canvas owns too many everyday runtime responsibilities in one QML surface.
- Gaming functionality recovery is complete: state-driven Gaming Mode, native
  browser handoff by default, managed browser mode as explicit opt-in,
  Battle.net readiness checks before Play approval, exact target invocation,
  postcondition verification, scoped remembered approvals, recipe
  transparency, setup overrides, and the live Gaming acceptance harness remain
  part of the functionality baseline.
- Release truth is not complete: live integration is `NOT_RUN`, human UX is
  `NOT_RUN`, and release readiness must not be claimed.

Home and Canvas-as-runtime-shell are baseline evidence and migration inputs.
They are not the target product contract. Once the replacement surfaces pass
their acceptance gates, Home is removed from the default path and then removed
as dead code rather than kept as a permanent compatibility surface.

## Product Decision

Setpiece runs as one resident per-user local Agent. At rest there is no visible
application window. The user invokes Setpiece through the tray icon, the
configured hotkey, Start/Search activation, or explicit secondary windows.

The everyday shell is:

1. Tray icon.
2. Contextual Picker.
3. One Quiet Instrument for the active ritual.
4. Owned confirmation and review surfaces.
5. Normal Settings, Room Builder, Run Log, and Approval Review windows.
6. Optional Desktop Work-Area layer when a Room genuinely needs desktop
   spatial context.

The Agent owns invocation, active-run state, confirmation presentation,
notifications, close/exit semantics, and one-attended-ritual enforcement. The
runtime engine continues to own recipe execution semantics, Doctor, dry-run,
policy, logging, recovery data, and target verification.

## Target Architecture

```text
Windows user session
  -> resident per-user Agent
      -> QSystemTrayIcon
      -> local-only single-instance activation
      -> configurable hotkey, default Win+Ctrl+R
      -> contextual Picker
      -> Quiet Instrument
      -> owned confirmation surface
      -> Settings window
      -> Room Builder window
      -> Run Log window
      -> Approval Review window
      -> optional Desktop Work-Area layer
      -> existing runtime engine and run journal
```

Architectural requirements:

- Exactly one Agent is resident per Windows user.
- Activation is local-only. No TCP listener, remote command channel, cloud sync,
  or network control plane is part of this design.
- The Agent has no visible window at rest.
- A second launch redirects a versioned, structured activation intent to the
  resident Agent and exits.
- Activation intents are narrow product intents, not arbitrary commands.
- Windows-specific imports stay lazy and inside adapter methods.
- Tests use fakes and must pass without a Windows desktop session.
- Existing safe execution contracts remain intact: no arbitrary recipe Python,
  JavaScript, PowerShell, shell snippets, QML, or HTML; no coordinate clicks;
  no recording, OCR, keylogging, screenshots, macro replay, password
  automation, gameplay automation, shell replacement, taskbar hiding, kiosk
  mode, marketplace behavior, cloud sync, or remote execution.

## Surface Responsibilities

| Surface | Target responsibility | Must not own |
| --- | --- | --- |
| Resident Agent | Per-user lifecycle, tray ownership, activation routing, one attended ritual, notification policy, surface orchestration, run-state presentation model | Recipe parsing, arbitrary command execution, network command channels |
| Tray icon | At-rest presence, state tooltip, left-click invocation, right-click menu, explicit Exit | Hidden run start, hidden approval, unique double-click behavior |
| Contextual Picker | Search, current Room, recent rituals, browse all, change Room, open Builder, return to active ritual | Direct ritual execution, dashboard tiles, permanent navigation shell |
| Quiet Instrument | Ready/preflight, running, waiting, confirmation, failure, recovery, completion, pause/resume/stop where already safe | Multiple concurrent runtime panels, recipe editing, broad logs, approval revocation |
| Owned confirmation | Exact consequence, target, risk, preserved work, Allow once, Always allow local where policy permits, Cancel, review details | Notification approval, bulk approve, vague or technical primary wording |
| Settings | Invocation, appearance, notifications, approvals, browser/media, privacy/diagnostics, about, explicit Exit | Running rituals or changing recipe behavior silently |
| Room Builder | Structured Room and ritual authoring, validation, Doctor/Dry Run preview, layout workspace when needed | Runtime ownership, live-run controls, arbitrary QML/HTML/JS/Python |
| Run Log | Chronology, artifacts, completed/failed/not-run/declined/stopped/interrupted/recovered states, diagnostics copy | Secret exposure, raw exception primary UI |
| Approval Review | Search, inspect, revoke remembered approvals, clear with confirmation | Creating approvals, running rituals, notification approval |
| Desktop Work-Area layer | Optional explicit spatial Room layer over the normal desktop when layout matters | Default shell, wallpaper renderer, taskbar owner, fullscreen/kiosk surface |
| Home | Current baseline and migration evidence only | Canonical default entry, independent run ownership, permanent compatibility role |
| Canvas `ApplicationWindow` | Current baseline and optional layer implementation input | Everyday runtime shell, default active-run surface |

## Binding Behavior

### Left-Click

Left-clicking the tray icon invokes Setpiece:

- If idle, open or focus the contextual Picker near the tray, cursor, or target
  monitor work area.
- If an attended ritual is active, open the active Quiet Instrument instead of
  starting another ritual.
- If a background confirmation is pending, open the owned confirmation or
  Approval Review state for that exact run.
- Double-click has no unique action.

### Right-Click

Right-clicking the tray icon opens a stable shortcut menu:

- Open Setpiece.
- Active ritual... when one exists.
- Rooms...
- Recent rituals...
- Run Log.
- Settings.
- Exit Setpiece.

The active submenu may expose Show ritual, Pause or Resume when supported,
Stop ritual..., Open current target when meaningful, and View run details.

### Hotkey

The default hotkey is `Win+Ctrl+R`. It performs the same product invocation as
tray left-click. It must not install global hooks, record keystrokes, or observe
input outside the narrow hotkey registration.

### Close Versus Exit

Closing any Picker, Instrument, Settings, Builder, Run Log, Approval Review, or
Desktop Work-Area surface closes or hides only that surface. The Agent remains
resident. An active run continues unless the user explicitly chooses a supported
Stop action.

Exit is a separate explicit command named `Exit Setpiece`. If no attended run
is active, it closes the Agent and removes the tray icon. If an attended run is
active, Exit requires an explicit confirmation explaining that the run must stop
before the Agent exits.

### Active-Run Collapse

Only one compact Quiet Instrument represents an active attended ritual. It may
collapse to the tray when the user dismisses it or after completion. Collapsing
never stops a run. Reopening returns to the exact current state.

Routine progress does not create additional taskbar windows. Failure,
confirmation, and recovery can open focused review surfaces when the user asks
or when notification policy says the run is hidden and attention is required.

### Notification Rules

Notifications are state-routing affordances, not command surfaces.

- No notification on startup.
- No notification for ordinary visible progress.
- No notification for short visible success.
- A hidden/background confirmation may notify and open Review.
- A hidden/background failure may notify and open the failed run state.
- Interrupted recovery may notify and open Recovery Review.
- Long hidden completion may use an optional quiet completion notification.
- Notification actions may open the relevant review surface.
- Notification actions may never approve a consequential action, run a ritual,
  stop a ritual, or mutate state beyond opening the owned surface.

### One Attended Ritual

There is at most one attended ritual per Windows user.

- Starting another attended ritual while one is active returns to the active
  ritual or requires an explicit stop-and-switch decision.
- Shortcuts are native handoffs and do not occupy the attended-run slot.
- Doctor, Dry Run, Builder preview, and read-only inspection do not occupy the
  attended-run slot unless they become an attended run by explicit design.
- The one-run rule is enforced in the Agent model, activation routing, and UI.

## Visual Contract

Setpiece uses a light, warm, mostly opaque default expression called
Setpiece Paper. The visual system is quiet and task-focused, not decorative.

Required tokens:

- Typography: Segoe UI Variable, falling back to Segoe UI; sentence case;
  minimum 12 epx body text.
- Surfaces: warm canvas and panel colors, opaque confirmation surfaces, restrained
  Windows-derived accent color.
- Semantic states: running, waiting, confirmation, failure, recovery,
  completed, stopped, and interrupted have distinct wording, iconography,
  geometry, and available actions. Color alone is never the state signal.
- Geometry: 4 epx base, 8/12/16/24/32 epx rhythm, 10 epx outer radius, 6 epx
  control radius, 40 epx primary hit target, one outer shadow only.
- Motion: 120-160 ms transient flyout, 180-220 ms state changes, and a Reduced
  Motion path that removes motion or keeps only a short fade.
- Accessibility: High Contrast, Reduced Motion, keyboard navigation, Narrator
  names/roles/states, focus restoration, and 100%, 125%, and 150% Windows
  scaling are acceptance requirements.

Anti-style rules:

- No gamer neon.
- No generic SaaS dashboard.
- No wall of elevated cards.
- No permanent runtime sidebar.
- No excessive pills.
- No dark fixed application shell as the default.
- No large Home-style launch surface at rest.
- No internal IDs, raw exceptions, raw run paths, or low-level policy terms in
  primary UI.
- No state changes that only recolor the same layout.
- No UI that implies background automation, recording, observation, remote
  control, or hidden approval.

## Release Truth

This design contract does not make a release taggable by itself.

Release evidence remains honest:

- Engine tests passing is not a UI release pass.
- Simulated acceptance passing is not live integration.
- `live_integration_pass` remains `NOT_RUN` until executed against real user
  applications.
- `human_ux_pass` remains `NOT_RUN` until a person explicitly approves the UX.
- Ambiguous visual evidence is `NEEDS_HUMAN_REVIEW`, not `PASS`.
- `release_pass` remains false while required live or human gates are `NOT_RUN`
  or `FAIL`.
