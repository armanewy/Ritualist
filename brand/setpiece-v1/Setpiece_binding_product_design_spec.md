# Setpiece — Binding Product Design Specification

**Status:** Research synthesis for prototype design; no production code and no high-fidelity UI generated.
**Date:** June 18, 2026
**Selected direction:** Quiet Instrument

## 0. Scope and evidence boundary

The five pasted prompts were treated as parallel research workstreams: tray behavior, visual direction, window/process architecture, permission design, and human usability testing. Their results are reconciled here into one binding specification rather than presented as equal alternatives.

Only the pasted Markdown brief was available in the working set; no current Setpiece screenshots were attached. Therefore, the current-state critique below is based on the brief’s explicit observations—multiple Home/Canvas windows, dark dashboard styling, overlap, leaked IDs, weak adaptation, technical confirmations, and excessive visual presence—not on pixel-level inspection.

The brief also establishes these immovable constraints:

- Windows, the taskbar, Explorer, and the user’s wallpaper remain in control.
- Setpiece is a Windows-first local attended runbook engine, not a shell replacement.
- Setpiece is absent at rest except for its notification-area icon.
- No Watch Me, screenshots, OCR, keylogging, macro recording, or input recording.
- Shortcuts are immediate native actions; rituals are attended multi-step procedures.
- The default is light, calm, mature, and non-gamer.
- Everyday run surfaces are transient or compact; Settings and Builder may be normal windows.
- Keyboard, Narrator, High Contrast, and 100%, 125%, and 150% Windows scaling are first-class requirements.

---

## 1. Binding decisions

| Area | Decision |
|---|---|
| Product posture | A quiet notification-area utility that orchestrates Windows, then recedes. It is not a dashboard or destination app. |
| Default invocation | Left-click tray icon or `Win+Ctrl+R`. Both open the same contextual flyout. The shortcut is user-configurable and conflict-checked. |
| Tray behavior | Left-click toggles the contextual flyout. Right-click opens a stable shortcut menu. Double-click has no unique action and is de-bounced to the single-click behavior. |
| At rest | No visible window. No taskbar button. Tray tooltip reads “Setpiece — Ready.” |
| Active run | Tray icon and tooltip communicate state. A compact edge-anchored Quiet Instrument can remain open or collapse back to the tray. |
| Process model | One single-instanced per-user resident Agent owns the tray, run state, journal, notifications, and UI surfaces. Individual action execution is isolated in disposable worker processes. Elevation occurs only in an on-demand elevated helper for the exact privileged action. |
| Everyday surfaces | Contextual tray flyout, Room/Ritual picker, Quiet Instrument, and owned confirmation. They do not appear in the taskbar or Alt+Tab, but remain fully activatable and accessible. |
| Normal windows | Settings, Room Builder, detailed Run Log, and Approval Review use ordinary Windows windows and do appear in taskbar/Alt+Tab. |
| Visual direction | Quiet Instrument is the shell. Editorial Ledger patterns structure details, logs, and recovery. Spatial Field appears only as an optional preflight window-layout preview. |
| Material | Mostly opaque, lightly warm neutral surfaces. Mica may back long-lived Settings/Builder windows. Acrylic is optional only for small transient flyouts and must fall back to an opaque matte. |
| Notifications | No start toast and no routine short-success toast. Toast only for action required, failure, interrupted recovery, or meaningful completion while Setpiece is not visible. A confirmation toast opens review; it never directly approves a consequential action. |
| Safety | Broad product consent never substitutes for narrow action approval. Imported rituals begin in Restricted mode. Remembered approval is content-addressed and target-specific. High-risk actions always ask. |
| Active-run concurrency | One attended ritual per Windows user in v1. Starting another offers “Return to active ritual” or “Stop and switch”; it never silently runs both. |
| Browser ambience | Normal signed-in browser handoff is the default and playback is not claimed as verified. Managed-browser automation is explicit, separately labeled, and may minimize only after media progression is verified. |
| Close versus Exit | Closing any UI hides/closes that surface; it never exits the resident utility and never stops a run. “Exit Setpiece” is explicit in the tray menu. Alt+F4 and the window close button have the same meaning. |

---

## 2. Parallel research synthesis

| Workstream | Binding conclusion |
|---|---|
| R1 — Notification-area patterns | Use the tray primarily as a persistent status anchor and entry point, not as a huge command menu. Keep direct access to Rooms, recent rituals, active state, logs, Settings, and Exit. |
| R2 — Light visual system | Select Quiet Instrument: one compact, lightly warm, wallpaper-conscious surface with a single dominant action and inline progressive disclosure. |
| R3 — Window/process architecture | Replace Home plus spawned Canvas windows with one resident Agent and a small set of owned surfaces. Separate UI lifecycle from run lifecycle. |
| R4 — Permission friction | Request capability at the moment it becomes relevant, allow exact remembered approvals for bounded medium-risk actions, and invalidate them on any recipe or target change. |
| R5 — Human validation | Test comprehension and trust, not only completion. “What happens next?” must be answerable in two seconds in every operational state. |

---

## 3. Reference matrix

| Reference | Pattern observed | Borrow | Avoid |
|---|---|---|---|
| Windows notification area | Persistent status icon, expected left-click content, conventional right-click menu, proximity anchoring | Use the icon as a stable state anchor and place the flyout near the actual tray interaction | Treating the tray as a generic launcher containing the entire product |
| Windows system flyouts | Compact, light-dismiss, keyboard-contained surfaces | Light-dismiss for idle selection; clear focus return to the tray | Making consequential decisions disappear on outside click |
| Windows app notifications | Timely information and contextual actions outside the app | Use for attention needed while Setpiece is hidden | Using notifications as a substitute for durable run state |
| PowerToys Quick Access | Tray icon can open a compact utility flyout while Settings remains separate | Distinguish quick operation from full configuration | Recreating PowerToys’ utility dashboard inside Setpiece |
| PowerToys Awake | Tray icon and tooltip encode persistent mode | Use stable icon variants and plain-language tooltips | Tiny animated iconography as the only state explanation |
| PowerToys Command Palette | One-keystroke invocation and recent/pinned results | Fast keyboard invocation and type-to-filter | Turning Setpiece into an everything-search palette |
| PowerToys Run | Configurable shortcut, preferred monitor, full-screen suppression | Detect shortcut conflicts and let users choose cursor/focused monitor | Stealing focus from full-screen games |
| PowerToys Workspaces | Capture and restore application positions | Preview the intended desktop scene before execution | Treating a captured layout as automatically safe or ready |
| EarTrumpet | Instant tray flyout, current-state tooltip, modern context menu | Compact, direct manipulation close to the taskbar | Off-screen flyouts, high-DPI breakage, or lingering task-switcher presence |
| Twinkle Tray | Single-purpose tray flyout resembling a system control | Immediate, narrow scope and strong native fit | Background behavior that minimizes full-screen applications |
| ShareX | Very broad tray command access | Keep frequently used entry points reachable | Long, uncurated tray menus that require scanning |
| OneDrive | Icon overlays distinguish progress, paused, blocked, and attention-needed states | A small stable state vocabulary with click-through detail | Depending on color or animation alone |
| Dropbox | Flyout combines status, recent activity, search, links, Settings, and Quit | Separate current status from deeper history | Letting recent activity become an always-visible feed |
| 1Password Quick Access | Tray or hotkey can summon a contextual, searchable picker | One equivalent invocation model across mouse and keyboard | Different mental models for tray and hotkey invocation |
| Bitwarden | Distinguishes close, hide to tray, and quit through explicit commands | Make “Exit Setpiece” explicit and document close behavior | Inconsistent meanings for X, Alt+F4, and Quit |
| Steam notifications | Current/new notifications are separated from historical notification review | Keep the flyout current and move history to Run Log | A permanent badge for old, already-reviewed events |
| Discord close-to-tray behavior | User confusion arises when X and Alt+F4 differ | Give both close mechanisms identical results | Hidden lifecycle rules users must memorize |
| Windows UAC | Consent appears when a privileged change is about to occur and identifies the requesting app | Keep elevation narrow, contextual, and delegated to Windows | Simulating secure-desktop styling or asking for blanket admin consent |
| VS Code Workspace Trust | Untrusted content is inspectable while execution is restricted | Imported rituals open in Restricted mode and can be reviewed safely | Enabling imported automation merely because it was opened |
| Windows Settings/Mica | Long-lived configuration windows use an opaque wallpaper-aware backdrop | Use Mica sparingly in Settings and Builder | Applying glass or transparency to every surface |

