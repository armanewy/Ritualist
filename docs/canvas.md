# Setpiece Canvas

Canvas is the implementation layer that lets Setpiece present a ritual-aware
desktop command surface without becoming a Windows shell replacement, file
manager, wallpaper renderer, or generic widget platform. Home remains a
compatibility surface. Canvas Foundation v1 adds the data model, component
registry, validation, storage, default templates, and performance smoke. Canvas
Runtime Components v1 adds model/controller bindings from those typed
components to existing Setpiece recipe, Doctor, target, runtime, and
run-history services. Canvas Use Mode MVP adds a bundled typed QML renderer for
using a Canvas document as a runtime command surface. The Canvas Edit model and
Room Builder UI MVP now exist for configuring typed native components.

The current pipeline is:

```text
Canvas document -> component registry -> validated component instances -> runtime model -> use view model -> renderer/runtime events
```

Canvas loading and structural validation are side-effect free. They do not run
recipes, open browsers, call Playwright, scan UI Automation, launch apps, click,
type, or call Doctor.

Full binding validation can optionally check installed recipes and known target
catalog entries. That is still read-only, but UI refresh paths should use the
cheap structural validation path so they do not scan local runtime state during
rendering.

## Canvas Documents

A Canvas document is a local YAML file:

```yaml
schema: setpiece.canvas.v1
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
python -m setpiece canvas init
```

## Components

Canvas components are typed native Setpiece components. They are not arbitrary
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

Component types also expose prop schema metadata for future editors. Each prop
schema includes:

- `name`
- `type`: `string`, `bool`, `int`, `float`, `enum`, `color`,
  `local_asset_path`, `recipe_id`, or `target_id`
- `required`
- `default`
- `allowed_values`
- `editor_hint`

`required_props` and `optional_props` remain for compatibility with older
Canvas-aware code.

## Risk Mapping

Canvas component risk uses the same vocabulary as primitive risk metadata:

- `read_only`
- `launches_app`
- `controls_ui`
- `modifies_files`
- `risky`

Canvas Foundation v1 does not add mutating Canvas components. The
`modifies_files` value exists so future component metadata can align with the
primitive policy layer without inventing a separate taxonomy.

## Canvas Runtime Components

Canvas Runtime Components v1 builds a `CanvasRuntimeModel` from a Canvas
document. The model includes component state, enabled/disabled actions, active
run summaries, recent activity, Doctor summaries, target plan summaries,
unresolved binding warnings, and advisory performance counters.

The runtime model supports these component families:

- `ritual.card`: explicit `run`, `dry_run`, `doctor`, `edit_recipe`, and
  `open_logs` actions through existing recipe/Home action services.
- `ritual.status`: current or last recipe state such as `idle`, `running`,
  `waiting`, `paused`, `confirming`, `stopped`, `failed`, `interrupted`, or
  `success`.
- `ritual.controller`: explicit `pause`, `resume`, `stop`, and `open_run_log`
  actions when a matching runtime control exists.
- `target.card`: read-only target discover/plan preview. Target execution is
  not added here; the action remains `preview_plan`.
- `target.status`: last known target state and summary data.
- `doctor.badge`: cached or explicit Doctor status. Doctor remains
  side-effect free.
- `recent.activity`: bounded run-history summaries including stopped, failed,
  and interrupted runs.
- `category.dock`: model-level category grouping/filter state.
- `text.label`, `image`, `shape`, and `clock`: display-only runtime state.

Canvas components never call low-level adapters directly. Runtime actions route
through existing controllers/services:

- recipe runner
- Doctor
- target resolver / intent planner
- runtime controls
- run history

Canvas load, structural validation, preview, and runtime model construction do
not execute recipes, launch apps, click UI, type, or open browsers.

## Dispatch Safety

Canvas action dispatch is explicit:

```python
dispatch_canvas_action(canvas_id, component_id, action_id, params)
```

Dispatch rules:

- the component id must exist
- the action id must be listed by the component type metadata
- required bindings must exist and be resolvable when a known binding set is
  supplied
- arbitrary action strings are rejected
- display-only components expose no runtime actions
- policy and confirmation behavior stays inside the existing runtime services
- `--dry-run` validates dispatch and does not execute the component action

Developer diagnostics:

```powershell
python -m setpiece canvas runtime gaming_desktop --json
python -m setpiece canvas action gaming_desktop diablo_night doctor --dry-run
python -m setpiece perf canvas-runtime --mock-components 100 --json
```

## Canvas Use Mode

Use Mode renders a Canvas document with absolute component geometry and live
runtime state from the Canvas view model. It is intentionally a functional MVP,
not a visual polish pass.

Launch it with:

```powershell
python -m setpiece canvas use gaming_desktop
python -m setpiece canvas use --mock --mock-components 100
```

Supported component rendering in the MVP:

- `ritual.card`
- `ritual.status`
- `ritual.controller`
- `target.card`
- `target.status`
- `doctor.badge`
- `recent.activity`
- `category.dock`
- `text.label`
- `image`
- `shape`
- `clock`

