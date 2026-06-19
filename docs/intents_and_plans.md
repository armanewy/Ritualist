# Intents And Primitive Plans

Setpiece intents are user-visible descriptions of local goals. They are not
freeform prompts and they are not AI planning. Intent Plan Compiler v1 uses
deterministic, reviewed rules to turn an `IntentSpec` into a `PrimitivePlan`.

The current pipeline is:

```text
User/Home intent -> IntentSpec -> PrimitivePlan -> Policy/Doctor report -> execution later
```

Plan preview is side-effect free. It must not launch apps, click UI, type,
mutate files, run shell commands, download assets, or access credentials.

## IntentSpec

An intent includes:

- `intent_id`
- `kind`
- `display_name`
- `description`
- optional `target`
- `requested_outcome`
- `constraints`
- `preferences`
- `risk_budget`
- `user_visible_summary`

Supported v1 fixture references:

- `diagnostics.collect:minimal`
- `workspace.prepare:basic`
- `target.start:placeholder`
- `target.start:<target-id-or-alias>`

The fixture syntax is intentionally small. It is a stable developer-facing
entry point for Home and CLI plan previews while richer intent input evolves.
Concrete `target.start:<target>` references are routed through the
[Target Resolution Engine](target_resolution.md) and remain side-effect free.

## PrimitivePlan

A compiled plan includes:

- primitive plan steps
- required primitives
- required capabilities
- risk summary
- confirmations needed
- expected artifacts
- verification steps
- cleanup/rollback notes
- unresolved questions

`cleanup_or_rollback_notes` and `rollback_or_cleanup_notes` currently expose
the same data for compatibility with both naming conventions.

## Doctor And Policy

Plan Doctor checks primitive support, capabilities, unresolved questions, and
policy findings without running the plan. Policy evaluation works on compiled
plans so imported or future Home-driven plans can be inspected before any
execution is added.

## Home Readiness

The compiler also exposes a small Home summary model:

- card title
- user-visible summary
- risk summary
- Doctor status
- policy status
- unresolved questions
- estimated step count
- expected confirmations

Home can use this model later without needing to parse low-level primitive plan
details directly.

## Non-Goals

Intent Plan Compiler v1 does not add:

- AI planning
- arbitrary expressions
- arbitrary code or scripts
- raw PowerShell
- coordinate clicks
- remote execution
- cloud sync
- marketplace behavior
- firmware, driver, storage, registry, firewall, or service mutation
- gameplay automation