### What these references collectively imply

Setpiece should combine the immediacy of Twinkle Tray and EarTrumpet, the state legibility of OneDrive and PowerToys Awake, the invocation speed of 1Password and PowerToys Run, the scene preview of Workspaces, and the trust boundary of UAC plus Workspace Trust. It should explicitly reject ShareX-style menu growth, Discord-style close ambiguity, full-screen focus disruption, and activity-feed creep.

---

## 4. Current Setpiece critique

This critique uses the problem statements supplied in the brief rather than direct screenshot inspection.

| Dimension | Current problem | Binding correction |
|---|---|---|
| Hierarchy | Home and Canvas produce several equally prominent windows and surfaces. Runtime, editing, system state, and logs compete. | The hierarchy becomes: ritual identity and intent → current state/current step → next safe action. Everything else is progressively disclosed. |
| Density | Technical cards and panels make edge cases permanently visible. | The everyday surface shows one current step, one next action, one secondary escape, and at most two supporting facts. |
| Typography | Internal IDs and implementation language leak into user-facing labels; dark technical styling makes all content feel operationally urgent. | Use Segoe UI Variable, sentence case, plain verbs, human-readable targets, and monospace only for paths, timestamps, hashes, and diagnostics. |
| Composition | Spawned panels overlap and fail to adapt convincingly to changing window dimensions. | One owned instrument uses vertical flow and inline expansion. No free-floating runtime panels. Settings and Builder use deliberate responsive layouts. |
| State clarity | Technical confirmations and generic runtime panels blur Waiting, Confirmation, Failure, and Recovery. | Each state has a distinct agency model, icon, wording, geometry, and motion—not merely a different color or badge. |
| Wallpaper coexistence | Dark, visually dominant windows replace rather than coexist with the desktop. | At rest there is no window. Transient surfaces occupy a small taskbar-adjacent area with a high-opacity local matte. |
| Emotional quality | The product currently reads as a technical dashboard or game utility rather than calm desktop infrastructure. | Use calm competence: quiet success, precise failure, explicit consequence, no gamer neon, no mystical copy, and no celebratory animation. |

---

## 5. Visual-direction decision

### Direction comparison

| Direction | Strength | Risk | Decision |
|---|---|---|---|
| Quiet Instrument | Native-feeling, fast, wallpaper-friendly, and appropriate for frequent invocation | Can feel generic without excellent typography and state choreography | **Selected as the default product shell** |
| Spatial Field | Makes window arrangement and desktop consequences visible | Can become theatrical, complex across monitors, and too visually dominant | Use only for optional preflight layout preview and Builder visualization |
| Editorial Ledger | Excellent for sequence, diagnostics, auditability, and recovery | Too document-like for lightweight everyday invocation | Use as the expanded-details grammar inside Run Log, Recovery, and Builder |

### Final design thesis

**Setpiece is a quiet Windows instrument that appears at the edge of the desktop, states the current intent and consequence in plain language, asks only for the decision needed now, and then recedes.**

The product should feel like trusted operating-system infrastructure with a lightly warm human tone. It is neither an application dashboard nor a theatrical desktop skin. Its visual identity comes from rhythm, typography, state choreography, and restraint—not from decorative widgets, persistent glass, or chromatic effects.


---

## 6. Surface and process architecture

### 6.1 Recommended process model

```text
Windows user session
└─ Setpiece.Agent.exe  [single instance; starts at sign-in if enabled]
   ├─ Notification-area icon and activation routing
   ├─ Local ritual catalog, settings, approvals, and encrypted local secrets
   ├─ Run state machine and append-only run journal
   ├─ Flyout / Picker / Quiet Instrument / Confirmation ownership
   ├─ Settings / Builder / Log window ownership
   ├─ Windows notification activation
   └─ Setpiece.Worker.exe  [one disposable worker per action or bounded action group]
      └─ Setpiece.ElevatedHost.exe  [only when a single approved action requires elevation]
```

**Rules**

1. The Agent is single-instanced per signed-in Windows user. A second activation redirects its intent to the existing Agent and exits.
2. The run journal is written before and after every side effect: intended action, canonical target, approval identity, start time, result, and recovery checkpoint.
3. A worker crash fails only the active step. It must not take down the tray or erase the visible recovery path.
4. The elevated helper starts only for the exact privileged operation, receives a narrow signed request, returns a result, and exits. The resident Agent does not run elevated.
5. One attended ritual may be active at a time. Native shortcuts remain available unless they conflict with the active step.

### 6.2 Surface ownership diagram

```text
Setpiece.Agent
│
├─ Tray icon                         persistent, no taskbar/Alt+Tab entry
│  ├─ Contextual flyout              transient, light-dismiss when safe
│  └─ Shortcut menu                  transient, stable command structure
│
├─ Room/Ritual picker                transient tool window, keyboard-searchable
├─ Quiet Instrument                  tool window, active-run surface, collapsible
├─ Safety confirmation               owned dialog/top-level safety surface
│
├─ Settings                          normal resizable window
├─ Room Builder                      normal resizable window
├─ Run Log                           normal resizable window
└─ Approval Review                   normal Settings destination or owned details window
```

### 6.3 Lifecycle contract

| Event | Behavior |
|---|---|
| First installation launch | Open a normal onboarding window. Explain local execution, startup, notifications, hotkey, and privacy. Do not ask for blanket action approval. |
| Sign-in startup | Start Agent silently and add tray icon. No flyout, toast, or Home window. |
| Launch from Start/Search while Agent exists | Redirect activation and open the contextual picker on the chosen monitor. |
| Click X or Alt+F4 in Settings/Builder/Log | Close that window only. Agent and any active ritual continue. Both actions are identical. |
| Dismiss idle flyout | Close on outside click, Escape, invoking the hotkey again, or selecting an item. Return focus to the prior application. |
| Dismiss active instrument | Collapse to tray. Running continues. The tray icon and tooltip remain authoritative. |
| Close confirmation | Equivalent to the safe negative action, such as “Not now.” It never silently approves. |
| Exit Setpiece | If idle, remove tray icon and exit. If a ritual is active, present “Stop ritual and exit?” with the exact unfinished work and recovery consequence. |
| Explorer/taskbar restart | Re-register the notification icon and preserve the same active state and tooltip. No duplicate icon. |
| Sleep | Journal a suspend checkpoint. Do not count asleep time against ordinary network/app waits unless the step explicitly uses wall-clock time. |
| Resume | Revalidate prerequisites and targets before continuing. If the environment changed, enter Waiting or Confirmation rather than resuming blindly. |
| Monitor disconnected | Move transient surfaces into the nearest remaining work area; preserve logical size and focus. |
| Agent crash/restart | Rehydrate the journal, show “Interrupted ritual” in the tray, and offer Recovery. Never auto-repeat an unknown-completion side effect. |

### 6.4 Focus and z-order rules

