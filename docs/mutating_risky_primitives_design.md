# Mutating And Risky Primitives Design

Status: design only. This document does not introduce new recipe actions,
primitive executors, adapters, policy bypasses, or runtime capabilities.

Setpiece v0.1 is intentionally conservative: local-first recipes, structured
actions, dry-run, run logs, and confirmation gates. Future mutating and risky
primitives must preserve that posture while making reversible system changes
and later high-risk operations inspectable, recoverable, and policy-governed.

## Design Goals

- Represent system changes as explicit primitives with declared risk,
  capabilities, platform support, safeguards, artifacts, and rollback notes.
- Prefer reversible operations before destructive or hardware-level operations.
- Make Doctor preflight and dry-run authoritative enough for a user to decide
  whether to proceed before the runtime touches the host.
- Keep imported packs unable to smuggle high-risk behavior.
- Keep all implementation behind structured adapters. Do not add arbitrary
  Python, shell, PowerShell, JavaScript, remote execution, or plugin escape
  hatches.

## Non-Goals

- No implementation in this design pass.
- No raw scripts or arbitrary command execution.
- No remote execution, cloud sync, marketplace behavior, credential handling,
  OCR, coordinate clicks, firmware flashing, driver installation, or storage
  mutation in v0.1.
- No gameplay automation.

## Primitive Contract

Every future mutating or risky primitive must declare:

- primitive id, family, verb, and schema version
- required and optional parameters
- required capabilities
- supported platforms
- side-effect level
- policy category and imported-pack eligibility
- confirmation policy
- dry-run behavior
- Doctor preflight checks
- artifacts created before and after execution
- rollback or recovery instructions
- reboot behavior
- test gate required before release

Primitive execution must be routed through typed adapters. Recipes may pass only
structured parameters accepted by the primitive schema.

## Reversible Operations

These operations are candidates for earlier implementation because they can be
planned with a clear rollback or recovery path. They still require policy,
Doctor, dry-run, artifacts, and explicit confirmation.

| Primitive Family | Example Verbs | Required Safeguards | Notes |
| --- | --- | --- | --- |
| `network.reset` | `winsock`, `dns_cache`, `tcpip_stack` | Doctor network snapshot, dry-run, current adapter inventory, recovery notes, reboot-aware state when needed | Must never run arbitrary `netsh` strings from recipes. Use fixed adapter methods only. |
| `nic.adapter` | `disable_enable`, `restart` | adapter identity verification, current IP/profile snapshot, confirmation, connectivity recovery notes | Must identify adapters by stable local metadata, not display text alone. |
| `firewall.rule` | `add`, `remove`, `enable`, `disable` | export existing matching rules, dry-run diff, explicit confirmation, rollback rule set | Imported packs should require disclosure or be blocked depending scope. |
| `registry.value` | `set`, `delete`, `restore` | export affected keys first, type validation, exact key/value diff, restore artifact, double confirmation for sensitive hives | No force cleanup, wildcard deletion, or broad registry mutation. |
| `restorepoint` | `create` | OS support check, admin check, disk/restore service check, artifact with restore point metadata | This is a safeguard primitive and may be prerequisite for riskier changes. |
| `packages.winget` | `install`, `upgrade`, `uninstall`, `pin`, `source_list` | package id verification, source verification, dry-run command preview, user confirmation, post-install verification | No arbitrary winget arguments from recipes. |
| `wsl.distro` | `export`, `import`, `unregister` | distro existence check, export path validation, artifact checksum, disk space check, double confirmation for unregister | Export/import are preferred; unregister is high risk and likely private-pack only. |
| `sandbox.run` | `create`, `run_package`, `destroy` | sandbox image/source verification, network isolation choice, output artifact capture, no host secret mounts by default | Must not become an arbitrary command runner on the host. |

### Reversible Operation Lifecycle

1. Resolve target: identify the adapter, rule, key, package, distro, or sandbox.
2. Doctor preflight: verify prerequisites, privileges, current state, and risks.
3. Dry-run: produce a redacted plan and expected state transition.
4. Snapshot: write restore artifacts before mutation.
5. Confirm: explicit user confirmation, double confirmation if policy requires.
6. Execute: one typed adapter call per primitive step.
7. Verify: read-only post-check confirms expected state.
8. Rollback notes: include exact restore command or in-app recovery path.

## High-Risk Operations

These operations are not candidates for casual consumer workflows. Most should
start as `never_importable`, `private_pack_only`, or `blocked_by_default` until
manual lab validation exists.

