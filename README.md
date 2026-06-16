# Ritualist

Ritualist is a local-first Windows desktop workflow automation app for repeatable personal routines. A ritual is a readable YAML recipe with explicit steps, validation, dry-run support, logs, and confirmation gates for risky actions.

This v0.1 implementation includes:

- CLI runner: `ritualist run recipe.yaml`
- Recipe initialization and discovery: `ritualist init`, `ritualist list`, `ritualist paths`
- Desktop diagnostics: `ritualist doctor`, `ritualist inspect-window`
- GUI launcher: `ritualist gui`
- YAML recipe validation and variable templating
- Persistent browser profiles and URL/media automation through Playwright
- Windows app/window/UI Automation adapters behind lazy imports
- Dry-run execution
- Step-by-step logging, per-run logs, and status
- Tests for the workflow engine using fake adapters

Release details for `v0.1.0-alpha.1` are in [CHANGELOG.md](CHANGELOG.md), [RELEASE_NOTES.md](RELEASE_NOTES.md), and [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md).

## Install

Core CLI and tests:

```powershell
python -m pip install -e ".[dev]"
```

Optional runtime pieces:

```powershell
python -m pip install -e ".[browser,gui,windows]"
python -m playwright install chromium
```

Windows-only actions raise clear errors if invoked on another OS or without the optional packages installed.

## Run A Ritual

```powershell
ritualist init
ritualist list
ritualist validate gaming_mode
ritualist doctor gaming_mode
ritualist doctor gaming_mode --json
ritualist dry-run gaming_mode
ritualist run gaming_mode --var youtube_url=https://www.youtube.com/watch?v=...
```

Recipe arguments can be either a recipe id from the user recipes directory or a direct YAML path.

Launch the GUI:

```powershell
ritualist gui
```

Launch the experimental Qt Quick Home recipe dashboard:

```powershell
ritualist home
```

Home loads installed recipes as cards, keeps slow recipe/run-history work off the UI thread, and can run, dry-run, doctor, edit, and open logs for selected recipes while preserving the same runtime confirmation gates as the CLI.

Launch the generated-data Home mock for UI development:

```powershell
ritualist home --mock
```

The Home mock uses bundled QML, 100+ generated cards, and coalesced fake status updates only; it does not run recipes, click windows, open browsers, or call runtime automation.

Inspect a real Windows UI Automation window before tuning click text:

```powershell
ritualist inspect-window "Battle.net" --control-type Button --limit 100
```

## First Real Trace

Use this sequence for the first Windows desktop trace of `gaming_mode`:

```powershell
python -m pip install -e ".[all,dev]"
python -m playwright install chromium
python -m ritualist init
python -m ritualist doctor gaming_mode
python -m ritualist dry-run gaming_mode
python -m ritualist inspect-window "Battle.net"
python -m ritualist run gaming_mode
```

`init` is safe to rerun. It creates missing directories, installs bundled samples if absent, and applies narrow sample migrations such as adding `keep_open: true` to older installed `gaming_mode` recipes.

The sample recipe sets `keep_open: true` on `browser.open`, so after the workflow reaches the browser step, the Ritualist CLI stays alive even if a later desktop step fails or the final Play confirmation is cancelled. Press `Ctrl+C` to exit the Ritualist CLI and let Playwright close its browser process.

## Test

Core tests do not require a desktop session:

```powershell
python -m pytest
```

Runtime smoke testing opens a local Playwright browser and a disposable native Windows window, then exercises the real browser, app, window, and UI Automation adapters:

```powershell
$env:RITUALIST_RUNTIME_SMOKE = "1"
python -m pytest tests\test_runtime_smoke.py
Remove-Item Env:\RITUALIST_RUNTIME_SMOKE
```

## Performance

See [PERFORMANCE.md](PERFORMANCE.md) for Ritualist's UI responsiveness contract, runtime event rules, and performance budgets. See [RUNTIME.md](RUNTIME.md) for Runtime v2 run states, step states, events, controls, waits, and GUI/Home integration rules.

### Performance Non-Negotiables

- Keep slow runtime, filesystem, adapter, and process work off the UI thread.
- Prefer event-driven Home updates over polling or broad synchronous reloads.
- Keep Pause and Stop controls responsive even when adapters are busy.
- Preserve local-first behavior and existing safety gates.
- Home card art must use cached local thumbnails, currently bounded to 512x288, with missing images falling back to static gradients.

## Recipe Format

