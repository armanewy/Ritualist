# Helpdesk Privacy And Evidence Policy

Setpiece helpdesk workflows are local-first support runbooks. They may help an
operator collect a narrow activity trail, but they must not turn templates into
screen recorders, browser scrapers, secret collectors, or remote command
channels.

This policy applies to bundled helpdesk templates, shared recipe packs, runtime
events, run logs, and any UI that summarizes helpdesk runs.

## Allowed Evidence

Default helpdesk evidence is limited to operational metadata that explains what
the local operator intentionally ran:

- Timestamps, such as run start, step start, confirmation, and finish times.
- Action names, such as `browser.open`, `assert.window_exists`, or
  `confirm.ask`.
- Statuses, such as `running`, `waiting`, `confirming`, `success`, `failed`,
  `stopped`, or `interrupted`.
- Window titles from scoped window checks or UI Automation probes.
- Operator notes typed intentionally by the local operator.

Allowed evidence should stay structured, concise, and redacted when displayed in
logs, runtime events, Home cards, or helpdesk summaries. It should be collected
from runtime events, run records, explicit operator input, or read-only adapter
checks running off the GUI thread.

## Forbidden Default Evidence

Bundled templates and default helpdesk flows must not capture, store, summarize,
or export these by default:

- Passwords.
- Cookies.
- Page contents.
- Screenshots.
- Clipboard contents.

This includes direct collection and indirect collection through recipe-supplied
code, browser scraping, OCR, screen capture, clipboard reads, cookie export, or
full page dumps. Setpiece does not support arbitrary recipe-supplied Python,
shell snippets, JavaScript, OCR, coordinate clicks, macro recording, cloud sync,
remote execution, or network command channels.

## Template Rules

Helpdesk templates must remain reviewable YAML made of structured actions only.
They must not use evidence-capture actions for screenshots, clipboard contents,
cookies, page contents, passwords, or similar sensitive material.

Templates may ask the operator for confirmation and may include prompts for
operator notes. Imported or shared recipes must remain quarantined/disabled until
the local user explicitly reviews and enables them, and enabling a recipe must
not run it automatically.

## Runtime And UI Rules

Evidence handling must preserve the Runtime v2 responsiveness contract:

- Slow checks and adapter calls run in runtime workers, never on the GUI thread.
- GUI and Home views consume events and run summaries; they do not perform
  synchronous scans or desktop/browser probes.
- Runtime events stay small and must not include secrets, cookies, page
  contents, screenshots, clipboard contents, full URLs with tokens, or broad
  environment dumps.
- Confirmation gates remain explicit for risky desktop actions.

When a future feature needs broader evidence, it must be designed as a separate
local-only, explicit, user-reviewed capability with policy and lint coverage
updated before templates can use it.