- User-invoked tray or hotkey surfaces may take focus because the user explicitly requested them.
- Background state changes must not force a foreground window. They update the tray and, when warranted, send a notification with **Review** or **Open Setpiece**.
- The flyout and Quiet Instrument are tool windows omitted from taskbar and Alt+Tab. They must remain normally activatable; do not use a no-activate style for surfaces requiring keyboard or screen-reader interaction.
- The Quiet Instrument is not permanently topmost. It is placed above ordinary windows only while the user is interacting with it, then returns to normal z-order. A user may opt into “Keep visible during this ritual.”
- A confirmation opens immediately only when it directly follows user interaction inside Setpiece. If reached in the background, the run enters Confirmation, the tray changes state, and a notification invites review without stealing focus.
- Launching or foregrounding a target application is itself a stated ritual action. Setpiece must not repeatedly bring itself back above that target.

### 6.5 Dismissal rules

| Surface/state | Outside click | Escape | Hotkey again | Close button |
|---|---:|---:|---:|---:|
| Idle picker | Dismiss | Dismiss | Dismiss | Not shown |
| Ready/preflight | Dismiss to tray | Dismiss to tray | Dismiss to tray | Not shown |
| Running | Collapse, do not stop | Collapse | Toggle visibility | Collapse |
| Passive Waiting | Collapse, do not stop | Collapse | Toggle visibility | Collapse |
| Confirmation | No light-dismiss | Choose safe negative path | Bring to front | Safe negative path |
| Failure | Collapse; state persists | Collapse | Toggle visibility | Collapse |
| Recovery in progress | Collapse; recovery continues | Collapse | Toggle visibility | Collapse |
| Settings/Builder/Log | Normal window behavior | Close transient dialogs only | Open/toggle picker, not the window | Close window only |

### 6.6 Multi-monitor and taskbar placement

- A tray click anchors to the actual notification-icon rectangle when available; otherwise use the interaction point.
- The flyout opens inside that monitor’s work area and chooses the open direction with the most available room. Do not assume a bottom taskbar.
- Hotkey invocation defaults to the monitor containing the pointer. Settings may switch this to the monitor containing the focused window or the primary monitor.
- The active instrument remembers its last monitor per ritual. If that monitor disappears, it relocates to the nearest valid work area.
- Saved Room layouts are display-topology aware. A topology mismatch produces a preview and a choice: **Adapt layout**, **Choose displays**, or **Cancel**.

### 6.7 DPI and responsive contract

Setpiece must be Per-Monitor v2 aware and respond to a DPI change by recomputing window bounds, typography, icons, shadows, and hit targets. All product dimensions below are logical effective pixels (epx), not fixed physical pixels.

| Surface | Default logical size | Responsive behavior |
|---|---:|---|
| Tray flyout / picker | 400 × up to 520 epx | Minimum 336 epx. Above 440 epx, descriptions may appear; below 380 epx, secondary actions move into an overflow menu. |
| Quiet Instrument | 420 × content, max 70% work area | Current action remains fixed at top; step detail scrolls. It may expand to 560 epx for preflight or recovery details. |
| Confirmation | 440–520 epx wide | Single column at all supported scales; button order and safe default remain stable. |
| Settings | 880 × 640 epx default; 720 × 520 minimum | Navigation collapses to a top selector below 800 epx. No horizontal scrolling. |
| Room Builder | 1120 × 720 epx default; 820 × 600 minimum | Three regions above 1040 epx; inspector overlays or moves below the sequence at narrower widths. |

- Validate 96, 120, and 144 DPI as release gates, and smoke-test 192 DPI.
- Text may reflow but cannot clip, overlap, or reveal internal IDs.
- Primary pointer/touch targets are at least 40 × 40 epx. A 32 epx-high target is permitted only when at least 120 epx wide.
- No status meaning depends on a one-pixel line or tiny icon overlay.

---

## 7. Annotated information architecture

```text
Setpiece
├─ Tray layer
│  ├─ Contextual flyout
│  │  ├─ Current/last Room
│  │  ├─ Recent rituals
│  │  ├─ Search all rituals
│  │  └─ Active ritual summary, when applicable
│  └─ Shortcut menu
│     ├─ Open Setpiece
│     ├─ Active ritual…              [conditional submenu]
│     ├─ Rooms…
│     ├─ Recent rituals…
│     ├─ Run log
│     ├─ Settings
│     └─ Exit Setpiece
│
├─ Run layer — Quiet Instrument
│  ├─ Ready / preflight
│  ├─ Running
│  ├─ Waiting
│  ├─ Confirmation
│  ├─ Failure
│  └─ Recovery
│
├─ Configuration layer
│  ├─ Settings
│  │  ├─ General
│  │  ├─ Invocation
│  │  ├─ Appearance
│  │  ├─ Notifications
│  │  ├─ Approvals
│  │  ├─ Browser & media
│  │  ├─ Privacy & diagnostics
│  │  └─ About
│  └─ Room Builder
│     ├─ Room outline
│     ├─ Ritual sequence
│     ├─ Selected-step inspector
│     ├─ Preflight/Doctor
│     └─ Version and approval impact
│
└─ Evidence layer
   ├─ Run log
   ├─ Interrupted-run recovery
   └─ Approval history and revocation
```

### IA rules

1. There is no default Home dashboard.
2. Rooms are organizational containers, not decorated destinations.
3. Recent rituals are limited to the most recent five in the flyout and menu; the full library lives in the picker.
4. Run Log is chronology and evidence, not a social/activity feed.
5. Settings may use normal category navigation because it is a deliberate destination; the everyday run experience may not.
6. Builder authoring and runtime execution never coexist as overlapping windows. “Test preflight” opens an instrument preview owned by Builder.

---

## 8. Tray interaction contract

### 8.1 Input behavior

| Input | Idle | Active ritual |
|---|---|---|
| Left-click tray icon | Toggle Room/Ritual flyout | Toggle active Quiet Instrument |
| Right-click tray icon | Open stable shortcut menu | Open shortcut menu with Active ritual submenu |
| Double-click | Same result as one left-click; second click is ignored | Same result as one left-click; never starts/stops anything |
| `Win+Ctrl+R` | Open picker with search focused | Open instrument with current step focused |
| Escape | Dismiss picker and restore prior focus | Collapse instrument; does not pause or stop |
| Enter on selected ritual | Open Ready/preflight | Invoke the currently focused safe action only |

No ritual starts from a tray-icon double-click, notification click, or accidental repeated hotkey. Starting always requires a named ritual selection followed by Ready/preflight unless the user has explicitly created a low-risk instant Shortcut.

### 8.2 Tray icon states

| State | Icon treatment | Tooltip |
|---|---|---|
| Ready/idle | Monochrome Setpiece mark | `Setpiece — Ready` |
| Running | Stable activity notch/ring; no continuous animation required | `Diablo Night — Running step 3 of 6` |
| Waiting | Pause/notch variant | `Diablo Night — Waiting for Battle.net` |
| Confirmation | Solid attention center or small system-consistent marker | `Diablo Night — Needs your decision` |
| Failure | Exclamation variant | `Diablo Night — Stopped at Launch Diablo IV` |
| Recovery | Repair/checkpoint variant | `Diablo Night — Restoring previous state` |

The tooltip always contains the plain-language state so icon visibility, color perception, or a tiny overlay is not the only channel.

### 8.3 Proposed right-click menu

```text
Open Setpiece                         Win+Ctrl+R
────────────────────────────────────────────────
Active ritual…                         [only while active]
Rooms…                                 > top 5 + Manage Rooms
Recent rituals…                        > last 5
Run log
Settings
────────────────────────────────────────────────
Exit Setpiece
```

**Active ritual submenu**

```text
Show Diablo Night
Pause / Resume                         [only when supported]
Stop ritual…
Open current target                    [when meaningful]
View run details
```

Do not place Start with Windows, theme controls, diagnostics, or approval management in the tray menu. Those belong in Settings.

### 8.4 Compact flyout information architecture

```text
[ Search rituals…                                      ]

CURRENT ROOM
Gaming Room                                      Change

RECENT
Diablo Night                  Opens 3 apps          Enter
Focused Coding                5 steps               Enter
Evening Reset                 4 steps               Enter

[ Browse all rituals ]                    [ + New ritual ]
```

