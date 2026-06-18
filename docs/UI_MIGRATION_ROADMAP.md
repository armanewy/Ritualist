# Ritualist UI Migration Roadmap

This roadmap turns the accepted Quiet Instrument design into executable phases.
It is scoped to the tray-first UI migration and does not authorize new
automation capabilities.

Quiet Instrument is the selected product direction. The migration removes the
current Home-default path after replacement surfaces pass acceptance. Home is a
current baseline and dead-end, not a long-term compatibility surface.

## Baseline To Replace

Current baseline at `4789b4c1b1795b89d91d109050c9153b9e41f13a` or later:

- Home is the default launch surface.
- Home spawns Room processes.
- Canvas Use Mode is a separate `ApplicationWindow`.
- Gaming recovery is complete and must be preserved.
- Live integration and human UX remain `NOT_RUN`.
- Release readiness must not be claimed without live and human evidence.

## Migration Map

| Current item | Target item | Migration rule | Exit evidence |
| --- | --- | --- | --- |
| `Ritualist.exe` opens Home | Resident Agent opens silently at startup and Picker on manual activation | Default entry moves to the Agent; Home is removed after replacement passes | Packaged manual launch opens Picker through one Agent; startup shows tray only |
| Home Room launcher | Contextual Picker | Picker exposes current Room, search, recents, browse all, Builder, and return to active | Picker tests and screenshots at 100/125/150% show no dashboard shell |
| Home-spawned Room process | Single Agent activation and one-run coordinator | Second process redirects narrow intent and exits | Single-instance tests; no duplicate active runtime process |
| Canvas `ApplicationWindow` runtime shell | Quiet Instrument owned by Agent | Active run uses one compact Instrument; Canvas no longer appears for Agent-started runs | Packaged active-run evidence shows no Home or Canvas runtime window |
| Canvas Use Mode everyday desktop | Optional Desktop Work-Area layer | Desktop layer is explicit and used only when spatial context matters | Work-Area acceptance proves taskbar/wallpaper boundaries and no shell replacement |
| Runtime cards and panels | Quiet Instrument states | Ready, running, waiting, confirmation, failure, recovery, and completion are one stateful surface | State evidence shows changed wording, geometry, icon, agency, and action set |
| Home privacy/settings controls | Normal Settings window | Settings owns invocation, appearance, notifications, approvals, browser/media, privacy, about | X/Alt+F4 close window only; Agent continues |
| Home/Canvas activity evidence | Run Log window | Run chronology and artifacts move into an Editorial Ledger-style normal window | Run Log tests show status taxonomy and no raw secrets |
| Existing remembered approvals | Approval Review window and owned confirmation | Review and revoke approvals through exact scoped data | Approval tests show no bulk approve and no notification approval |
| Canvas Edit Mode | Room Builder window | Builder becomes a normal focused authoring surface; layout workspace is secondary | Builder does not execute behavior and warns about approval impact |

## Implementation Phases

### Phase 0 - Contract, Baseline, And Truth Model

Scope:

- Create the canonical binding product contract.
- Capture the current UI/process baseline from the packaged app.
- Create explicit UI release truth gates.

Exit criteria:

- Documents agree that the target is one resident Agent, tray icon, Picker,
  Quiet Instrument, owned confirmation, Settings, Room Builder, Run Log,
  Approval Review, and optional Desktop Work-Area layer.
- Baseline evidence records Home default, Home-spawned Room processes, Canvas
  `ApplicationWindow`, Gaming recovery, and `NOT_RUN` live/human UX.
- UI truth model keeps human usability as `NOT_RUN` and release not taggable.

### Phase 1 - Agent Domain Foundations

Scope:

- GUI-independent Agent state model.
- One attended ritual model.
- Local-only single-instance activation.
- Tray/menu/notification domain policy.
- Lazy Windows adapters for hotkey, tray geometry, monitor work area, and shell
  restart.

Exit criteria:

- Unit tests pass on non-Windows using fakes.
- Activation intents are versioned and reject malformed or arbitrary payloads.
- Notification policy cannot approve, run, stop, or mutate consequential state.
- No product entry behavior changes yet.

### Phase 2 - Opt-In Resident Agent Skeleton

Scope:

- Add `Ritualist.exe --agent`, `--agent --startup`, and
  `--agent --open-picker` as opt-in paths.
- Own one tray icon, the stable right-click menu, local activation service, and
  explicit Exit.

Exit criteria:

- Startup silent shows no window.
- Tray tooltip reports `Ritualist - Ready`.
- Right-click menu works.
- Redirected activation reaches the existing Agent.
- Closing any temporary surface does not exit the Agent.
- Runtime behavior and Gaming semantics do not regress.

### Phase 3 - Contextual Picker

Scope:

- Implement shared light tokens and Picker model/controller/QML.
- Wire left-click tray, hotkey, and redirected activation to the same Picker.
- Selection opens preflight and never executes directly.

Exit criteria:

- Picker is a transient Qt Tool-style surface, omitted from taskbar and Alt+Tab
  while remaining keyboard and Narrator activatable.
- Escape, outside click, and hotkey dismiss when idle and restore focus.
- It fits 400 x up to 520 epx by default and 336 epx minimum width.
- No permanent sidebar, dashboard tiles, internal IDs, or double-click start.
- 100%, 125%, and 150% placement and clipping tests pass.

