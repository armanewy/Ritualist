# Ritualist Roadmap

This roadmap is intentionally conservative. Ritualist should be narrower than
its architecture: a local ritual/runbook engine with a desktop-native Room
surface. Recipes and rituals remain the center of gravity; Canvas, Rooms,
shortcuts, Suggestions, and packs must serve ritual quality, Room usefulness,
trust and safety, the Suggestion-to-draft loop, or pack/template reuse.

Ritualist should not expand horizontally while release acceptance is open.

## Current Focus

- Stabilize the v0.2 release line and cut feature creep.
- Keep product boundaries executable through tests and release acceptance
  evidence.
- Keep Home and CLI workflows responsive and diagnosable.
- Evolve Home toward Canvas as the Room implementation layer, without
  replacing Explorer, hiding the taskbar, rendering wallpapers, or adding
  arbitrary widget code.
- Keep recipes local-first, structured, Doctor-checkable, dry-runnable,
  confirmable, logged, and recoverable.
- Improve target resolution and intent planning without adding arbitrary code
  execution.
- Preserve imported-pack quarantine, disclosure, and policy checks.

## Active Feature Freeze

The current release line is frozen against new product systems and horizontal
platform work. Do not add:

- desktop-host expansion beyond Desktop Work-Area Mode and wallpaper
  passthrough
- native blank-area click-through, component-island windows, WorkerW/Progman
  attachment, desktop icon integration, fullscreen couch mode, shell
  replacement, or taskbar manipulation
- browser history collection, Recall-like sources, screenshots, OCR, or
  activity snapshots
- Watch Me, record mode, macro recording, teach-by-watching, global hooks, or
  coordinate capture
- marketplace behavior
- generic widget families or arbitrary-code component surfaces
- new primitive families unless a hero Room or runbook requires them and the
  full Doctor, dry-run, policy, confirmation, logging, recovery, and pack-safety
  gates are designed first

## Canvas Sequence

- Canvas Foundation: complete.
- Canvas Runtime Components: complete. Components now have typed runtime state
  and explicit action dispatch through existing safe services.
- Canvas Use Mode: current. The MVP renderer uses the Canvas view model,
  component geometry, runtime state, and explicit safe dispatch.
- Canvas Edit Mode / Room Builder: later, after the release gate. Editing
  should configure typed native components, never arbitrary user-supplied QML,
  JavaScript, HTML, or Python.
- Visual polish: only when it improves one of the hero Room loops.

## Near-Term Primitive Direction

- Do not add new primitive families during the active feature freeze.
- Keep existing read-only primitives focused on Doctor, planning, diagnostics,
  and hero Room needs.
- Keep mutation out of imported packs by default.
- Keep target and intent plans previewable before execution.
- Use fake adapters and golden JSON fixtures for all new primitive families.
- Keep intent planning deterministic and inspectable; see
  [Intents And Primitive Plans](intents_and_plans.md).
- Keep target discovery generic, read-only, and primitive-backed; see
  [Target Resolution Engine](target_resolution.md).
- Keep Canvas documents typed, local, and side-effect free; see
  [Ritualist Canvas](canvas.md).

## Future Mutating And Risky Primitives

Future reversible operations and high-risk operations must follow
[Mutating And Risky Primitives Design](mutating_risky_primitives_design.md).

That design is the required reference for:

- `network.reset`
- `nic.adapter`
- `firewall.rule`
- `registry.value`
- `restorepoint`
- `packages.winget`
- `wsl.distro`
- `sandbox.run`
- `driver.package`
- `vendor.update`
- `firmware.guard`
- `firmware.vendor_flash`
- `storage.volume`
- `bootmedia.rufus`
- `security.bitlocker`

No implementation should add these execution capabilities until the relevant
policy profile, Doctor checks, dry-run behavior, artifact snapshot, confirmation
requirements, recovery instructions, and test gates are designed and reviewed.

## Explicit Non-Goals

- AI planning
- arbitrary recipe-supplied Python, shell, PowerShell, or JavaScript
- raw host scripting escape hatches
- coordinate clicks
- cloud sync
- remote execution
- marketplace behavior
- password automation
- gameplay automation
- firmware, driver, or storage mutation without lab gates