| Primitive Family | Example Verbs | Minimum Gate | Notes |
| --- | --- | --- | --- |
| `driver.package` | `stage`, `install`, `rollback` | lab-only or managed policy, vendor/package signature verification, restore point, double confirmation, reboot-aware state | Must verify hardware model and package identity before install. |
| `vendor.update` | `check`, `download_metadata`, `apply` | managed/power-user policy, vendor signature and model checks, AC power check when relevant, recovery notes | No automatic web downloads in early versions. Metadata-only checks can be read-only. |
| `firmware.guard` | `assess`, `preflight`, `block_if_unsafe` | read-only first, model/vendor/BIOS verification, AC power and BitLocker checks | Guard primitives should prevent unsafe flashing rather than perform flashing. |
| `firmware.vendor_flash` | `prepare`, `flash` | hardware lab manual gate, never importable by default, double confirmation, AC power, BitLocker suspend/restore guidance, recovery media | Firmware flashing should remain out of consumer_safe and power_user until proven in lab. |
| `storage.volume` | `inspect`, `mount`, `format`, `partition` | inspect read-only first, destructive actions never importable without local author approval, backups and recovery instructions | Destructive storage actions must require explicit local author approval and double confirmation. |
| `bootmedia.rufus` | `inspect_iso`, `write_usb` | ISO checksum/signature, target drive confirmation, destructive drive warning, lab/manual gate | Must clearly identify the USB device and expected data loss. |
| `security.bitlocker` | `status`, `suspend`, `resume`, `backup_key_check` | status read-only first, recovery-key availability check, double confirmation for suspend, resume verification | Never log recovery keys or secrets. |

### High-Risk Release Stages

1. Metadata only: primitive specs, policy decisions, and Doctor checks.
2. Read-only probes: model, version, package, and environment assessment.
3. Dry-run previews: exact typed operations without execution.
4. Lab-only execution: fake adapters plus manual hardware lab checklist.
5. Private-pack controlled use: local author only, never imported silently.
6. Managed policy: enterprise-managed profile may allow narrow operations with
   external policy files in a future design.

## Policy Requirements

Policy decisions must be local, explicit, inspectable, and profile-aware.

### `consumer_safe`

- Allows read-only primitives and low-risk local workflow operations.
- Mutating operations are blocked unless they are proven reversible and have
  strong snapshots, Doctor checks, and confirmation.
- High-risk operations are blocked.
- Imported packs cannot enable mutating or risky operations without disclosure
  or explicit local approval.

### `power_user`

- Allows selected reversible operations with disclosure and confirmation.
- Requires dry-run and artifact snapshots for all mutations.
- Requires double confirmation for registry writes, package uninstall, WSL
  unregister, BitLocker changes, and any operation that can interrupt network
  connectivity.
- High-risk operations remain blocked or private-pack only.

### `lab_only`

- Allows controlled testing of selected high-risk operations in a documented
  hardware or VM lab.
- Requires manual gates, lab checklist IDs, and artifact bundles.
- Requires double confirmation and explicit recovery instructions.
- Never applies to imported packs by default.

### `enterprise_managed`

- Reserved for future managed local policy.
- Does not imply remote execution or cloud control.
- Allows narrowly scoped operations only when a local managed policy explicitly
  permits them.
- Requires audit artifacts and policy identifiers in run logs.

## Required Safeguards

### Doctor Preflight

Doctor must validate:

- OS and platform support
- required optional dependencies
- privilege/admin status when required
- target identity and current state
- policy profile decision
- expected reboot behavior
- AC/battery status when relevant
- BitLocker state when relevant
- vendor/model/package compatibility
- available disk space for backups, exports, or images
- rollback artifact location

Doctor must not mutate state.

### Dry-Run

Dry-run must show:

- exact primitive sequence
- target object and stable identifiers
- side-effect level and policy decision
- required confirmations
- expected artifacts
- expected rollback path
- unresolved questions

Dry-run must not launch apps, click UI, write files, download installers, change
settings, or execute host commands.

### Artifact Snapshot

Before mutation, Setpiece must capture the smallest useful restore artifact:

- firewall rule export
- registry key export
- network adapter/IP/profile snapshot
- package/version/source metadata
- WSL distro export metadata and checksum
- restore point metadata
- BitLocker status, never recovery keys
- hardware model/vendor/firmware version snapshot

Artifacts must be redacted and must not include secrets, passwords, tokens,
private keys, cookies, browser history, page contents, screenshots, or clipboard
contents by default.

### Explicit Confirmation

Confirmation must name:

- primitive family and verb
- target object
- current state and proposed state
- artifact snapshot path
- rollback/recovery note
- policy profile and decision

### Double Confirmation

Double confirmation is required for:

- firmware flashing
- driver installation or rollback
- destructive storage operations
- registry deletion or sensitive hive edits
- BitLocker suspend/resume when it changes protection state
- WSL unregister
- package uninstall
- network reset that may disconnect the user

