# Primitive Layer Gap Report

This report inventories the current Ritualist primitive layer before adding more
primitive work. It is intentionally descriptive. It does not add execution
capability, primitive adapters, or new recipe actions.

## Summary

Primitive Kernel v1 is already implemented. The current repo has primitive
models, action-to-primitive metadata, a registry, fake/no-op adapter contract,
CLI inspection, Doctor reporting, local primitive policy, pack review support,
and several read-only primitive executors.

The recommended next implementation phase is a read-only primitive pack
audit/hardening pass, not another Primitive Kernel implementation. Policy and
pack governance are present. This pass also hardened two metadata-only seams:
primitive-only capability names are now accepted by pack manifest validation
with platform checks, and `PrimitivePlan` objects can be evaluated by the
policy engine without execution.

Do not implement mutating or risky primitives yet. In particular, do not add
firmware, driver, storage, registry write, firewall write, service-control,
package-install, sandbox-run, raw PowerShell, arbitrary scripts, coordinate
clicks, cloud sync, remote execution, marketplace behavior, or gameplay
automation.

## Implemented

### Primitive Kernel Models

The following kernel models exist in `ritualist/primitives.py` and are covered
by tests in `tests/test_primitives.py`:

| Item | Status |
| --- | --- |
| `PrimitiveSpec` | Implemented and serializable |
| `PrimitiveFamily` | Implemented with dotted lowercase validation |
| `PrimitiveVerb` | Implemented with lowercase snake-case validation |
| `PrimitiveParameter` | Implemented with required/sensitive metadata |
| `PrimitiveRisk` | Implemented |
| `PrimitiveCapability` | Implemented |
| `PrimitiveAdapterBinding` | Implemented |
| `PrimitivePlan` | Implemented |
| `PrimitivePlanStep` | Implemented |
| `PrimitiveExecutionResult` | Implemented |
| `PrimitiveVerification` | Implemented |
| `PrimitiveArtifact` | Implemented |
| Primitive registry | Implemented |
| Fake/no-op primitive adapter | Implemented as `FakePrimitiveAdapter` |
| CLI primitive inspection | Implemented as `ritualist primitives`, `ritualist primitive show`, and `ritualist primitive families` |
| Doctor primitive reporting | Implemented in `ritualist/doctor.py` |

### Primitive Risk Model

`PrimitiveRisk` has the required values:

- `read_only`
- `launches_app`
- `controls_ui`
- `modifies_files`
- `risky`

Existing action `side_effect_level` metadata maps cleanly to this risk model.
The legacy action side effect `types_input` is mapped to primitive risk `risky`.

### Existing Primitive Family Coverage

| Family | Status | Notes |
| --- | --- | --- |
| `app.process` | Implemented/partial runtime | Action-backed launch/wait metadata exists; read-only process list/find/is_running/wait_running/wait_exit runtime exists. |
| `service.control` | Missing | Naming is reserved only. No service control primitive exists. |
| `window.topology` | Implemented/partial runtime | Action-backed window controls exist; read-only list/find/bounds/foreground/monitor runtime exists. |
| `uia.element` | Implemented/partial runtime | Existing desktop click maps here as risky/action-backed; read-only UIA label/control discovery runtime exists. |
| `browser.session` | Metadata/action-backed | `browser.open` maps to this family. |
| `browser.interact` | Metadata/action-backed | Structured browser media/click actions map here and remain policy-gated. |
| `browser.assert` | Implemented/partial runtime | Browser assertion and wait metadata exists; read-only runtime exists for text/title/url/element checks. |
| `hardware.inventory` | Read-only runtime | Snapshot and component read-only primitives exist. Windows-only. |
| `network.connectivity` | Read-only runtime | Snapshot/dns/tcp/route_hint/profile primitives exist. |
| `diagnostics.bundle` | Read-only runtime | Minimal/support/gamer_crash bundle primitives exist and emit redacted artifacts. |
| `packages.winget` | Missing | Future design only. |
| `sandbox.run` | Missing | Future design only. |
| `obs.session` | Missing | Naming is reserved only. |
| `vendor.update` | Missing | Future design only. |
| `firmware.guard` | Missing | Future design only. |
| `firmware.vendor_flash` | Missing | Future design only. |

Additional implemented families not listed in the original inventory prompt:

- `filesystem.assert`
- `filesystem.wait`
- `flow.control`
- `input.keyboard`
- `operator.notify`
- `operator.prompt`
- `registry.read`
- `runtime.wait`

These map existing action or predicate surfaces into primitive metadata. They do
not add new unsafe execution power.

### Policy And Pack Governance

The repo currently has:

| Item | Status |
| --- | --- |
| Primitive policy model | Implemented in `ritualist/policy.py` |
| Policy categories | Implemented |
| Policy decisions | Implemented |
| Policy profiles | Implemented: `consumer_safe`, `power_user`, `lab_only`, `enterprise_managed` |
| Imported-pack primitive policy checks | Implemented during pack enable and pack review |
| Nested primitive/predicate/branch validation | Implemented for `preflight`, `steps`, `verify`, `flow.if`, `then`, `else`, `on_timeout`, and `when` conditions |
| Never-importable categories | Implemented for embedded credentials, elevated unsigned executable hints, opaque binary assets, unsupported flash tools, raw firmware payloads, restore-point deletion, forced registry cleanup, destructive storage/system cleanup text, and related asset classes |
| `ritualist policy show` | Implemented |
| `ritualist policy check` | Implemented |
| `ritualist policy explain` | Implemented |
| Policy JSON output | Implemented |
| Pack validation against primitive risk | Implemented at pack enable and Home/classic review; archive validation also blocks never-importable content and arbitrary-code/coordinate-click action names |
| Primitive-only capability declarations in packs | Implemented for `hardware_inventory`, `network_connectivity`, and `diagnostics_collect`; Windows-only capabilities must declare Windows support |
| PrimitivePlan policy reporting | Implemented for side-effect-free plan checks |