When a ritual is active, the top of this same surface becomes the compact instrument summary; recent content moves below a divider or disappears until the run is complete.

### 8.5 Auto-dismiss versus persistence

Auto-dismiss idle selection and informational flyouts on outside click. Do not auto-dismiss when:

- a consequential confirmation is open;
- the user is editing a value;
- the user invoked an accessibility help/description region;
- the user has pinned the active instrument for the current run;
- dismissing would conceal the only available path to recover from a failure.

Even when the visible instrument collapses, the active run remains represented by the tray icon, tooltip, and persistent local journal.

---

## 9. Interaction state machine

```text
Dormant/Idle
   │ invoke
   ▼
Picker
   │ choose ritual
   ▼
Preflight
   ├─ prerequisites fail ──> Blocked preflight ──> recheck / edit / cancel
   ├─ approval required ───> Confirmation ───────> Ready / cancel
   └─ all clear ───────────> Ready
                                │ Start
                                ▼
                              Running
                   ┌────────────┼──────────────┐
                   │            │              │
                   ▼            ▼              ▼
                Waiting    Confirmation      Failure
                   │            │              │
             condition met   approve/cancel    ├─ retry step
                   │            │              ├─ recover
                   └──────► Running ◄──────────┘
                                                │
                                                ▼
                                             Recovery
                                              │     │
                                            resume stop
                                              │     │
                                              ▼     ▼
                                           Running Stopped

Running ── complete ──> Completed ──> Idle
Running ── user stop ─> Stopping ───> Stopped ─> Idle
Agent interruption ───> Interrupted ─> Recovery review
```

### State contract

| State | User agency | Required visual treatment | Primary action |
|---|---|---|---|
| Ready | User chooses whether to begin | Ritual intent, affected apps/settings, duration/scope, prerequisites, and one clear start control | **Start ritual** |
| Running | System is acting; user may monitor or interrupt | Current step as a direct verb, progress position, next step, stable activity indicator | Usually none; **Pause** or **Stop** remains secondary |
| Waiting | System cannot proceed yet; user action may be unnecessary | Motion stops; reason, elapsed time, next check/timeout, and whether action is required are explicit | Contextual: **Check again**, **Continue without**, or none |
| Confirmation | User must decide before any further side effect | Consequence, exact target, why now, what is preserved, safe default, and decision boundary | Explicit verb such as **Launch Diablo IV** |
| Failure | The attempted path stopped | Failed step, cause, downstream steps not run, work already completed, and recommended remedy | **Retry step** or **Start recovery** |
| Recovery | Setpiece is actively repairing or restoring | Checkpoint, repair sequence, preserved work, and whether resuming is safe | Usually none during repair; then **Resume ritual** or **Leave restored** |

### State-copy rules

- Use present-tense verbs: “Opening Battle.net,” not “Executing action `open_app_03`.”
- Separate cause from consequence: “Battle.net shows Install. The launch step did not run.”
- Never label downstream steps “Failed” when they were not attempted; use “Not run.”
- A spinner means active work only. Passive waiting uses a still icon and a clock/countdown.
- Confirmation text always names the object and effect. Avoid “Continue?”, “Click target,” “Execute,” “Proceed,” and raw component IDs.


---

## 10. Visual system

### 10.1 Philosophy

The interface is a lightly warm instrument panel, not a pane of glass and not a collection of cards. Visual depth is shallow. Hierarchy comes from type scale, spacing, rules, and a single local surface. The wallpaper remains visible around it and is never treated as an image to be replaced or themed by Setpiece.

### 10.2 Typography

**Primary family:** Segoe UI Variable, falling back to Segoe UI and the Windows UI sans stack.
**Monospace:** Cascadia Mono only for paths, timestamps, hashes, target identities, and raw diagnostics.

| Token | Size / line height | Weight | Use |
|---|---:|---:|---|
| Display | 28 / 34 epx | 600 | Ritual name in Ready and major Builder titles |
| Title | 20 / 26 epx | 600 | Surface headings, current failure title |
| Subtitle | 16 / 22 epx | 600 | Current step, section title |
| Body | 14 / 20 epx | 400 | Instructions, consequences, descriptions |
| Label | 12 / 16 epx | 600 | Small section labels and compact metadata |
| Meta | 12 / 16 epx | 400 | Time, step count, optional detail |
| Code | 12 / 18 epx | 400 | Paths, hashes, diagnostic values |

Rules:

- Sentence case everywhere.
- Left alignment except isolated icon captions.
- No all-caps status badges.
- No type below 12 epx in shipping UI.
- The ritual name may truncate once; operational instructions wrap rather than truncate.

### 10.3 Color tokens

These are light-theme baseline values. High Contrast mode replaces them with system colors rather than derived brand values.

| Token | Value | Purpose |
|---|---|---|
| `surface.canvas` | `#F4F2EE` | Long-lived window base |
| `surface.panel` | `#FBFAF8` | Flyout/instrument matte |
| `surface.raised` | `#FFFFFF` | Focused input or confirmation section, used sparingly |
| `text.primary` | `#202327` | Main copy |
| `text.secondary` | `#5D646C` | Supporting copy |
| `text.tertiary` | `#737A82` | Optional metadata |
| `border.subtle` | `#DCD9D3` | Dividers and field outlines |
| `border.strong` | `#B9B5AE` | Focus-independent structural edge |
| `accent.default` | Windows accent, contrast-adjusted | Selection and primary action |
| `state.running` | `#386B87` | Supporting semantic accent only |
| `state.waiting` | `#866321` | Supporting semantic accent only |
| `state.confirmation` | `#62508A` | Supporting semantic accent only |
| `state.failure` | `#A13D35` | Supporting semantic accent only |
| `state.recovery` | `#426F60` | Supporting semantic accent only |

Status color is never the only signal. Every state also changes icon, wording, structure, and available action.

### 10.4 Spacing, geometry, and elevation

- Base spacing unit: 4 epx.
- Primary rhythm: 8, 12, 16, 24, and 32 epx.
- Flyout outer padding: 16 epx.
- Instrument section gap: 16 epx; major-state boundary: 24 epx.
- Flyout and instrument corner radius: 10 epx.
- Inputs and buttons: 6 epx radius; compact metadata is not automatically pill-shaped.
- Dividers are preferred to nested containers.
- One shallow shadow around transient surfaces; no shadows between internal sections.
- A focused element uses the Windows focus visual plus a geometry change where appropriate.

### 10.5 Material treatment

- **Tray flyout and Quiet Instrument:** default to a 94–98% opaque local matte. Desktop Acrylic may be offered only if text and controls remain legible over both light and detailed wallpapers. There is always an opaque accessibility fallback.
- **Settings and Room Builder:** Mica or a solid warm neutral backdrop. Content panes remain opaque enough for sustained reading.
- **Confirmation:** opaque. Consequential text must never depend on wallpaper contrast or blur.
- **No full-desktop dimming** except when Windows itself presents a secure UAC prompt.

### 10.6 Motion

| Motion token | Duration | Use |
|---|---:|---|
| Instant | 0–80 ms | Selection, state-icon swap, progress value update |
| Fast | 120–160 ms | Flyout show/hide, hover, inline disclosure |
| Standard | 180–220 ms | State transition, instrument expansion |
| Deliberate | 240–300 ms | Recovery sequence reorganization or spatial preflight preview |

- No bounce, elastic easing, confetti, glow pulses, or perpetual ambient animation.
- Running progress may move only while work is occurring.
- Waiting removes directional motion.
- Confirmation inserts a visible boundary; it does not shake or flash.
- Reduced Motion substitutes fades or immediate changes and preserves all information.

### 10.7 Component behavior

