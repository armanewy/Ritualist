# Changelog

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
