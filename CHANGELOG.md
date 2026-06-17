# Changelog

## Unreleased

- No unreleased changes yet.

## v0.2.0-alpha.1

Canvas-era alpha release candidate focused on a customizable local command surface, typed components, deterministic planning, and safe visual sharing.

### Added

- Added a best-effort PySide6 visual trust overlay for GUI runs before window and desktop click actions.
- Added target previews for window focus/minimize/maximize actions and UI Automation bounds previews for `desktop.click_text` when available.
- Added a waiting HUD for long `window.wait` steps.
- Improved risky-action confirmation prompts with step, action, window, and target details.
- Added UI config options for action overlays, overlay duration, and desktop click previews.
- Added read-only assertion actions and optional assertion-only `preflight`/`verify` recipe sections.
- Added Capability Doctor v2 with action metadata, environment contracts, compatibility scoring, JSON output, capability checks, and missing-variable setup hints.
- Added Primitive Kernel metadata, policy/governance, read-only primitive families, deterministic intent plan preview, and generic target resolution.
- Added Canvas Foundation, Canvas Use Mode, Canvas Edit Mode foundation/UI MVP, performance modes, theme tokens, and Canvas runtime/performance smoke commands.
- Added Browser Clean Start options for Ritualist-managed profiles.
- Added explicit Watch Me drafting sessions with safe high-level signals, redaction, disabled drafts, and draft previews.
- Added local `.ritualistcanvas` and `.ritualisttheme` pack export/import with quarantine and visual-only validation.

### Safety Constraints

- Visual packs remain local and quarantined; Canvas packs reject action-triggering components, arbitrary component code, auto-run fields, remote image URLs, executable/script-like assets, and undeclared assets.
- Theme packs contain theme tokens only in this release and cannot contain recipes, actions, intents, components, or remembered approvals.
- Intent planning remains deterministic and inspectable; no AI/freeform planning is included.
- Browser clean-start handling does not click arbitrary page prompts or automate passwords/login credentials.
- Watch Me does not record keystrokes, passwords, screenshots, page contents, cookies, clipboard contents, or private/incognito tabs.

## v0.1.0-alpha.1

Initial alpha release of Ritualist as a local-first Windows personal workflow app.

### Added

- CLI workflow runner with `run`, `dry-run`, `validate`, `init`, `list`, `paths`, `runs`, and `show-run`.
- GUI runner for initializing the app, selecting recipes, running, dry-running, stopping, opening local folders, running Doctor, and viewing diagnostics.
- Packaged Windows one-folder app build using PyInstaller at `dist\Ritualist\Ritualist.exe`.
- Bundled `gaming_mode` sample recipe for opening persistent browser media, minimizing Chrome, launching Battle.net, selecting Diablo IV, and requiring confirmation before Play.
- `ritualist doctor` checks for recipe loadability, optional dependencies, OS support, browser profile creation, local app paths, and desktop click targets without launching apps, opening browsers, or clicking.
- `ritualist inspect-window` for Windows UI Automation window/label diagnostics.
- Per-run history under `runs/<timestamp>_<recipe_id>` with `run.json` and `steps.jsonl`.
- Stale running-run recovery that marks abandoned runs as `interrupted` while preserving step logs.
- Packaged-app diagnostics dialog with app version, PyInstaller status, local data paths, Python executable, current working directory, dependency status, and run status counts.
- Startup error logging for packaged GUI startup failures.

### Safety Constraints

- No coordinate-click action is implemented.
- `desktop.click_text` requires `window_title_contains`.
- Clicking visible text exactly equal to `Play` requires confirmation.
- Recipes expose only structured actions; arbitrary recipe-supplied Python or JavaScript is not supported.
- No AI features, macro recording, OCR, cloud sync, plugin systems, telemetry, remote execution, or gameplay automation are included.
