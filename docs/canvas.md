# Ritualist Canvas

Canvas is the product abstraction that lets Ritualist become a customizable PC
command surface without becoming a true Windows shell replacement. Home remains
the current renderer/surface. Canvas Foundation v1 adds the data model,
component registry, validation, storage, default templates, and performance
smoke that future UI work can render and edit.

The current pipeline is:

```text
Canvas document -> component registry -> validated component instances -> bindings -> renderer/runtime events
```

Canvas loading and validation are side-effect free. They do not run recipes,
open browsers, call Playwright, scan UI Automation, launch apps, click, type, or
call Doctor unless a future explicit command asks for live checks.

## Canvas Documents

A Canvas document is a local YAML file:

```yaml
schema: ritualist.canvas.v1
id: gaming_desktop
name: Gaming Desktop
mode: desktop_canvas
resolution_policy: responsive

background:
  type: gradient
  value: midnight_violet

grid:
  enabled: true
  size: 16

components:
  - id: diablo_night
    type: ritual.card
    x: 80
    y: 120
    width: 520
    height: 300
    z: 10
    props:
      title: Diablo Night
    binding:
      kind: recipe
      recipe_id: gaming_mode
```

User canvases live under the platform user-data directory in `canvases/`.
Bundled samples are local package templates and can be copied with:

```powershell
python -m ritualist canvas init
```

## Components

Canvas components are typed native Ritualist components. They are not arbitrary
QML, JavaScript, HTML, Python, or shell snippets.

Canvas Foundation v1 registers:

- `ritual.card`
- `ritual.status`
- `ritual.controller`
- `target.card`
- `target.status`
- `category.dock`
- `app.launcher`
- `window.layout_button`
- `doctor.badge`
- `recent.activity`
- `clock`
- `text.label`
- `image`
- `shape`
- `spacer/divider`

Each component type declares supported bindings, required props, risk,
imported-canvas policy, update behavior, performance class, and whether it can
trigger future actions. Trigger-capable components are metadata only in this
phase; validation and preview do not execute bindings.

## Bindings

Bindings describe what a component points at:

- `recipe`
- `intent`
- `target.start`
- `primitive_plan_preview`
- `app.launcher`
- `window.layout`
- `runtime_state`
- `doctor_status`
- `recent_runs`
- `category`
- `static`

Unresolved recipe and target bindings are warnings by default so shared
templates remain inspectable on machines that do not have the same local setup.
Strict validation can treat warnings as errors.

## Use Mode And Edit Mode

Canvas metadata names Use Mode and Edit Mode, but v1 does not implement a
visual editor. Use Mode means components are rendered as a command surface. Edit
Mode is future UI work for moving/resizing/configuring typed components.

## Shell Boundary

Canvas Mode is a reversible desktop canvas layer. It is not v1 shell
replacement. Ritualist does not hide the taskbar, replace Explorer, use kiosk
mode, or claim ownership of the Windows session.

Future stages can be:

- Stage 1: desktop canvas mode on top of the normal desktop.
- Stage 2: immersive/fullscreen canvas mode.
- Stage 3: true shell replacement research, only after separate safety,
  recovery, and policy design.

## Pack Domains

Future package types should remain separate trust domains:

- `.ritualistpack`: behavior, recipes, intents.
- `.ritualistcanvas`: visual layout, components, theme references.
- `.ritualisttheme`: colors/assets only.
- `.ritualistsuite`: future combined behavior + canvas + assets.

Canvas Foundation v1 implements local canvas documents only. It does not add
sharing, sync, marketplace behavior, or trusted approvals. Canvas pack metadata
must not carry remembered approvals or local target memory.

## Performance Rules

Canvas model generation and validation must stay cheap:

- no adapter calls
- no Playwright calls
- no UIA scans
- no Doctor runs
- no image decoding during model validation
- no action execution

Use:

```powershell
python -m ritualist perf canvas-model --mock-components 100 --json
python -m ritualist perf canvas-model --mock-components 300 --json
```

These commands report durations and advisory warnings without enforcing hard
timing gates in CI.
