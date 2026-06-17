---
name: ritualist-release-validation
description: Use for Ritualist release validation, packaged dogfood, release checklist updates, acceptance harness work, tag readiness, and v0.2/v0.3 release gates. Enforces Ritualist safety boundaries, structured evidence requirements, human-review semantics, and no-tag-unless-explicit policy.
---

# Ritualist Release Validation

## Release Gate Workflow

Use this workflow for Ritualist release validation, packaged desktop dogfood,
release checklist updates, acceptance harness changes, and tag readiness.

1. Start from a clean, current branch:
   - `git pull --ff-only`
   - `git status --short --branch`
2. Run the required validation commands:
   - `python scripts/check_line_endings.py --stats --check-git-head --check-git-index`
   - `python -m pytest -q`
   - `python -m compileall -q ritualist tests`
   - `.\scripts\build_windows_app.ps1`
   - `.\scripts\ritualist_release_acceptance.ps1 -Packaged -RecordScreen -EvidenceDir artifacts\release-acceptance`
3. Read `artifacts\release-acceptance\acceptance-summary.json` and
   `artifacts\release-acceptance\acceptance-summary.md`.
4. Update `RELEASE_CHECKLIST.md` with factual evidence only.
5. Report PASS / FAIL / NEEDS_HUMAN_REVIEW, blockers, artifact paths, and
   taggability.

## Safety Boundaries

Do not add or expand these capabilities during release validation unless the
user explicitly asks in a separate message and the release scope permits it:

- arbitrary recipe-supplied Python
- arbitrary recipe-supplied JavaScript
- arbitrary QML or HTML components
- coordinate clicks in product runtime
- cloud sync
- remote execution
- marketplace behavior
- gameplay automation
- password or credential automation
- true Windows shell replacement
- taskbar hiding or kiosk mode
- risky or mutating primitives

Keep Windows UI Automation imports lazy in product code. Tests must remain
cross-platform and use fakes/mocks instead of requiring a real Windows desktop.
Use explicit confirmation gates for risky desktop actions.

## Evidence Rules

- Mark a check `PASS` only when structured evidence or visual evidence supports
  the claim.
- Mark ambiguous visual or subjective checks as `NEEDS_HUMAN_REVIEW`, not PASS.
- Treat screenshots and screen-frame captures as supporting evidence; prefer
  structured logs, runtime events, run logs, process trees, window trees, and
  z-order captures as primary machine evidence.
- Keep packaged app evidence separate from source CLI supplemental evidence.
- Confirm packaged Home, Canvas Use Mode, and classic GUI were launched from
  `dist\Ritualist\Ritualist.exe`.
- Confirm confirmation, declined-run, recovery, Watch Me, pack import/export,
  and performance claims are supported by logs or artifacts.

## Tag Policy

Do not create or push a release tag unless the user explicitly asks for the tag
in a separate message. A tag is not ready while any release check is `FAIL` or
`NEEDS_HUMAN_REVIEW`, unless the human release owner explicitly accepts the
remaining review items.