| Component | Binding behavior |
|---|---|
| Primary action | Exactly one per state. Full verb plus object when consequence matters. |
| Secondary action | Plain button or link; never styled to compete with the primary. |
| Destructive action | Explicit verb, separated spatially, never the default focus. |
| Status indicator | Icon + plain-language label + optional time. No badge-only communication. |
| Step list | Current step expanded; completed and future steps condensed. Detailed logs hidden by default. |
| Progress | Determinate only when the denominator is meaningful. Otherwise show current step and elapsed time, not a fake percentage. |
| Overflow menu | Contains low-frequency actions only. It must not hide the sole safe exit or recovery action. |
| Tooltip | Supplemental. No required information or action exists only in a tooltip. |
| Error detail | Human explanation first; technical detail in an expandable section with Copy diagnostics. |
| Empty state | One sentence describing what belongs here and one appropriate next action. No illustration required. |

### 10.8 Wallpaper coexistence tests

Each transient surface must be reviewed over:

1. a bright low-detail wallpaper;
2. a dark low-detail wallpaper;
3. a high-frequency photograph;
4. a high-contrast illustration;
5. a motion wallpaper frame with both light and dark regions.

Acceptance requires readable text, visible focus, distinct boundaries, and no need for a full-screen scrim. Relocation to another taskbar-adjacent corner must remain possible when the local wallpaper defeats the preferred treatment.

---

## 11. Permission and confirmation model

### 11.1 Trust principles

1. **Consent is layered.** First-run consent explains the product; it does not authorize every future side effect.
2. **Imported content is data until trusted.** It can be read, inspected, and edited without execution.
3. **Remembered approval is exact, not broad.** It binds to the current Windows user, device, recipe content, action, target, arguments, risk class, and source identity.
4. **Elevation is separate.** Setpiece may explain why elevation is needed, but Windows owns the credential/consent prompt.
5. **Changed intent means changed approval.** A semantic change to the recipe or target invalidates approval before execution.
6. **High-risk effects always ask.** Repetition does not make an irreversible or externally consequential action safe.

### 11.2 Risk tiers

| Tier | Examples | Enable-time behavior | Runtime behavior | Rememberable? |
|---|---|---|---|---:|
| R0 — Read/check | Check process state, verify file exists, read window title, run Doctor | No approval beyond product consent | No prompt | N/A |
| R1 — Reversible local | Open app, open URL, arrange windows, change non-sensitive local app setting | Review in ritual summary | No prompt after enabled unless target changes | Yes, implicit in enabled local ritual |
| R2 — Consequential scoped | Close named windows, interact with a named app control, terminate a non-critical process, overwrite a bounded generated file | Explicit review and optional exact remembered approval | Ask unless a valid exact approval exists | Yes, with expiry/revocation |
| R3 — High risk | Elevation, install/uninstall, delete user files, change security/account settings, send/post/purchase, close unsaved work, broad process/file operations | Cannot be blanket-approved | Always ask immediately before effect; UAC follows if needed | No |

### 11.3 Permission matrix

| Moment | What is asked | What is not asked |
|---|---|---|
| First run | Start at sign-in, notification permission/expectation, hotkey, local storage, optional diagnostics, plain privacy statement | Approval to run all rituals, admin rights, access to all apps, or any recording capability |
| Local Learning consent | Only capabilities actually present in the product; local processing and retained data explained | Watch Me, screenshots, OCR, keylogging, macro recording, or silent observation |
| Enable local ritual | Human-readable action summary, exact apps/targets, risk tier, recovery behavior, and whether approvals can be remembered | Raw internal IDs as the primary explanation |
| Review imported ritual | Source, signature if available, exact diffable recipe, targets, risk summary, and Restricted status | Automatic execution on open or trust inherited from a folder name |
| Runtime one-time approval | Exact effect, object, reason, and preserved state | Vague “Continue?” or “Click target?” prompts |
| Remember approval | Exact scope and expiration, with a direct Review link | “Always allow” without scope |
| Recipe/target change | Show what changed and which approval was invalidated | Silent migration of prior approvals |
| High-risk action | Ask every time; defer elevation to Windows when required | Permanent approval or approval from a toast action |

### 11.4 Remembered-approval record

A valid record includes:

```text
Windows user SID
local device key / installation identity
ritual ID and canonical content hash
source identity and signature state
exact action type and normalized arguments
canonical target identity
  - package family / app user model ID where available
  - canonical executable path
  - publisher/signature identity
  - UI Automation identity when targeting a control
risk tier
approval timestamp and expiry
Setpiece policy/schema version
revocation state
```

Approval is checked atomically immediately before the side effect, not only at preflight.

### 11.5 Invalidation rules

Invalidate when any of these occurs:

- recipe content hash changes;
- target executable path, package identity, publisher, or UI Automation identity changes;
- arguments or file scope broaden;
- risk tier rises;
- an imported pack is updated or its source/signature changes;
- the Windows user or local device identity changes;
- the approval expires or the user revokes it;
- the policy schema changes in a way that affects risk evaluation;
- the target disappears and a different executable is found under the same display name.

A harmless presentation-only edit, such as a ritual description or icon, may preserve approval only if it is excluded from the canonical executable-content hash and the UI clearly labels the edit as non-executable.

### 11.6 Recommended confirmation copy

**Diablo IV approval**

> **Start Diablo IV?**
> Setpiece is ready to ask Battle.net to launch Diablo IV. Battle.net will come to the foreground and Setpiece will select **Play**. No keyboard or mouse input will be recorded.
>
> `[ Launch Diablo IV ]`  `[ Not now ]`
>
> `□ Remember this exact launch step on this PC for 30 days`

Show the remember option only if the action is classified R2 and the ritual is local/trusted. Do not show it for the first run of an imported pack.

**Blocked / not ready**

> **Battle.net needs your attention**
> Diablo IV is not ready to launch because Battle.net currently shows **Install**. Finish installation in Battle.net, then return here.
>
> `[ Open Battle.net ]`  `[ Check again ]`  `Stop ritual`

**Changed recipe**

> **This ritual changed since you approved it**
> The Diablo IV launch target changed from `Battle.net.exe` by Blizzard Entertainment to an unverified executable. The previous approval no longer applies.
>
> `[ Review changes ]`  `[ Stop ritual ]`

### 11.7 Approval settings

**Settings → Approvals** contains:

- Search by ritual, app, target, or action.
- Columns: Ritual, approved action, exact target, source, risk, approved date, expires, status.
- Row action: **Review details**, **Revoke**, and **Open ritual**.
- Bulk action is limited to **Revoke selected**. There is no bulk approve.
- A top summary distinguishes Valid, Expiring soon, Invalidated, and Revoked.
- “Clear all approvals” requires confirmation and explains that rituals may ask again; it has no effect on run history.

### 11.8 Adversarial abuse analysis

| Abuse case | Required mitigation |
|---|---|
| Recipe swap after approval | Canonical content hash and atomic recheck before execution |
| Display-name spoofing | Canonical path/package identity plus publisher/signature, not visible name alone |
| Target replacement at same path | Revalidate file identity/signature/hash as appropriate immediately before action |
| Broad wildcard introduced | Treat scope expansion as a risk increase and invalidate approval |
| Imported pack impersonates a trusted pack | Track source/signature independently from title and artwork; default to Restricted |
| Child process performs broader action | Worker receives a narrow capability request; no ambient elevation or broad token |
| Time-of-check/time-of-use race | Resolve and validate target at execution boundary; journal exact resolved identity |
| Approval copied to another user/device | Bind to user SID and local device key |
| Deceptive confirmation text | Generate consequence copy from normalized action data, not pack-authored prose alone |
| Stale long-lived approval | Expiration, settings review, and invalidation on policy/target change |
| Log tampering or secret leakage | Append-only integrity checks; redact secrets and sensitive values from ordinary logs |
| Notification-action approval | Notifications may open review but cannot approve R2/R3 effects directly |

---

## 12. Browser and media behavior

### Default: native browser handoff

