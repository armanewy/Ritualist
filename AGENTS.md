# Ritualist Development Notes

- Keep workflow parsing and execution cross-platform.
- Keep Windows UI Automation imports lazy and inside adapter methods.
- Do not add recipe actions that execute arbitrary Python, shell snippets, or JavaScript.
- Tests should use fake adapters and must not require a Windows desktop session.
- Use explicit confirmation gates for risky desktop actions.

## Release Validation Policy

- Use `.codex/skills/ritualist-release-validation/SKILL.md` for Ritualist
  release validation, packaged dogfood, release checklist updates, acceptance
  harness work, tag readiness, and v0.2/v0.3 release gates.
- Do not add arbitrary recipe-supplied Python or JavaScript, arbitrary QML/HTML
  components, coordinate clicks in product runtime, cloud sync, remote
  execution, marketplace behavior, gameplay automation, password/credential
  automation, true Windows shell replacement, taskbar hiding/kiosk mode, or
  risky/mutating primitives unless explicitly requested.
- Require structured evidence before marking a release check `PASS`.
- Mark ambiguous visual checks as `NEEDS_HUMAN_REVIEW`, not `PASS`.
- Do not create or push release tags unless the user explicitly asks in a
  separate message.
- Keep `RELEASE_CHECKLIST.md` honest and factual.