```yaml
version: "0.1"
id: gaming_mode
name: Gaming Mode
home:
  category: Gaming
  card:
    title: Diablo IV Night
    subtitle: YouTube ambience + Battle.net
    image: ""
    accent: ""
variables:
  youtube_url: https://www.youtube.com/watch?v=dQw4w9WgXcQ
  battle_net_window: Battle.net
  battle_net_app: C:\Program Files (x86)\Battle.net\Battle.net Launcher.exe
environment:
  os:
    - windows
  required_capabilities:
    - playwright
    - windows_uia
    - app_launch
    - browser_control
    - window_management
  expected_windows:
    - title_contains: "{{ battle_net_window }}"
  expected_labels:
    - window_title_contains: "{{ battle_net_window }}"
      text: Play
  variable_hints:
    battle_net_app: Set this to your local Battle.net Launcher.exe path.
preflight:
  - name: Battle.net is installed
    action: assert.file_exists
    path: "${battle_net_app}"
steps:
  - name: Open video
    action: browser.open
    url: "{{ youtube_url }}"
    profile: gaming_mode
    keep_open: true

  - name: Loop and play video
    action: browser.media
    selector: video
    loop: true
    play: true

  - name: Ask before Play
    action: desktop.click_text
    text: Play
    window_title_contains: "{{ battle_net_window }}"
    requires_confirmation: true
verify:
  - name: Battle.net window is visible
    action: assert.window_exists
    title_contains: "{{ battle_net_window }}"
```

The recipe exposes only structured actions. It does not permit arbitrary Python or recipe-supplied JavaScript.

`environment` is optional and lets a recipe describe the machine it expects. Recipes without an `environment` section remain valid. Doctor uses environment contracts to report OS compatibility, required capabilities, expected windows/labels, and setup hints for missing variables. These contracts are portability metadata: they do not launch apps, open browsers, click controls, type input, or run recipe actions. Expected window and label checks are best-effort, read-only probes so a shared recipe can explain what should be visible on the target machine. Doctor summarizes compatibility as `compatible`, `compatible_with_warnings`, or `incompatible`, with machine-readable output available through `ritualist doctor <recipe> --json`.

Supported capability names include:

- `playwright`
- `windows_uia`
- `app_launch`
- `browser_control`
- `window_management`
- `keyboard_input`
- `file_read`
- `file_write`
- `registry_read`
- `registry_write`
- `process_inspection`

`preflight` and `verify` are optional assertion-only sections. They run before and after `steps`, respectively, and are intended for read-only checks:

- `assert.file_exists`
- `assert.path_exists`
- `assert.process_running`
- `assert.window_exists`
- `assert.window_text_visible`
- `assert.browser_text_visible`
- `assert.registry_value` on Windows

Assertions do not click, type, launch apps, or modify browser/page state. They pass with a short message or fail the run with a clear assertion error unless marked `optional: true`.

## Safety

- Coordinate clicks are not implemented in v0.1.
- `desktop.click_text` must be scoped with `window_title_contains`.
- The workflow stops on the first failed step unless that step has `optional: true`.
- Clicking visible text exactly equal to `Play` must include `requires_confirmation: true`.
- No telemetry, accounts, cloud backend, or remote execution are present.

## Visual Trust Layer

The GUI shows a best-effort transparent overlay before window focus/minimize/maximize and desktop click actions. For `desktop.click_text`, Ritualist previews the UI Automation element bounds when Windows exposes them, then keeps the existing confirmation gate for risky actions such as `Play`. Long `window.wait` steps show a small waiting HUD with elapsed seconds.

Overlay failures never fail the workflow. These settings live under `ui` in `config.yaml`:

```yaml
ui:
  show_action_overlay: true
  overlay_duration_ms: 700
  preview_desktop_clicks: true
```

Home categories are local config too. Recipes or cards with a category outside this list still appear safely by appending that category to the Home payload; blank categories appear under `Other`.

```yaml
home:
  categories:
    - Gaming
    - Media
    - Coding
    - News
    - Helpdesk
    - Settings
```

## Local Data

Use `ritualist paths` to inspect local directories. Ritualist creates:

- `config`
- `recipes`
- `logs`
- `runs`
- `browser-profiles`

Per-run logs are written to `runs/<timestamp>_<recipe_id>/run.json` and `steps.jsonl`. Browser URLs are redacted in run step messages; Ritualist does not log cookies, screenshots, page contents, passwords, or secrets.

Run history uses `success` for completed runs, `stopped` for cleanly cancelled or failed workflows, and `interrupted` when a previous Ritualist process exited before finalizing `run.json`. `ritualist runs` repairs stale `running` records automatically; use `ritualist runs --no-repair` to inspect raw statuses without reconciliation.

## Browser Lifecycle