- Open the ambience URL in the user’s normal signed-in browser context.
- Mark ambience as optional unless the ritual explicitly says otherwise.
- Do not minimize the browser automatically.
- Do not claim playback was detected or verified.
- If the browser launch succeeds, continue according to the ritual’s declared dependency model.

### Optional: Managed browser session

The user must explicitly select **Managed browser session** in the ritual or Settings. The UI explains that it uses a separate Setpiece-controlled browser profile and may not share the user’s sign-in state.

Before claiming playback and before minimizing, verify:

```text
media element exists
readyState is sufficient
paused == false
ended == false
currentTime advances over a short interval
```

This proves only that the selected media element is progressing. It does not generically prove that a provider is playing the intended content rather than an interstitial. Provider-specific ad skipping or circumvention is not part of Setpiece.

### Settings placement

**Settings → Browser & media**

- Default browser behavior: Normal browser / Managed browser when explicitly requested.
- Managed profile location and Clear managed data.
- “Allow minimizing after verified playback” off by default.
- Plain warning that normal-browser playback cannot be deterministically inspected in the current architecture.


---

## 13. Seven approved low-fidelity wireframes

These are prototype-level interaction wireframes, not high-fidelity screens. They define hierarchy, state, and behavior while leaving visual styling for the selected-direction design phase.

### Wireframe 1 — Contextual tray flyout / picker

```text
╭──────────────────────────────────────────────╮
│  Search rituals…                         ⌕   │  A
├──────────────────────────────────────────────┤
│  GAMING ROOM                                 │
│  Diablo Night                                │
│  Open ambience, prepare Battle.net,          │
│  then launch Diablo IV                    ›  │  B
│                                              │
│  Focused Coding                           ›  │
│  Evening Reset                            ›  │
├──────────────────────────────────────────────┤
│  Browse all rituals          + New ritual    │  C
╰──────────────────────────────────────────────╯
```

**Annotations**

- **A:** Search receives focus for hotkey invocation; tray-click invocation preserves a selected recent item for immediate keyboard use.
- **B:** One row includes intent, not implementation. Enter opens preflight; it does not execute immediately.
- **C:** Builder is reachable but visually secondary. No permanent sidebar, metrics, status-card grid, or feed.
- Outside click and Escape dismiss. Focus returns to the previously active application.

### Wireframe 2 — Ready and live preflight

```text
╭──────────────────────────────────────────────────╮
│  Diablo Night                              Ready  │
│  Prepare a calm gaming setup, then launch         │
│  Diablo IV.                                       │
│                                                   │
│  ✓ Battle.net found                               │
│  ✓ Diablo IV installed                            │
│  ! Ambience will open in your normal browser      │
│    Playback will not be verified.          Details│
│                                                   │
│  Will open 2 apps · arrange 2 windows · ~20 sec   │
│                                                   │
│  [ Start ritual ]                    Cancel       │
╰──────────────────────────────────────────────────╯
```

**Annotations**

- The title, intent, and consequence precede technical detail.
- Preflight uses plain rows, not independent cards.
- Only one dominant action.
- A layout-affecting ritual may add **Preview layout** as a secondary action, using the Spatial Field grammar.
- If blocked, the primary action becomes the remedial action, not a disabled Start button with no explanation.

### Wireframe 3 — Running and passive Waiting

**Running**

```text
╭──────────────────────────────────────────────╮
│  Diablo Night                   Step 3 of 6   │
│                                              │
│  Opening Battle.net                          │
│  ━━━━━━━━━━━━━━━╺━━━━━━━━━━━━━━━━━━━━━━━━    │
│  Next: Check Diablo IV status                │
│                                              │
│  00:08 elapsed                               │
│                           Pause   Stop…       │
╰──────────────────────────────────────────────╯
```

**Waiting**

```text
╭──────────────────────────────────────────────╮
│  Diablo Night                        Waiting │
│                                              │
│  Waiting for Battle.net to finish signing in│
│  No action is required. Checking again in 8s │
│                                              │
│  00:34 elapsed · timeout in 01:26            │
│                         Check now   Stop…     │
╰──────────────────────────────────────────────╯
```

**Annotations**

- The same shell changes state structurally; no overlapping runtime panels.
- Running has restrained directional progress. Waiting removes motion and explicitly states whether the user must act.
- Pause appears only when the current action can safely pause. Stop always opens a consequence summary if cleanup is needed.

### Wireframe 4 — Confirmation

```text
╭──────────────────────────────────────────────────╮
│  Start Diablo IV?                                │
│                                                  │
│  Setpiece is ready to ask Battle.net to launch  │
│  Diablo IV. Battle.net will come to the foreground│
│  and Setpiece will select Play.                 │
│                                                  │
│  No keyboard or mouse input will be recorded.    │
│                                                  │
│  □ Remember this exact launch step on this PC    │
│    for 30 days                                   │
│                                                  │
│  [ Launch Diablo IV ]              [ Not now ]   │
│                                                  │
│  Why am I seeing this?                           │
╰──────────────────────────────────────────────────╯
```

**Annotations**

- Consequence, target, method, and privacy statement are explicit.
- Safe negative action closes the dialog and leaves the ritual in a comprehensible stopped/paused state.
- A high-risk action omits the remember option.
- Technical target identity is available under **Why am I seeing this?**, not in the headline.

### Wireframe 5 — Failure and interrupted Recovery

**Failure**

```text
╭──────────────────────────────────────────────────╮
│  Diablo Night                         Stopped     │
│                                                  │
│  Diablo IV could not be launched                 │
│  Battle.net currently shows Install instead of   │
│  Play.                                           │
│                                                  │
│  Completed: ambience opened, windows arranged    │
│  Not run: launch game, minimize ambience         │
│                                                  │
│  [ Open Battle.net ]   [ Check again ]           │
│  Restore previous layout                     ›   │
│  Technical details                           ›   │
╰──────────────────────────────────────────────────╯
```

**Recovery**

```text
╭──────────────────────────────────────────────────╮
│  Restoring your previous layout                  │
│                                                  │
│  ✓ Returned Battle.net to its prior position     │
│  ● Restoring browser window                      │
│  ○ Releasing temporary keep-awake request        │
│                                                  │
│  2 of 3 · 00:05                                  │
│                                                  │
│  Recovery can continue while this is hidden.     │
╰──────────────────────────────────────────────────╯
```

**Annotations**

- Failure distinguishes cause, completed work, and steps not run.
- The recommended remedy is specific; retry is not the only answer.
- Recovery is an active state, not a success-colored failure card.
- On completion, offer **Resume ritual** and **Leave restored**.

### Wireframe 6 — Settings window

```text
┌──────────────────────────────────────────────────────────────────┐
│ Setpiece Settings                                        — □ × │
├──────────────────────┬───────────────────────────────────────────┤
│ General              │ General                                   │
│ Invocation           │                                           │
│ Appearance           │ Start Setpiece when I sign in       [on] │
│ Notifications        │ Close windows without exiting        [on] │
│ Approvals            │                                           │
│ Browser & media      │ Default invocation                        │
│ Privacy & diagnostics│  Tray click: Open contextual flyout       │
│ About                │  Shortcut: Win+Ctrl+R        [ Change… ]   │
│                      │                                           │
│                      │ Active ritual behavior                    │
│                      │  Show instrument on: Cursor monitor  [v]  │
│                      │                                           │
│                      │                         [ Exit Setpiece ] │
└──────────────────────┴───────────────────────────────────────────┘
```

**Annotations**

- Settings is allowed a conventional navigation structure because it is a deliberate, long-lived destination.
- The window uses Mica or a solid warm backdrop; content remains opaque.
- Categories are stable and searchable. No dashboard Home with tiles.
- **Exit Setpiece** is explicit and separated from ordinary settings.
- Below 800 epx, the category rail becomes a top category selector.

### Wireframe 7 — Room Builder

