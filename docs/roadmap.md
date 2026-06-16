# Ritualist Roadmap

This roadmap is intentionally conservative. Ritualist should expand by adding
inspectable, typed, local primitives only after the policy, Doctor, dry-run,
artifact, and test contracts are clear.

## Current Focus

- Keep Home and CLI workflows responsive and diagnosable.
- Keep recipes local-first and structured.
- Improve target resolution and intent planning without adding arbitrary code
  execution.
- Preserve imported-pack quarantine, disclosure, and policy checks.

## Near-Term Primitive Direction

- Continue adding read-only primitives that improve Doctor, planning, and
  diagnostics.
- Keep mutation out of imported packs by default.
- Keep target and intent plans previewable before execution.
- Use fake adapters and golden JSON fixtures for all new primitive families.
- Keep intent planning deterministic and inspectable; see
  [Intents And Primitive Plans](intents_and_plans.md).

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