Playwright owns the browser process it launches. When a CLI run exits, the browser it opened may close with the Playwright driver. For media workflows, set `keep_open: true` on `browser.open` or pass `ritualist run <recipe> --keep-alive`; Ritualist will keep the CLI process alive after execution until you press `Ctrl+C`. Recipe-level `keep_open: true` activates only after that browser step succeeds. The `--keep-alive` option keeps the CLI alive after execution regardless of workflow success, unless the run is a dry-run.

GUI/tray mode is the better long-running shape for media rituals because the app process naturally stays alive. Recipes still expose only structured browser actions such as `browser.open` and `browser.media`; arbitrary recipe-supplied JavaScript is not supported.

## Building A Local Windows App

Use a PyInstaller one-folder build for v0.1-alpha packaging. One-folder mode leaves the executable and its support files visible under `dist\Ritualist`, which makes missing data files and DLL issues easier to diagnose than a one-file bundle.

Build on Windows:

```powershell
python -m pip install -e ".[all,dev]"
python -m playwright install chromium
.\scripts\build_windows_app.ps1
```

The build script runs PyInstaller in one-folder/windowed mode and writes:

```text
dist\Ritualist\Ritualist.exe
```

`Ritualist.exe` launches the GUI through `ritualist.desktop_entry`; it does not run any ritual automatically. The normal development CLI stays available through `python -m ritualist` and the `ritualist` console command.

Bundled sample recipes are collected into the app bundle so **Initialize App** can still install `gaming_mode.yaml`. User data still belongs in the platform user-data directory shown by `ritualist paths`; recipes, logs, runs, and browser profiles should not be stored inside `dist\Ritualist`.

Manual packaged-build smoke checks:

```text
dist\Ritualist\Ritualist.exe opens the GUI
Initialize App works
Open Recipes Folder works
Dry Run selected recipe works with gaming_mode
Open Logs/Runs Folder works
python -m ritualist doctor gaming_mode still works from the development checkout
```

Playwright browser binaries and persistent profile behavior should be retested after packaging. Keep the one-folder build working before attempting a one-file executable.

### Packaged App Troubleshooting

If `dist\Ritualist\Ritualist.exe` opens but a workflow fails, use **About / Diagnostics** first. It shows whether the app is running from a PyInstaller bundle, where user data/logs/runs/browser profiles live, and whether PySide6, Playwright, and Windows UI Automation dependencies are importable. Use **Copy Diagnostics** when filing a bug diary entry.

If the Playwright browser is missing or browser steps fail immediately, rerun this from the development checkout before rebuilding:

```powershell
python -m playwright install chromium
.\scripts\build_windows_app.ps1
```

If Battle.net cannot launch, run **Doctor** for the selected recipe or `python -m ritualist doctor gaming_mode`. Missing-path errors mean the installed recipe variable/config points at a local file that does not exist on this machine.

If UI Automation labels are not found, use the development CLI to inspect the live window:

```powershell
python -m ritualist inspect-window "Battle.net" --control-type Button --limit 100
```

Then update `desktop.click_text` labels in the installed recipe. Ritualist still does not use coordinate clicks or gameplay automation.

Packaged startup failures are written to `startup-error.log` under the logs directory when possible. Normal app logs are under `logs`, and run details are under `runs`; the exact locations are shown in **About / Diagnostics** and by `python -m ritualist paths`.

## Diagnostics

`ritualist doctor <recipe-id-or-path>` validates a recipe without opening browsers, launching apps, clicking, typing, or running workflow actions. It checks optional dependency availability, OS support, browser profile creation, local app paths, `environment` contracts, and the window/text targets for `desktop.click_text`. Environment expected-window and expected-label checks use read-only inspection only; they are portability hints, not automation steps.

Machine-readable Doctor output is available with `--json` and keeps stable top-level fields for UI badges:

```json
{
  "schema_version": "doctor.v2",
  "recipe_id": "gaming_mode",
  "recipe_name": "Gaming Mode",
  "compatibility": {
    "status": "compatible_with_warnings",
    "errors_count": 0,
    "warnings_count": 1
  },
  "checks": [
    {
      "id": "expected_window",
      "category": "Windows/UI labels",
      "status": "warning",
      "message": "expected window not currently visible: Battle.net",
      "details": {
        "target": "Battle.net"
      }
    }
  ],
  "capabilities": [],
  "variables": [],
  "actions": [],
  "environment": {
    "current_os": "windows",
    "expected_os": ["windows"],
    "required_capabilities": ["playwright", "windows_uia"],
    "expected_windows": [],
    "expected_labels": [],
    "variable_hints": {}
  }
}
```

`ritualist inspect-window <title-contains>` is Windows-only and prints matching window titles plus visible descendant labels. Use it to discover the exact labels exposed to UI Automation before editing `desktop.click_text` steps.