```text
┌──────────────────────────────────────────────────────────────────────────┐
│ Gaming Room / Diablo Night                                      — □ ×  │
├───────────────────┬────────────────────────────────┬─────────────────────┤
│ ROOM OUTLINE      │ RITUAL SEQUENCE                │ SELECTED STEP       │
│                   │                                │                     │
│ Diablo Night      │ 1  Open ambience          ✓    │ Open Battle.net     │
│ Focused Practice  │ 2  Arrange windows        ✓    │                     │
│ Update Games      │ 3  Open Battle.net        ●    │ Application         │
│                   │ 4  Check Diablo status     ○    │ Battle.net          │
│ + Add ritual      │ 5  Confirm launch          ○    │                     │
│                   │ 6  Launch Diablo IV        ○    │ On failure          │
│                   │                                │ Wait and explain [v]│
│                   │ + Add step                     │                     │
├───────────────────┴────────────────────────────────┴─────────────────────┤
│ Doctor: 5 ready · 1 warning          [ Preview preflight ] [ Save ]      │
│ Saving changes will invalidate 1 remembered approval.  Review change ›  │
└──────────────────────────────────────────────────────────────────────────┘
```

**Annotations**

- Builder is a normal window with one outline, one sequence, and one contextual inspector—not a freeform card canvas.
- The inspector appears only for the selected step. At narrow widths, it moves below the sequence or opens as an owned panel.
- Save communicates approval impact before committing executable changes.
- Doctor and preflight preview are first-class; raw IDs remain in an optional technical details section.

---

## 14. Notification model

| Event | Tray | Notification | Visible surface |
|---|---|---|---|
| Agent starts | Ready icon | None | None |
| Ritual starts from visible UI | Running icon | None | Instrument remains available |
| Short step completes | Update tooltip/state | None | Inline update only |
| Passive wait begins | Waiting icon | Usually none | Instrument explains reason if open |
| User decision needed in background | Confirmation icon | “Diablo Night needs your decision” + **Review** | Confirmation opens only after user action |
| Failure in background | Failure icon | Specific failure + **Open Setpiece** | Failure surface persists in Agent state |
| Recovery starts | Recovery icon | None unless triggered after crash/restart | Recovery surface on demand |
| Long/background ritual completes | Ready icon | Optional quiet completion notification | No forced window |
| Short visible ritual completes | Ready icon | None | Quiet completion then auto-collapse after a brief readable interval |

Notification rules:

- Never use notification audio for ordinary progress or success.
- Respect Windows notification settings and Focus Assist/Do Not Disturb behavior.
- No critical recovery information exists only in a notification, because the tray icon may be in overflow and notifications may be suppressed.
- Selecting a notification opens the exact ritual and state that produced it.
- Clear or replace stale notifications when the state has resolved.
- Notification buttons perform only safe actions such as **Review**, **Open app**, or a pre-authorized idempotent **Check again**. They do not grant consequential approval.

---

## 15. Human usability study

### 15.1 Study design

**Round A — Moderated formative study**

- 15 participants, three from each target profile:
  - ordinary Windows user;
  - PC gamer;
  - developer/power user;
  - IT/helpdesk operator;
  - keyboard-first or assistive-technology user.
- At least two participants should routinely use a screen reader, and all keyboard-profile participants should complete the session without a pointer.
- 60 minutes per session using an interactive prototype and a controlled Windows desktop environment at mixed 100%, 125%, and 150% scaling.
- Think aloud for discovery and interpretation tasks. For the two-second state-recognition probes, ask for an immediate answer before think-aloud discussion so prompting does not distort the measure.

**Round B — Unmoderated validation**

- 30 participants, balanced as closely as practical across the same profiles.
- Instrumented prototype records task completion, elapsed time, backtracks, incorrect commands, flyout dismissal, and state-choice errors.
- Follow-up comprehension questions verify what participants believe Setpiece did; telemetry alone is insufficient.

### 15.2 Moderated script

**Introduction**

> We are testing Setpiece, not you. Some parts may be incomplete. Please say what you expect to happen before you act. During a few short questions, I will ask for your immediate interpretation before we discuss it.

**Tasks**

1. Find and open Gaming Room.
2. Explain what Diablo Night will do before starting it.
3. Change the ambience URL and choose the normal browser.
4. Run Doctor and explain the warning it finds.
5. Interpret a Battle.net state that says Diablo IV must be installed.
6. Approve a ready Play action and describe what the approval covers.
7. Interpret a failed launch and identify what did and did not run.
8. Pause and then stop a ritual; predict the cleanup consequence before confirming.
9. Find the run log and locate the failed step.
10. Open Settings and revoke the Diablo IV remembered approval.
11. Edit Gaming Room and understand that the changed executable step invalidates approval.
12. Exit Setpiece completely rather than merely closing a window.

**State-recognition probes**

For Ready, Running, Waiting, Confirmation, Failure, and Recovery, show the state for two seconds and ask:

1. What is happening now?
2. Does Setpiece need you to do anything?
3. What would you do next?

### 15.3 Unmoderated variant

- Provide a fresh Windows test profile and a scenario narrative rather than moderator instructions.
- Randomize two non-critical task orders to detect sequence learning.
- Use a forced-choice comprehension question after every consequential state.
- Include one deliberate interruption/relaunch so Recovery can be tested.
- Include one shortcut conflict and one 150%-scaling condition.
- End with a free-response explanation: “Describe what Setpiece changed on the computer during this session.”

### 15.4 Success metrics

| Metric | Acceptance threshold |
|---|---:|
| Find Gaming Room | 90% within 15 seconds; median ≤ 8 seconds |
| Correctly explain Diablo Night before running | 85% name all major effects; 100% identify game launch as consequential |
| Identify next action in operational states | 90% of all probes within 2 seconds; no state below 80% |
| Distinguish Waiting from Confirmation | At least 90%; zero participants approve while believing no action was required |
| Interpret blocked Install state | 90% choose Open Battle.net or Check again; <5% repeatedly press Start |
| Understand failure scope | 90% correctly distinguish Failed from Not run |
| Pause/stop without feeling trapped | 90% complete; median perceived control ≥4/5 |
| Find run log | 85% within 30 seconds |
| Revoke approval | 90% within 45 seconds; no accidental bulk revocation |
| Edit Room and notice approval invalidation | 85% without moderator intervention |
| Exit completely | 100% locate explicit Exit and correctly predict the result |
| Keyboard-only critical paths | 100% completion with no keyboard trap or pointer requirement |
| Narrator critical paths | All controls expose correct name, role, state, and value; state changes are announced without excessive chatter |
| Utility versus dashboard perception | At least 80% choose “utility” or equivalent over “dashboard” |
| Perceived interruption | Median ≤2 on a 1–5 interruption scale |
| Trust in confirmations | Median ≥4 on a 1–5 trust/clarity scale |

### 15.5 Observation sheet

Record for each task:

| Field | Values |
|---|---|
| Outcome | Success / partial / failure |
| Time | Seconds to first correct action and total completion |
| Incorrect action | Command, click, or key used and participant expectation |
| State interpretation | Verbatim immediate answer |
| Assistance | None / neutral prompt / directed help |
| Trust signal | Hesitation, rereading, avoidance, overconfidence |
| Focus behavior | Window stealing, lost focus, off-screen surface, unexpected Alt+Tab/taskbar presence |
| Accessibility | Focus order, announcement, control name/role/state, contrast/scaling issue |
| Quote | Verbatim participant language |
| Severity | 0–4 |

**Severity scale**

- 0 — Not a usability problem.
- 1 — Cosmetic; no material effect on task or trust.
- 2 — Minor; causes hesitation or recoverable inefficiency.
- 3 — Major; causes failure, serious misunderstanding, or repeated interruption.
- 4 — Release-blocking; creates unsafe action, data risk, inaccessible critical path, or a trapped user.

### 15.6 Post-test questions