### Phase 4 - One Quiet Instrument

Scope:

- Present Ready/preflight, Running, Waiting, Confirmation, Failure, Recovery,
  Completion, and collapsed states from existing runtime data.
- Route background confirmation/failure/recovery notifications to review.
- Enforce one attended ritual globally.

Exit criteria:

- Picker -> Ready/preflight -> Start -> Running -> Waiting/Confirmation/Failure/
  Recovery -> completion -> collapse to tray works in packaged evidence.
- Agent-started runs do not open Home or Canvas runtime panels.
- Closing or collapsing the Instrument never stops the run.
- A second attended ritual returns to active or requires stop-and-switch.
- Notification actions open review only.

Stop after this phase for a human prototype review. Do not proceed if the tray,
Picker, or Instrument still feels like a smaller dashboard.

### Phase 5 - Normal Review And Configuration Windows

Scope:

- Settings model/controller and QML.
- Run Log window.
- Approval Review window.
- Recipe View and Edit Setup window.

Exit criteria:

- Settings, Run Log, Approval Review, and Recipe Setup are normal resizable
  taskbar/Alt+Tab windows.
- X and Alt+F4 close the window only.
- Explicit Exit remains separate.
- Approval Review can revoke but cannot create or bulk approve approvals.
- Recipe Setup can Doctor, Dry Run, validate, and save setup without running.
- No raw secrets, raw IDs, or raw exceptions appear in primary UI.

### Phase 6 - Room Builder And Optional Desktop Work-Area

Scope:

- Structured Room Builder model/controller and QML.
- Decouple Canvas Use Mode from everyday runtime.
- Add Spatial Field only for meaningful layout-changing preflight.

Exit criteria:

- Builder is a normal focused authoring window and never executes behavior.
- Editing does not overlap a live run surface.
- Active runtime state stays in the Agent's Quiet Instrument.
- Desktop Work-Area is explicit opt-in and never the default shell.
- Spatial Field does not move windows during preview and is not shown for every
  ritual.

Stop after this phase for a human product review before default-entry removal.

### Phase 7 - Run Isolation And Lifecycle Hardening

Scope:

- Local worker-process protocol for attended runs.
- Suspend/resume and crash recovery.
- Close, exit, startup, Explorer restart, and lifecycle hardening.
- Elevation boundary specification and tests only.

Exit criteria:

- Agent owns tray, UI, approvals, run state, and journal.
- Worker receives only validated recipe/policy snapshots and local IPC.
- Worker crash or Agent restart becomes failed/interrupted and never removes
  evidence.
- Sleep/resume revalidates targets and does not blindly repeat unknown side
  effects.
- Resident Agent never runs elevated.

### Phase 8 - Default Entry Migration And Home Removal

Scope:

- Manual launch starts or activates the Agent and opens Picker.
- Sign-in startup starts Agent silently.
- Home no longer owns default launch or independent attended runs.
- Remove Home from the release path after replacement acceptance passes.

Exit criteria:

- No arguments mean manual activation/open Picker, not Home.
- Startup creates tray only with no window and no toast.
- One instance is enforced.
- Settings and Builder are normal windows.
- No Home window at rest.
- No Canvas window at rest.
- Exit removes tray icon and resident process.
- Any temporary development-only Home entry is removed before release
  readiness.

### Phase 9 - DPI, Accessibility, Focus, And Visual Hardening

Scope:

- Per-monitor DPI.
- Keyboard, Narrator, High Contrast, Reduced Motion.
- Focus and fullscreen behavior.
- Visual matrix over wallpaper and scaling fixtures.

Exit criteria:

- Picker, Instrument, Confirmation, Settings, and Builder fit at 100%, 125%,
  150%, and smoke 200%.
- Critical keyboard paths have no traps and restore focus.
- Background progress never steals focus.
- Full-screen games are not minimized or covered by routine state changes.
- Visual matrix records bounds, clipping, blank surfaces, internal IDs, and
  overlapping runtime windows.
- Human-only visual and usability statuses remain `NOT_RUN` or
  `NEEDS_HUMAN_REVIEW` until explicitly reviewed.

### Phase 10 - Human Validation And Release Gate

Scope:

- Packaged tray-first acceptance.
- Human usability evidence package.
- Independent adversarial release critique.

Exit criteria:

- Packaged flow proves startup tray-only, manual Picker activation, one Agent,
  Ready/preflight, state sequence, Settings, Builder, Run Log, Approval Review,
  close semantics, and explicit Exit.
- Live Gaming integration is run separately and recorded.
- Human usability evidence records participant profiles, scripts, metrics,
  severity, blockers, and explicit decision.
- Release is rejected if Home still opens by default, multiple runtime windows
  remain, UI resembles a dashboard, internal IDs leak, focus is stolen, DPI
  clipping remains, keyboard/Narrator paths fail, live Gaming remains
  `NOT_RUN`, or human UX remains `NOT_RUN`.

## Validation Policy

Every implementation phase must return exact changed files, validation commands
and results, unresolved limitations, and confirmation that no forbidden
capability was added.

Machine tests may prove structure, state, and absence of forbidden behavior.
They may not grant human usability. Screenshots alone may not grant visual
contract pass without explicit review.
