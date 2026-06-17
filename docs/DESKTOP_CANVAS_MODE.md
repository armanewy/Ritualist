# Ritualist Desktop Work-Area Canvas

Desktop Work-Area Canvas is the next desktop-canvas direction for Ritualist. It
is a host-mode design for making a Room feel like the desktop while keeping
Windows visibly available.

The product goal is:

- Ritualist should feel like the desktop, but not make users feel trapped inside
  Ritualist.
- The first desktop-canvas host occupies the Windows work area above the
  taskbar.
- The taskbar remains visible as a trust and recovery surface.
- Explorer remains the Windows shell.
- Home and windowed Canvas remain available as compatibility and recovery
  surfaces.

This document defines the host model before implementation. It does not add
shell replacement, taskbar hiding, kiosk mode, arbitrary QML/HTML/JS/Python,
coordinate clicks, cloud sync, remote execution, marketplace behavior, gameplay
automation, password automation, or risky/mutating primitives.

## Terms

- **Room** is the user-facing product surface for an activity.
- **Canvas** is the implementation layer: schema, component registry, runtime
  model, view model, and QML renderer.
- **Host mode** controls how the same Canvas renderer is placed on the desktop.
- **Desktop Work-Area Canvas** is the first desktop-canvas host: borderless or
  seamless, sized to the Windows work area, and leaving the taskbar visible.
- **Use Mode** is the interactive Room surface.
- **Edit Mode / Room Builder** edits typed components through validation and
  explicit save/cancel flows.

## Host Modes

### `windowed`

The existing behavior. Ritualist opens Canvas Use Mode as a normal Qt
application window with title bar, taskbar presence, normal z-order behavior,
and normal close controls.

Requirements:

- Default mode for every existing launch path until a user explicitly chooses a
  desktop host.
- Always available even if every other host mode is disabled.
- Must not require a Windows desktop session in automated non-Windows tests.
- Must preserve current Canvas action, confirmation, run-control, Watch Me, and
  Edit Mode behavior.

### `desktop_work_area`

The first Desktop Canvas Mode. It is an opt-in borderless or seamless Room
surface sized to the selected Windows work area, not the full monitor.

Requirements:

- Explorer remains the shell.
- Taskbar remains visible and usable.
- Window bounds match monitor work area, not full monitor.
- A safe exit affordance is always visible.
- Escape or a documented safe shortcut exits Desktop Work-Area Canvas.
- Windowed fallback is always available.
- Confirmation dialogs remain native/top-level and appear above external apps.

Non-requirements:

- No startup registration.
- No shell registry mutation.
- No taskbar hiding.
- No desktop icon hiding.
- No fullscreen default.
- No kiosk or lock-in behavior.

### `desktop_full_monitor_later`

An optional future mode that covers the full monitor while explicitly active. It
is disabled by default and is not part of the first Desktop Canvas Mode.

Requirements before enabling:

- `desktop_work_area` is stable.
- The mode is clearly labeled as advanced or immersive.
- It must not hide, disable, or mutate the Windows taskbar.
- It must not register as the shell or take over startup.
- Escape/safe exit must work.
- Windowed fallback remains available.
- Confirmation dialogs and stop controls remain visible above content.

If a future policy value is needed for this behavior, use language such as
`cover` or `full_monitor`, not `hide_taskbar`.

### `desktop_attached_experimental_later`

An optional future Rainmeter-like or wallpaper-layer experiment. This is not
part of the first Desktop Canvas Mode.

Requirements before enabling:

- `desktop_work_area` is stable.
- Windows-version guard is present.
- Fallback to `desktop_work_area` or `windowed` is automatic.
- Crash-safe recovery is tested.
- Acceptance evidence proves shell registry and startup state are unchanged.
- Feature flag or explicit experimental opt-in is required.

This mode must still not replace Explorer, hide the taskbar, register as shell,
or run at startup without explicit user-owned configuration.

### `immersive_couch_later`

