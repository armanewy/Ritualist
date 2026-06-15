# Ritualist

Ritualist is a local-first Windows desktop workflow automation app for repeatable personal routines. A ritual is a readable YAML recipe with explicit steps, validation, dry-run support, logs, and confirmation gates for risky actions.

This v0.1 implementation includes:

- CLI runner: `ritualist run recipe.yaml`
- GUI launcher: `ritualist gui`
- YAML recipe validation and variable templating
- Browser URL/media automation through Playwright
- Windows app/window/UI Automation adapters behind lazy imports
- Dry-run execution
- Step-by-step logging and status
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
ritualist validate ritualist\sample_recipes\gaming_mode.yaml
ritualist run ritualist\sample_recipes\gaming_mode.yaml --dry-run
ritualist run ritualist\sample_recipes\gaming_mode.yaml --var youtube_url=https://www.youtube.com/watch?v=...
```

Launch the GUI:

```powershell
ritualist gui
```

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
name: Gaming Mode
variables:
  youtube_url: https://www.youtube.com/watch?v=dQw4w9WgXcQ
steps:
  - name: Open video
    action: browser.open
    url: "{{ youtube_url }}"

  - name: Loop and play video
    action: browser.media
    selector: video
    loop: true
    play: true

  - name: Ask before Play
    action: desktop.click_text
    text: Play
    requires_confirmation: true
```

The recipe exposes only structured actions. It does not permit arbitrary Python or recipe-supplied JavaScript.

## Safety

- Coordinate clicks are not implemented in v0.1.
- The workflow stops on the first failed step unless that step has `optional: true`.
- Clicking visible text exactly equal to `Play` must include `requires_confirmation: true`.
- No telemetry, accounts, cloud backend, or remote execution are present.