1. What did Setpiece feel like: a utility, launcher, dashboard, automation tool, or something else?
2. At any point did you feel Setpiece took over the desktop?
3. Which state was hardest to understand?
4. Did any confirmation feel repetitive, vague, or too permissive?
5. What do you believe “Remember this approval” covered?
6. Did closing a window behave as expected?
7. Did you ever feel unable to stop, recover, or exit?
8. What information was missing before you trusted a ritual?
9. Which technical detail was unnecessary or arrived too early?
10. On a 1–5 scale, how confident are you that you can explain what Setpiece changed?

### 15.7 Release-blocking UX criteria

Do not ship when any of the following remains:

- A user can approve or trigger an R3 action without explicit current intent.
- Any participant mistakes a passive Waiting state for a required approval in a way that causes unsafe action.
- A critical path is impossible with keyboard or Narrator.
- Focus is stolen from a full-screen app by a background event.
- A flyout or confirmation is clipped/off-screen at 100%, 125%, or 150% scaling.
- X and Alt+F4 produce different lifecycle outcomes for the same window.
- Users cannot distinguish closing a surface, stopping a ritual, and exiting Setpiece.
- Failure obscures which actions completed and which were not run.
- Interrupted recovery can repeat an unknown-completion side effect automatically.
- Internal IDs, raw exceptions, or technical “Click target” language appear in the primary UI.
- More than 10% of validation participants describe the everyday experience as a dashboard or feel trapped by it.
- Any unresolved severity-4 issue or more than two unresolved severity-3 issues affect a critical task.

---

## 16. Implementation and migration phases

### Phase 1 — State and shell foundation

- Define the binding state machine and append-only run journal.
- Introduce the single-instanced Agent and activation redirection.
- Add the notification-area icon, tooltip states, stable right-click menu, and silent sign-in startup.
- Implement Explorer/taskbar restart recovery and Per-Monitor v2 awareness.
- Keep the current Home available only as a temporary compatibility window.

**Exit criterion:** Setpiece can remain resident, open one picker, survive Explorer restart, and show accurate idle/running/attention tray states without spawning Canvas windows.

### Phase 2 — Quiet Instrument

- Build the contextual picker, Ready/preflight, Running, Waiting, Confirmation, Failure, and Recovery surfaces.
- Route existing runtime events into the state model.
- Replace overlapping runtime panels with inline expansion.
- Add notification routing and focus-safe background attention behavior.

**Exit criterion:** All six states are understandable, keyboard operable, and represented by one owned instrument.

### Phase 3 — Safety and recovery

- Introduce risk classification, imported Restricted mode, exact approval records, invalidation, and Settings review/revoke.
- Isolate action workers and the on-demand elevated helper.
- Add checkpoint recovery and unknown-completion safeguards.
- Replace technical confirmation copy with normalized consequence copy.

**Exit criterion:** No changed recipe or target can reuse stale approval; interrupted runs enter a safe recovery review.

### Phase 4 — Settings and Room Builder

- Replace Home’s configuration responsibilities with normal Settings and Builder windows.
- Implement Room outline, sequence editor, contextual inspector, Doctor, preflight preview, and approval-impact warnings.
- Add Browser & media settings with explicit normal versus managed behavior.

**Exit criterion:** All legitimate Home/Canvas tasks have a destination in the new architecture and no authoring task requires spawned overlapping windows.

### Phase 5 — Remove default Home and harden fundamentals

- Stop launching Home by default and remove automatic Canvas spawning.
- Preserve a developer-only diagnostics window behind an explicit debug flag.
- Validate 96/120/144 DPI, monitor changes, taskbar auto-hide/location, sleep/resume, shell restart, full-screen applications, High Contrast, Reduced Motion, Narrator, and keyboard-only operation.

**Exit criterion:** The product starts invisibly, passes accessibility and scaling gates, and has no ordinary dashboard path.

### Phase 6 — Human validation and limited optional features

- Run the moderated and unmoderated studies.
- Resolve all release-blocking issues.
- Only after the core model passes, evaluate optional Spatial Field layout preview, managed-browser playback verification, and an optional Desktop Work-Area Room layer.

### Migration map from current Home + Canvas

| Current responsibility | New destination |
|---|---|
| Home launch/selection | Tray flyout and full picker |
| Home settings/status cards | Settings categories or tray tooltip, depending on purpose |
| Canvas runtime panels | Single Quiet Instrument |
| Canvas step details | Inline disclosure / Run Log |
| Room editing | Room Builder normal window |
| Technical diagnostics | Doctor and expandable technical details |
| Confirmation panel | Owned confirmation with normalized consequence copy |
| Failure panels | Failure state plus explicit Recovery |
| Internal IDs | Hidden from ordinary UI; available only in Copy diagnostics |

A compatibility adapter may translate old Canvas events into the new state model during migration, but it must not preserve the old window architecture.

---

## 17. Anti-style guide

| Prohibition | Binding rule |
|---|---|
| No generic SaaS dashboard | No default sidebar + header + metric tiles + activity feed composition. |
| No wall of white cards | Group with typography, spacing, dividers, and inline disclosure before adding a container. |
| No excessive pills | Pills are limited to compact atomic metadata or filters; buttons, tabs, states, and steps are not pills by default. |
| No arbitrary gradients | A gradient may represent a real material transition or state progression only; it cannot exist merely to imply premium polish. |
| No fake glass everywhere | Transparency is limited to small transient surfaces, and every such surface has an opaque fallback. |
| No gamer-neon default | No RGB glow, cyan-magenta pairing, luminous borders, pulsing chroma, or sci-fi HUD language. |
| No decorative widgets without ritual purpose | Every persistent element must answer what is active, what happens next, what is blocking, or what the user can safely do. |
| No color-only state | State also changes icon, text, geometry, behavior, and available action. |
| No leaked implementation language | No component IDs, raw selectors, internal action names, or stack traces in primary UI. |
| No mystical cosplay | “Ritual” does not authorize runes, incantations, occult ornament, smoke, ceremony, or anthropomorphic system claims. |
| No permanent run sidebar | Everyday execution is one compact instrument, not a multi-pane cockpit. |
| No unnecessary badges | A status label exists only when the state is not already clear from the sentence and structure. |

---

## 18. Explicit non-goals

The first release will not:

- replace the Windows shell, Start menu, taskbar, Explorer, virtual desktops, or wallpaper system;
- render or manage live wallpaper;
- record the screen, take screenshots for automation, run OCR, keylog, record macros, or capture user input;
- provide a permanent Home dashboard, widget board, social feed, achievement system, or game-store catalog;
- run multiple attended rituals concurrently for the same Windows user;
- silently elevate the resident process or retain broad administrator capability;
- approve imported rituals merely because their source folder or display name appears familiar;
- perform high-risk approval from a toast, tray double-click, or background event;
- steal focus from unrelated foreground or full-screen applications;
- claim verified playback in a normal browser session;
- implement provider-specific advertisement detection, skipping, or circumvention;
- minimize a normal browser merely because a URL was opened;
- ship a browser extension or OS media-session bridge in the first release;
- use an always-on-top desktop overlay as the primary runtime model;
- build a plugin marketplace, cloud account system, or cross-device synchronization before the local trust and recovery model is validated;
- expose arbitrary theme/skin authoring that can break hierarchy, accessibility, or state recognition.

---

## 19. Acceptance summary

The next Setpiece prototype is approved to proceed only as a **tray-first Quiet Instrument** with:

- one resident Agent;
- no default Home window;
- a contextual tray flyout and global hotkey;
- one compact active-run instrument;
- distinct Ready, Running, Waiting, Confirmation, Failure, and Recovery structures;
- normal Settings and Room Builder windows;
- exact, revocable, content-addressed approvals;
- imported Restricted mode;
- focus-safe notifications;
- Per-Monitor v2 scaling and full keyboard/Narrator operation;
- an opaque light visual system that lets wallpaper remain dominant;
- no high-fidelity design work until this architecture and direction are accepted.