Use Mode consumes `CanvasViewModel`, which combines component layout, props,
bindings, runtime state, warnings, and enabled actions. It does not call
low-level adapters during load. It does not run Doctor, scan UI Automation,
resolve targets, or read run logs on the UI thread.

Explicit user actions dispatch through `CanvasRuntimeController`. Display-only
components expose no actions. Unknown actions and unsupported component/action
pairs are rejected. Existing recipe confirmation and policy gates remain inside
the runtime services.

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

The canonical form is the explicit `binding:` object:

```yaml
components:
  - id: diablo_night
    type: ritual.card
    props:
      title: Diablo Night
    binding:
      kind: recipe
      recipe_id: gaming_mode
```

Legacy props such as `recipe_id`, `target`, and `target_id` are still accepted.
`normalize_canvas_bindings(document)` returns a copied document with those
legacy references mirrored into canonical binding objects. It does not mutate
the input document.

## Asset Sandbox

Canvas image components can reference local assets only. The validator does not
decode images and does not require asset files to exist unless a future strict
asset check explicitly adds that behavior.

Canvas v1 rejects:

- remote URLs
- absolute paths outside `<canvas_dir>/assets`
- relative `..` traversal outside the assets folder
- ambiguous drive-relative or stream-like relative paths containing `:`
- executable or script-like asset names such as `.exe`, `.msi`, `.ps1`, `.bat`,
  `.cmd`, `.js`, `.vbs`, `.dll`, `.lnk`, and `.url`

Relative paths are resolved into the canvas assets sandbox. Both `hero.png` and
`assets/hero.png` are treated as canvas-local asset references.

## Validation Modes

Use structural validation for UI/model refreshes:

```python
validate_canvas_structure(document, canvas_dir=canvas_dir)
```

Use live binding validation only when a user explicitly asks to check local
bindings:

```python
validate_canvas_bindings(document, canvas_dir=canvas_dir)
```

The older `validate_canvas_document(..., check_bindings=True)` remains
compatible and performs live binding checks by default. Pass
`check_bindings=False` or call `validate_canvas_structure` for the cheap path.

## Use Mode And Edit Mode

Canvas metadata names Use Mode and Edit Mode. Use Mode is implemented as a
runtime command surface. Edit Mode now has model/controller support and a Room
Builder UI MVP for moving, resizing, selecting, inspecting, validating, and
saving typed components. Preview and validation still must not execute
component behavior.

Next Canvas-facing work is hero-room depth, clearer runtime/editor state UX,
safe shortcuts, and Suggestions that draft changes only after explicit user
review. It is not a rebuild of Edit Mode.

## Shell Boundary

Canvas Mode is a reversible desktop canvas layer. It is not v1 shell
replacement. Setpiece does not hide the taskbar, replace Explorer, use kiosk
mode, or claim ownership of the Windows session.

The supported stage is Desktop Work-Area mode on top of the normal desktop,
with wallpaper passthrough to whatever Windows or a wallpaper app already owns.
Setpiece does not render, manage, pause, stop, or replace wallpaper.

Blank-area click-through is not implemented and remains frozen. Desktop-host
expansion is frozen after Desktop Work-Area mode and wallpaper passthrough: no
native click-through research, immersive/fullscreen mode, shell replacement
research, taskbar manipulation, WorkerW/Progman attachment, or desktop icon
integration belongs on the v0.2 release line.

## Pack Domains

Setpiece keeps package types in separate local trust domains:

- `.setpiecepack`: behavior, recipes, intents.
- `.setpiececanvas`: visual layout, display-safe components, and local assets.
- `.setpiecetheme`: colors and local visual assets only.
- `.setpiecesuite`: future combined behavior + canvas + assets.

Canvas and theme packs are local archives. Import stores them in quarantine,
disabled by default, and does not run rituals or activate components. Canvas
pack validation rejects arbitrary component code, auto-run fields, remote image
URLs, executable-like assets, and action-triggering component types. Theme packs
cannot contain recipes, actions, intents, components, or remembered approvals.

Suite packs are design-only in this phase. There is no network sharing, sync,
marketplace behavior, auto-install, or trusted approval propagation. Canvas pack
metadata must not carry remembered approvals or local target memory.

## Performance Rules

Canvas model generation and validation must stay cheap:

- no adapter calls
- no Playwright calls
- no UIA scans
- no Doctor runs
- no image decoding during model validation
- no action execution
- runtime model updates should be coalesced before renderer delivery

Use:

```powershell
python -m setpiece perf canvas-model --mock-components 100 --json
python -m setpiece perf canvas-model --mock-components 300 --json
python -m setpiece perf canvas-runtime --mock-components 100 --json
python -m setpiece perf canvas-runtime --mock-components 300 --json
python -m setpiece perf canvas-use --mock-components 100 --json
python -m setpiece perf canvas-use --mock-components 300 --json
```

These commands report durations and advisory warnings without enforcing hard
timing gates in CI.
