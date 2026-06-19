# Room Builder Roadmap

Room Builder is the product-facing name for Canvas Edit Mode. The foundation
has landed through the Edit Model and UI MVP; future work should deepen the
three hero Rooms and improve editing/state quality, not rebuild Edit Mode.

## Stage 1: Theme Token Schema

Add safe declarative theme tokens:

- theme document model
- typed token validation
- token resolver
- sample `setpiece.paper` theme
- theme CLI list/show/validate
- tests for invalid colors, references, recursion, remote assets, and code-like
  fields

No QML redesign is required in this stage.

## Stage 2: Theme-To-Canvas Bridge

Load selected themes for Canvas Use Mode and expose a read-only token map to
built-in QML components. Invalid themes should fail validation before render.
Missing optional values should fall back to app defaults.

Acceptance evidence should include selected theme id and validation status.

## Stage 3: Accessibility Diagnostics

Add contrast and legibility diagnostics for themes and Canvas/component styling.
Warnings should preserve local customization freedom; malformed or unsafe values
should remain errors.

## Stage 4: Visual Performance Budgets

Add component performance profiles and Canvas performance diagnostics. Record
100 and 300 component outputs before adding heavier visuals or animations.

## Stage 5: Starter Rooms

Introduce curated Room templates using existing Canvas infrastructure:

- Gaming Room
- Project Room
- Support Desk

`minimal_desktop` may remain as an internal Desktop Work-Area fallback and
release-acceptance fixture, but it is not a promoted starter Room. Do not add a
fourth promoted Room until the three hero Rooms work end to end. Room aliases
may map to Canvas commands internally. No new risky behavior should be
introduced.

## Stage 6: Use Mode Visual Refresh

Refresh built-in component visuals using tokens and built-in variants only.
Required states must remain visible: ready, running, waiting, confirming,
paused, stopped, failed, and interrupted.

Packaged acceptance must still pass or honestly mark human-review items.

## Stage 7: Edit Model Foundation

Status: complete.

Model/controller support exists before the full editor UI:

- edit session lifecycle
- selection model
- move/resize model
- snap grid data
- property inspector schema data
- undo/redo command model
- dirty state
- save/cancel flow
- validation before save

Editor previews must not auto-run behavior.

## Stage 8: Room Builder UI MVP

Status: complete.

The minimal visual editor exists:

- top bar with Done and Cancel
- component palette
- canvas preview
- properties panel
- selected component outline
- safe move/resize controls
- save/discard confirmation

Behavior bindings should be shown and validated, not executed from preview.

## Stage 9: Hero Room Depth

Deepen exactly the promoted starter Rooms:

- Gaming Room
- Project Room
- Support Desk

Do not promote a fourth Room. `minimal_desktop` must remain available as an
internal Desktop Work-Area fallback and acceptance fixture, not a promoted Room.

Hero Room work should focus on better ritual cards, target/plan previews,
status, recent activity, safe launch affordances, and evidence surfaces without
adding new risky behavior.

## Stage 10: State UX, Shortcuts, And Suggestions

Improve the Room and Builder experience around:

- visible states: ready, running, waiting, confirming, paused, stopped, failed,
  interrupted, and draft/dirty editor state
- keyboard shortcuts for safe editor and Room navigation commands
- Suggestions that can draft recipes or Room changes only after explicit user
  review

Suggestions, shared/imported behavior, and imported Room content must never
auto-run or auto-create recipes, Rooms, components, approvals, or risky actions.
Blank-area click-through remains unimplemented and frozen; do not reopen
desktop-host research for this stage.

## Required Evidence

Each stage should run:

- `python -m pytest -q`
- `python -m compileall -q setpiece tests`

Stages that change runtime UI should also run packaged acceptance with a unique
artifact directory.

## Explicitly Out Of Scope

- true shell replacement
- taskbar hiding
- kiosk mode
- video backgrounds
- marketplace behavior
- arbitrary custom components
- arbitrary QML, HTML, JavaScript, or Python
- remote execution
- cloud sync
- password automation
- gameplay automation
- coordinate clicks in product runtime