### AC And Power Checks

Required for firmware, driver, BIOS/vendor update, boot media, and long-running
storage operations. The preflight must block or require lab override when the
machine is on battery or power state cannot be verified.

### BitLocker Checks

Required for firmware, BIOS/vendor update, boot media, storage volume, and
driver operations that could affect boot. Setpiece must never log recovery
keys. If recovery-key availability cannot be confirmed safely, the operation
must stop with recovery instructions.

### Model, Vendor, And Package Verification

High-risk primitives must verify:

- hardware model and vendor
- current firmware/driver/package version
- target package version
- signature/checksum/source
- compatibility rules

Ambiguous matches must be blocked.

### Reboot-Aware Run State

Mutating/risky primitives may require reboot. Run logs must support:

- `reboot_required`
- `waiting_for_reboot`
- `resumed_after_reboot`
- `reboot_failed_or_not_detected`
- last verified step before reboot
- post-reboot verification result

No recipe should assume a reboot completed without verification.

### Recovery Instructions

Every mutating or risky plan must include recovery instructions written before
execution. Recovery instructions should be local, specific, and printable:

- where the artifact is stored
- how to restore the previous state
- what to do if reboot fails
- when to stop and use vendor/manual recovery

## Pack Governance

Pack validation must recursively inspect primitives in normal steps, preflight,
verify, `flow.if` branches, timeout handlers, intent plans, and future target
plans.

| Category | Meaning | Imported Pack Behavior |
| --- | --- | --- |
| `importable_without_warning` | Read-only or proven safe metadata operations | May be imported and reviewed normally. |
| `importable_with_disclosure` | Low-risk but stateful or privacy-relevant operations | Import requires visible disclosure and explicit enable. |
| `blocked_by_default` | Mutating or risky operations not appropriate for normal imported packs | Import can quarantine but cannot enable without local/private policy. |
| `private_pack_only` | Allowed only for local author/private workflows | Blocked for untrusted imported packs. |
| `never_importable` | Classes that must never come from untrusted packs | Import must fail or quarantine as blocked. |

Never importable classes include:

- embedded credentials
- arbitrary unsigned executables launched elevated
- opaque binary helper DLLs
- unsupported flash tools
- raw firmware payloads
- force BIOS downgrade
- delete all restore points
- force registry cleanup
- destructive storage actions without local author approval

Exported packs must not include local approval state, policy overrides, local
absolute paths from user variables, secrets, logs, run artifacts, or browser
profiles.

## Testing Gates

### Unit Tests

- schema validation
- policy decisions by profile
- Doctor preflight result shape
- dry-run plan shape
- artifact manifest shape
- rollback instruction generation
- blocked import behavior

### Fake Adapters

Every primitive must have fake adapter coverage for:

- success
- failure
- missing dependency
- unsupported platform
- permission denied
- interrupted/reboot-required state where relevant

Fake adapters must be the default for CI tests.

### Golden Fixtures

Golden fixtures should cover:

- policy reports
- Doctor JSON
- dry-run JSON
- artifact manifests
- pack validation reports
- recovery instruction text

Schema changes must be intentional and reviewed.

### VM Integration Tests

VM tests may cover reversible operations:

- firewall rule add/remove
- registry set/export/restore in a disposable key
- network reset simulation where safe
- Winget metadata-only checks
- WSL export/import with a disposable distro

VM tests must not require physical hardware.

### Hardware Lab Manual Gates

High-risk primitives require manual lab gates before any release:

- documented hardware model
- vendor package source
- screenshots or external notes stored outside default run logs when needed
- AC power verified
- BitLocker state verified without logging keys
- recovery media available
- human sign-off

Hardware lab gates should remain outside normal CI.

### Performance Tests

Mutating/risky primitive planning and Doctor must remain responsive:

- no GUI-thread blocking
- bounded filesystem scans
- bounded registry/package inventory
- cancellable long probes
- run-log writes throttled
- large artifact hashing done off the UI thread

## Implementation Roadmap

1. Metadata only: add primitive specs and policy decisions without execution.
2. Doctor only: add read-only preflight checks and JSON reports.
3. Dry-run only: compile plans and artifact requirements.
4. Fake-adapter execution: exercise lifecycle and run logs in CI.
5. Reversible primitive pilot: choose one low-risk operation with rollback.
6. VM validation: prove rollback and failure behavior.
7. Private local use: require explicit local author approval.
8. High-risk lab design: keep hardware-level operations behind lab-only gates.

No stage may skip policy, Doctor, dry-run, artifacts, confirmation, recovery
instructions, or tests appropriate to its risk level.