An optional future fullscreen or couch mode for gaming and media contexts. It is
separate from Desktop Work-Area Canvas and disabled by default.

Requirements:

- Not kiosk mode.
- Not shell replacement.
- Escape/safe exit must work.
- Windowed fallback remains available.
- Confirmation dialogs and stop controls remain visible above content.

### `advanced_shell_later`

A research-only label for possible lab, kiosk, classroom, or appliance-style
deployments. It is outside the current product line.

Requirements before any future work:

- Separate security design.
- Separate recovery design.
- Separate installer/uninstaller design.
- Explicit release-owner approval.
- Dedicated acceptance harness and manual recovery drill.

This mode must not be implied by `Room`, `Canvas`, `desktop_work_area`,
`desktop_full_monitor_later`, or `immersive_couch_later`.

## Taskbar Policy

The taskbar is a trust and recovery surface, not visual clutter to remove.
Ritualist should preserve a visible connection to Windows in the first Desktop
Canvas Mode.

Allowed implemented value now:

```text
taskbar_policy: respect
```

Disallowed values now:

```text
hide
auto_hide
replace
kiosk
```

The first implementation must not add taskbar hiding, taskbar auto-hide,
taskbar replacement, or kiosk behavior. A later full-monitor mode may document a
`cover` or `full_monitor` policy, but it must still avoid taskbar mutation and
must remain opt-in.

## Safety Invariants

All host modes must preserve these invariants unless a future separate design
explicitly supersedes them:

- Explorer remains the Windows shell.
- `desktop_work_area` respects the taskbar.
- No shell registry mutation.
- No startup takeover.
- No taskbar hiding.
- No kiosk mode.
- No arbitrary component code.
- No arbitrary user-supplied QML, HTML, JavaScript, Python, shell, or
  PowerShell.
- No untrusted widget execution.
- No remote execution.
- No cloud sync or marketplace activation.
- No password automation.
- No gameplay automation.
- No coordinate-click automation added by host work.
- Safe exit is always visible in non-windowed modes.
- Windowed fallback is always available.
- Risky desktop actions still use explicit confirmation gates.
- Native/top-level confirmation remains above external foreground windows.
- Tests must pass on non-Windows with fakes or mocks.
- Windows UI Automation imports remain lazy and inside adapter or harness code.

## Windows Host Capabilities

Desktop Work-Area Canvas implementation needs a small host layer around the
existing Canvas renderer. The host layer should expose typed data and policy
decisions; it should not add new automation primitives.

Required capabilities:

- Monitor enumeration.
- Primary-monitor detection.
- Stable monitor ids or names when Windows exposes them.
- Monitor work-area geometry.
- Full-monitor geometry for later full-monitor modes.
- DPI scale per monitor.
- Coordinate transform from Canvas logical units to host pixels.
- Z-order policy.
- Taskbar-respect policy.
- Hit-test/pass-through policy.
- Safe exit affordance policy.
- Tray, escape, or safe-mode recovery hooks.

The first implementation should keep these capabilities small and testable:

```text
Canvas document
-> Canvas runtime/view model
-> QML renderer
-> host mode
```

The renderer should not fork per host mode. Host mode changes window flags,
geometry, z-order, and exit/recovery affordances around the same typed Canvas
payload.

## Z-Order Policy

`windowed` uses normal application z-order.

`desktop_work_area` should be visible as the Room surface while avoiding shell
takeover behavior. It should not use always-on-top for ordinary operation unless
there is a documented, temporary reason. Confirmation dialogs are separate:
they must remain top-level and foreground-safe because they protect risky
actions.

The acceptance harness must record:

- top-level window list
- foreground window
- Ritualist window title and process id
- confirmation dialog z-order relative to fake external apps
- taskbar visibility evidence where available

## Hit-Test Policy

The hit-test design should be explicit before desktop host work expands.

Use Mode options:

- `capture_all`: the Room surface receives all input inside its window.
- `component_only`: only component bounds receive input; blank canvas can pass
  through or be ignored by Ritualist.
