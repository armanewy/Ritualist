# Ritualist Rooms

Ritualist uses **Room** as the user-facing product term and **Canvas** as the
implementation term. A Room is a personalized desktop for an activity. A Canvas
is the data model and runtime surface that renders that Room.

This is product language, not a runtime rewrite. The existing `ritualist.canvas`
modules, CLI commands, sample canvases, and runtime behavior remain the
technical foundation.

## Definition

A Room is:

- a Canvas layout
- a selected declarative theme
- built-in components
- safe behavior bindings
- local assets
- policy and validation results

A Room is not:

- a Windows user account
- a security sandbox
- a virtual desktop
- a Windows shell replacement
- a remote execution surface
- a marketplace object
- a place for arbitrary user-supplied QML, HTML, JavaScript, or Python

## Modes

**Use Mode** is where a user lives in the Room. It shows Room identity, runnable
rituals, target previews, status, controls, and recent activity.

**Edit Mode** or **Room Builder** is where a user safely changes a Room. It must
operate through typed component schemas, validation, and explicit save/cancel
flows. Builder previews must not auto-run behavior.

**Run Mode** is the active ritual state. It must keep status, confirmation,
pause/resume/stop controls, logs, and recovery visible.

## First Starter Rooms

The first starter Rooms should be small, typed, and built from existing safe
Canvas infrastructure:

- **Minimal Room**: a calm starter with status, recent activity, clock, and a few
  safe ritual cards.
- **Gaming Room**: the existing `gaming_desktop` direction, with target preview
  and explicit confirmation. It must not automate gameplay.
- **Work/Project Room**: project setup rituals, folder/app launchers, status, and
  recent runs.
- **Focus/Study Room**: a low-distraction room with current task, status, and
  safe focus rituals.
- **Helpdesk Room**: runbook cards, Doctor, status, recent runs, and evidence
  surfaces.

## Pack Separation

Ritualist should keep pack types explicit:

- **Theme Pack**: visual tokens and local assets only. No behavior.
- **Canvas/Room Pack**: layout, components, selected theme, local assets, and
  safe bindings.
- **Ritual Pack**: typed recipes and policy-reviewed behavior.
- **Suite Pack**: a bundle of Theme, Canvas/Room, and Ritual packs with review
  metadata.

Importing any pack must not auto-run behavior. Risky behavior must remain behind
explicit confirmation gates.

## Out Of Scope

These are out of scope for the Room Builder foundation:

- true Windows shell replacement
- taskbar hiding or kiosk mode
- video backgrounds
- arbitrary custom components
- arbitrary QML, HTML, JavaScript, or Python
- marketplace behavior
- cloud sync
- remote execution
- password automation
- gameplay automation
- coordinate clicks in product runtime
