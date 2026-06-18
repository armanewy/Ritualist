# Ritualist UI/UX Convergence

This document binds the post-north-star UI direction. It is a product design
contract, not a new capability plan.

## Design Character

Ritualist uses one design system with three expressions:

- Quiet Instrument: the default invocation and active-run surface.
- Spatial Field: a preflight or recovery visualization when desktop geometry
  matters.
- Editorial Ledger: an expanded evidence, log, failure, and recovery surface.

These are compositions, not separate themes. They share typography, controls,
state words, accessibility behavior, and safety language.

## Hierarchy

Every Room surface must prioritize:

1. Ritual identity and intent.
2. Current state or active step.
3. Next safe action.
4. Details, history, logs, and settings.

State changes must alter structure and available agency, not only color. For
example, `Running` removes the large Start action and makes the current step
primary; `Confirmation` holds the Room and mirrors the native confirmation
language; `Failed` separates completed, failed, and not-run work.

## Quiet Instrument

Quiet Instrument is the first implementation target. In Use Mode, an active
ritual appears as one compact, edge-anchored matte surface around 520-640 px
wide. Other Room components recede while the active ritual owns attention.

The instrument may show:

- ritual name and state;
- current step or decision;
- dependency/waiting language;
- pause/resume/stop/log actions already exposed by the runtime;
- failed/interrupted recovery language already present in run state.

It must not add new automation actions, hidden shortcuts, coordinate input, or
recording/observation behavior.

## Spatial Field

Spatial Field appears only when geometry is meaningful:

- a ritual opens multiple applications;
- windows or monitors will be arranged;
- existing windows may conflict;
- a partial layout needs recovery context.

The initial proof should be Project Room preflight. Do not show a desktop map
for every ritual.

## Editorial Ledger

Editorial Ledger appears when explanation matters:

- Support Desk runbooks;
- long dry-run previews;
- failure diagnosis;
- interrupted-run repair;
- logs, artifacts, and operator review.

It should preserve chronology and distinguish `completed`, `failed`, `not run`,
`declined`, `stopped`, `interrupted`, and `recovered`.

## Confirmation

Ritualist keeps the native top-level confirmation dialog. The active Room and
Quiet Instrument should visibly enter `Confirmation required`, while the native
dialog remains the authoritative decision surface above other applications.

## Non-Goals

This convergence work must not add:

- Watch Me, recording, replay, OCR, screenshot, keylogging, or browser-history
  learning;
- arbitrary recipe-supplied Python, JavaScript, PowerShell, shell, QML, or HTML;
- coordinate clicks, click-through implementation, taskbar hiding, kiosk mode,
  shell replacement, cloud sync, remote execution, marketplace behavior,
  password automation, or gameplay automation;
- suggestions or imports that auto-create, auto-enable, or auto-run behavior.

## First Milestone

The first implementation milestone is QML-only:

- keep Rooms ambient at rest;
- when a `ritual.card` enters `running`, `waiting`, `confirming`, `paused`,
  `failed`, or `interrupted`, place it as the Quiet Instrument at the right edge;
- dim non-active components so the Room still exists without becoming a
  dashboard wall;
- keep Edit Mode layout unchanged;
- preserve existing action IDs and explicit confirmation gates.

## Second Milestone

The second implementation milestone remains QML-only:

- make confirmation read as a held Room state while the native confirmation
  dialog remains authoritative;
- surface exact target/action/consequence language already present in runtime
  state;
- make recent activity more ledger-like with existing stopped, cleanup,
  ownership, and last-step metadata;
- avoid raw run paths, new action IDs, approval buttons inside the Room, or any
  new capture/automation behavior.

## Third Milestone

The third implementation milestone is shared rest-state chrome:

- make display-only elements such as labels, clocks, docks, and dividers ambient
  at rest instead of card-like;
- make supporting status, controller, target, Doctor, and recent-activity
  surfaces lower-emphasis while still readable and actionable;
- keep ritual cards, shortcut handoffs, and active/error states structurally
  clear;
- do not change component IDs, action IDs, bindings, or packaged acceptance
  expectations.

## Fourth Milestone

The fourth implementation milestone is bundled Room composition:

- make the starter Gaming, Project, and Support Desk Rooms read as activity
  environments within the first packaged viewport;
- preserve existing component IDs, action IDs, bindings, and recipe/target
  references;
- make Gaming quiet-instrument first, Project shortcut/preflight first, and
  Support Desk ledger/runbook first;
- keep the change data-only: no runtime behavior, automation surface, import,
  suggestion, or confirmation semantics change.

## Fifth Milestone

The fifth implementation milestone is Support Desk Editorial Ledger:

- expose bounded, sanitized run-log chronology to the Room surface;
- distinguish completed, failed, not-run, stopped, interrupted, and operator
  review metadata without showing raw log paths;
- keep `Open Logs` as the existing explicit action for deeper evidence;
- do not add recovery buttons, approval controls, automation actions, or new
  run semantics inside the Room.

## Sixth Milestone

The sixth implementation milestone is accessibility, performance, and wallpaper
dogfood validation:

- verify focus-ring contrast, readable matte surfaces, and keyboard-visible controls
  across the shared design system;
- keep reduced motion tied to the existing low performance mode and tokenized
  motion settings;
- record 100 and 300 component performance output before adding heavier visual
  effects;
- keep wallpaper coexistence honest: Desktop Work-Area may layer over system
  wallpaper, but blank-area click-through remains `NEEDS_HUMAN_REVIEW` until
  native hit-test evidence proves it;
- prove Quiet Instrument, Spatial Field, and Editorial Ledger share tokens,
  controls, accessibility behavior, and safety language rather than becoming
  separate products or themes.
