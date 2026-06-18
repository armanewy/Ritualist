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
- a desktop component layer that can sit over the user's existing wallpaper

A Room is not:

- a Windows user account
- a security sandbox
- a virtual desktop
- a Windows shell replacement
- a remote execution surface
- a marketplace object
- a wallpaper engine
- a live/video/web wallpaper renderer
- a place for arbitrary user-supplied QML, HTML, JavaScript, or Python

## Modes

**Use Mode** is where a user lives in the Room. It shows Room identity, runnable
rituals, target previews, status, controls, and recent activity.

In Desktop Work-Area Use Mode, a Room layers Ritualist components over Windows
and the user's wallpaper app. The wallpaper remains owned by Windows or the
wallpaper app; Ritualist does not render, manage, pause, stop, or replace it.
Blank desktop-area click-through is a target interaction policy, but it must be
reported as unverified until machine evidence proves it.

**Edit Mode** or **Room Builder** is where a user safely changes a Room. It must
operate through typed component schemas, validation, and explicit save/cancel
flows. Builder previews must not auto-run behavior.

**Run Mode** is the active ritual state. It must keep status, confirmation,
pause/resume/stop controls, logs, and recovery visible.

## First Starter Rooms

The first starter Rooms are the three north-star hero Rooms. They should be
small, typed, ritual-aware, and built from existing safe Canvas infrastructure:

- **Gaming Room** (`gaming` -> `gaming_desktop`): the existing gaming Canvas
  direction, with target preview and explicit confirmation. It must not automate
  gameplay.
- **Project Room** (`project` -> `project_room`): project setup plan previews,
  launcher placeholders, status, and recent runs.
- **Support Desk** (`support_desk` -> `helpdesk_desktop`): runbook cards, Doctor,
  status, recent runs, and evidence surfaces.

`minimal_desktop` remains an internal Desktop Work-Area fallback and acceptance
fixture. It is intentionally not a promoted starter Room while the product is
narrowed around Gaming Room, Project Room, and Support Desk.

The starter Room CLI is a product-facing alias over bundled Canvas templates:

```powershell
python -m ritualist room list --json
python -m ritualist room show support_desk --json
```

`room show` reads the bundled starter template for evidence and onboarding
consistency. `canvas show` keeps the existing Canvas behavior, including user
Canvas overrides.

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
- wallpaper app replacement
- video backgrounds
- live/web/app wallpaper rendering
- arbitrary custom components
- arbitrary QML, HTML, JavaScript, or Python
- marketplace behavior
- cloud sync
- remote execution
- password automation
- gameplay automation
- coordinate clicks in product runtime