- `disabled`: no pass-through; normal window behavior.

Edit Mode must capture input inside the Canvas because drag, resize, selection,
grid, and property editing need predictable behavior.

The first Desktop Work-Area Canvas MVP may start with normal window capture if
component-only pass-through is not implemented yet, but it must document the
limitation and must keep the visible exit control.

## Recovery Policy

Every non-windowed host must provide at least two recovery paths:

- Visible exit control inside the Room.
- Keyboard safe exit, such as Escape or a documented shortcut.

Future recovery additions:

- tray icon with "Exit Desktop Canvas"
- config or environment safe mode that forces `windowed`
- crash marker that relaunches in `windowed`
- acceptance evidence for safe-mode fallback

Recovery must not rely on a user editing registry keys, killing Explorer, or
knowing hidden command-line flags.

## Acceptance Harness Requirements

Desktop Canvas host work must extend acceptance evidence before it is considered
release-ready.

For `windowed`:

- packaged Home opens visibly
- packaged Canvas Use Mode opens visibly
- packaged classic GUI opens visibly
- confirmation z-order remains trustworthy
- current v0.2 release acceptance remains green

For `desktop_work_area`:

- Desktop Work-Area Canvas opens visibly from source and packaged entry points
- window bounds match selected monitor work area, not full monitor
- taskbar remains visible and usable
- Explorer process remains running
- shell registry keys are not changed
- no startup entries are added
- process tree and top-level window tree are captured
- monitor geometry, work area, and DPI scale are captured
- screenshot/frame evidence is nonblank
- app heartbeat evidence has bounded gaps
- safe exit control is visible and works
- keyboard safe exit works
- fallback to `windowed` works
- confirmation dialog appears above fake Chrome/Battle.net foreground windows
- run controls still work during active waits/runs
- imported Canvas/theme packs still do not auto-run behavior

For `desktop_full_monitor_later`:

- all applicable `desktop_work_area` evidence
- explicit opt-in evidence
- evidence that the taskbar was not hidden, disabled, or mutated
- clear fallback evidence

For `desktop_attached_experimental_later`:

- all applicable `desktop_work_area` evidence
- Windows-version guard evidence
- fallback evidence when attach fails
- crash-recovery evidence
- explicit experimental warning evidence

## Implementation Sequence

1. **Design only**
   - Define host modes, taskbar policy, invariants, recovery, and acceptance.

2. **Host abstraction**
   - Add typed host-mode model and config.
   - Keep default behavior `windowed`.
   - Define `desktop_work_area` as the first desktop-canvas target.
   - Reject unsupported or unsafe host selections.
   - Allow only `taskbar_policy: respect` initially.

3. **Desktop Work-Area Canvas MVP**
   - Add opt-in `desktop_work_area`.
   - Size to work area.
   - Respect taskbar.
   - Add visible and keyboard exit.
   - Extend packaged acceptance evidence.

4. **Interaction hardening**
   - Add monitor selection.
   - Record DPI and geometry evidence.
   - Define and test hit-test/pass-through policy.
   - Add tray/safe-mode recovery.

5. **Experimental desktop-attached research**
   - Only after Desktop Work-Area Canvas is stable.
   - Guard behind explicit experimental opt-in.

6. **Immersive/full-monitor research**
   - Separate opt-in mode for media, couch, or full-monitor contexts.
   - Still not kiosk or shell replacement.

7. **Advanced shell research**
   - Out of current product scope.

## Non-Goals

Desktop Canvas Mode must not become:

- a Windows shell replacement
- a taskbar replacement
- a kiosk system
- a startup/login manager
- a remote execution surface
- a marketplace widget runtime
- an arbitrary-code component system
- a password automation tool
- gameplay automation
- a true virtual desktop or security boundary

The goal is a visible, local, policy-gated Room surface that makes repeated
desktop activity setup feel coherent while preserving normal Windows ownership
and recovery.
