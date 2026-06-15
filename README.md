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
ritualist dry-run gaming_mode
ritualist run gaming_mode --var youtube_url=https://www.youtube.com/watch?v=...
```

Recipe arguments can be either a recipe id from the user recipes directory or a direct YAML path.

Launch the GUI:

```powershell
ritualist gui
```

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

## Recipe Format

```yaml
version: "0.1"
id: gaming_mode
name: Gaming Mode
variables:
  youtube_url: https://www.youtube.com/watch?v=dQw4w9WgXcQ
  battle_net_window: Battle.net
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
```

The recipe exposes only structured actions. It does not permit arbitrary Python or recipe-supplied JavaScript.

## Safety

- Coordinate clicks are not implemented in v0.1.
- `desktop.click_text` must be scoped with `window_title_contains`.
- The workflow stops on the first failed step unless that step has `optional: true`.
- Clicking visible text exactly equal to `Play` must include `requires_confirmation: true`.
- No telemetry, accounts, cloud backend, or remote execution are present.

## Local Data

Use `ritualist paths` to inspect local directories. Ritualist creates:

- `config`
- `recipes`
- `logs`
- `runs`
- `browser-profiles`

Per-run logs are written to `runs/<timestamp>_<recipe_id>/run.json` and `steps.jsonl`. Browser URLs are redacted in run step messages; Ritualist does not log cookies, screenshots, page contents, passwords, or secrets.

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

`ritualist doctor <recipe-id-or-path>` validates a recipe without opening browsers, launching apps, or clicking. It checks optional dependency availability, OS support, browser profile creation, local app paths, and the window/text targets for `desktop.click_text`.

`ritualist inspect-window <title-contains>` is Windows-only and prints matching window titles plus visible descendant labels. Use it to discover the exact labels exposed to UI Automation before editing `desktop.click_text` steps.