### Read-Only Primitive Pack Coverage

The following read-only primitive groups exist and are tested in
`tests/test_read_only_primitives.py`:

| Group | Status |
| --- | --- |
| Process list/find/is_running/wait_running/wait_exit | Implemented and tested with fakes |
| Window list/find/bounds/foreground/monitor list | Implemented and tested with fakes |
| UIA list_labels/find_text/find_control/candidate_dump | Implemented and tested with fakes |
| Browser text/title/url/element assertions | Implemented; text/element are action-backed, title/url are primitive-only metadata/runtime |
| Hardware inventory snapshot and components | Implemented; Windows-only with friendly unsupported-platform errors |
| Network connectivity snapshot/dns/tcp/route_hint/profile | Implemented |
| Diagnostics bundle minimal/support/gamer_crash | Implemented with redacted artifacts and forbidden secret classes excluded |

### Docs Alignment

Docs are aligned with the current safety posture:

- `README.md` points future risky primitive work to `docs/roadmap.md` and
  `docs/mutating_risky_primitives_design.md`.
- `docs/roadmap.md` frames mutating/risky work as future work.
- `docs/mutating_risky_primitives_design.md` explicitly states that it is
  design-only and does not introduce runtime capabilities.
- The docs do not claim firmware, driver, storage, registry write, firewall
  write, package install, or sandbox-run mutation exists today.

## Partial

### Read-Only Runtime Adapter Boundaries

Several read-only primitive executors use existing concrete adapters when real
adapters are not supplied. Tests use fakes and Windows-specific imports remain
lazy.

Impact: acceptable today. Future work should continue tightening boundaries so
Doctor, pack review, and dry-run never accidentally probe real desktop or
browser state.

Hardening status:

- Semantic golden JSON fixtures now cover `primitives --json`,
  `policy show --json`, `actions --json`, representative `gaming_mode` Doctor
  JSON, representative `PrimitivePlan` policy reporting, and read-only
  primitive dry-run/execution reports.
- Fake-adapter coverage now exercises every implemented read-only primitive
  family and asserts those reads do not call app launch, UI click, browser
  click/open/media, keyboard input, or window mutation adapter methods.
- Diagnostics bundle primitives are still allowed to write explicit redacted
  artifact output under the requested diagnostics output directory; tests verify
  forbidden secret classes remain excluded.

## Missing

These families are intentionally missing and should remain missing until their
design, policy, Doctor, dry-run, artifact, confirmation, recovery, and testing
gates are complete:

- `service.control`
- `packages.winget`
- `sandbox.run`
- `obs.session`
- `vendor.update`
- `firmware.guard`
- `firmware.vendor_flash`

The following mutating/risky families from the design doc are also not
implemented and should not be added in the next phase:

- `network.reset`
- `nic.adapter`
- `firewall.rule`
- `registry.value` write/set/delete/restore
- `restorepoint.create`
- `wsl.distro`
- `driver.package`
- `storage.volume`
- `bootmedia.rufus`
- `security.bitlocker` mutation

## Recommended Next Implementation Phase

Do not run another Primitive Kernel prompt. The kernel exists.

Do not run a broad Primitive Policy / Pack Governance implementation prompt as
though policy were missing. Policy and pack governance exist.

The next phase should be:

1. Reuse the hardened read-only primitive contracts from future
   target/intent import paths.
2. Add targeted fixtures only when future primitive schemas intentionally
   change.
3. Keep expanding fake-adapter coverage for any newly introduced read-only
   primitive family before adding target/intent dependencies.

This phase should start with: inspect first, harden missing/partial pieces, do
not duplicate existing models, registries, policy engines, or CLI commands.

## What Not To Implement Yet

Do not implement:

- Firmware flashing or firmware update execution.
- Driver install, rollback, or vendor updater execution.
- Storage partitioning, formatting, boot media writes, or destructive disk
  actions.
- Registry writes, forced registry cleanup, or restore-point deletion.
- Firewall writes or service stop/start/restart.
- Package install/upgrade/uninstall primitives.
- Sandbox execution primitives.
- Raw PowerShell, arbitrary scripts, arbitrary host commands, arbitrary
  recipe-supplied Python/JavaScript, or script escape hatches.
- Coordinate clicks.
- Cloud sync, remote execution, marketplace behavior, or gameplay automation.

## Validation Commands

The inventory gate should be considered complete when these commands pass:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
$env:PYTHONFAULTHANDLER = "1"
python -m pytest -q
python -m compileall -q ritualist tests
python -m ritualist primitives --json
python -m ritualist actions --json
python -m ritualist dry-run gaming_mode
python -m ritualist doctor gaming_mode --json --no-strict
```
