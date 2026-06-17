# Ritualist

Ritualist is a local-first Windows desktop workflow automation app for repeatable personal routines. A ritual is a readable YAML recipe with explicit steps, validation, dry-run support, logs, and confirmation gates for risky actions.

This alpha implementation includes:

- CLI runner: `ritualist run recipe.yaml`
- Recipe initialization and discovery: `ritualist init`, `ritualist list`, `ritualist paths`
- Portable recipe packs: `ritualist pack export`, `ritualist pack import`, `ritualist pack list-imports`, `ritualist pack enable`
- Desktop diagnostics: `ritualist doctor`, `ritualist inspect-window`
- GUI launcher: `ritualist gui`
- Canvas schema and component kernel: `ritualist canvas list`, `ritualist canvas validate`
- YAML recipe validation and variable templating
- Persistent browser profiles and URL/media automation through Playwright
- Windows app/window/UI Automation adapters behind lazy imports
- Dry-run execution
- Step-by-step logging, per-run logs, and status
- Tests for the workflow engine using fake adapters

Release-candidate details for `v0.2.0-alpha.1` are in [CHANGELOG.md](CHANGELOG.md), [RELEASE_NOTES.md](RELEASE_NOTES.md), and [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md). Future risky primitive work is tracked in [docs/roadmap.md](docs/roadmap.md) and must follow [docs/mutating_risky_primitives_design.md](docs/mutating_risky_primitives_design.md).

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

Export and import a portable recipe pack:

```powershell
ritualist pack export gaming_mode --out gaming_mode.ritualistpack
ritualist pack import .\gaming_mode.ritualistpack
ritualist pack list-imports
ritualist doctor <quarantined-recipe-path>
ritualist dry-run <quarantined-recipe-path>
```

Pack export writes a `.ritualistpack` zip containing `manifest.yaml`, `recipe.yaml`, and
optionally `README.md` when `--readme` points at an explicit UTF-8 text file. Pack import
validates the archive and copies it into disabled quarantine storage under local app data. It
does not enable, run, launch, click, type, open browsers, or contact any remote service. Packs
containing UI, app-launch, or browser-control actions remain blocked from enable by the current imported-pack policy and
should be reviewed with Doctor and dry-run from quarantine. Enable is only available for actions
allowed by the imported-pack policy, and still does not run recipes. Logs, run history, browser
profiles, cookies, screenshots, secrets, local paths, and user data are never included in exported
packs.

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

## Watch Me Drafts

Watch Me is an explicit draft helper for local setup sessions. Start it only when
you want Ritualist to observe high-level, safe signals, then stop it and create a
disabled draft:

```powershell
python -m ritualist watch-me start
python -m ritualist watch-me stop <session-id>
python -m ritualist watch-me create-draft <session-id>
```

Watch Me may record process/app names, foreground window titles, window bounds,
monitor layout, timestamps, and redacted browser URLs from Ritualist-managed
context. It does not record keystrokes, passwords, screenshots, OCR, page
contents, cookies, tokens, clipboard contents, or private/incognito tabs. Drafts
are written under the local Watch Me session folder, not installed into recipes;
review the draft, run Doctor, and dry-run before saving it as a real ritual.

## Canvas Foundation

Canvas is the next Ritualist product layer: a typed, customizable desktop command surface that Home can gradually render. It is not a true Windows shell replacement, does not hide the taskbar, and does not allow arbitrary QML, JavaScript, HTML, Python, shell snippets, or remote widgets.

Canvas documents are local YAML layouts made of native Ritualist components bound to recipes, intents, targets, runtime state, and static display data. Canvas validation is side-effect free; it does not run recipes, launch apps, click, type, open browsers, call UI Automation, or execute bindings.

```powershell
python -m ritualist canvas init
python -m ritualist canvas list
python -m ritualist canvas validate gaming_desktop
python -m ritualist canvas show gaming_desktop --json
python -m ritualist perf canvas-model --mock-components 300 --json
```

See [docs/canvas.md](docs/canvas.md) for the schema, component registry, binding model, pack-domain separation, and performance rules.

## Starter Rooms

Rooms are the user-facing name for curated Canvas templates. A Room is a Canvas
plus theme, components, safe bindings, and validation; it is not a Windows user
account, sandbox, virtual desktop, shell replacement, or automation marketplace.

```powershell
python -m ritualist room list --json
python -m ritualist room show minimal --json
```

Starter Rooms currently map to bundled Canvas templates: Minimal, Gaming,
Project, Focus, and Helpdesk. See [docs/ROOMS.md](docs/ROOMS.md) for the Room
language and the Canvas mapping.

## Home Alpha Dogfood

Before a Home-focused alpha build, use the packaged app and development checkout to verify:

- Launch `dist\Ritualist\Ritualist.exe`.
- Open Home.
- Run mock Home with `python -m ritualist home --mock`.
- Run `gaming_mode` from Home.
- Pause and resume a visible `window.wait` action.
- Stop an active ritual from Home.
- Confirm interrupted recovery after hard-killing the packaged app during a run.
- Inspect logs from Home and confirm `run.json` and `steps.jsonl` are present.

During this pass, confirm Home stays responsive while cards, run history, thumbnails, runtime status, Pause/Resume, Stop, logs, and diagnostics update. Slow recipe, filesystem, adapter, thumbnail, and run-history work must stay off the GUI thread. See [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) for the complete Home dogfood and performance checklist.

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

`init` is safe to rerun. It creates missing directories, installs the default bundled `gaming_mode` sample if absent, and applies narrow sample migrations such as adding `keep_open: true` and browser clean-start options to older installed `gaming_mode` recipes.

The sample recipe sets `keep_open: true` on `browser.open`, so after the workflow reaches the browser step, the Ritualist CLI stays alive even if a later desktop step fails or the final Play confirmation is cancelled. Press `Ctrl+C` to exit the Ritualist CLI and let Playwright close its browser process.

## Starter Workspace Templates

Bundled starter templates live under `ritualist\sample_recipes` for local editing and review:

- `coding_mode.yaml`: editor, project directory, documentation, and tracker.
- `meeting_mode.yaml`: calendar, notes, meeting app, and meeting lobby.
- `research_mode.yaml`: notes app, research workspace, and source URLs.
- `streaming_mode.yaml`: streaming app, dashboard, and chat without starting a broadcast.
- `support_triage_workspace.yaml`: ticket queue, knowledge base, service status, and local notes.
- `meeting_audio_troubleshooting.yaml`: audio checklist, meeting service status, device help, and meeting app.
- `vendor_app_configuration_placeholder.yaml`: vendor app, approved runbook, change record, and status page.
- `collect_basic_diagnostics.yaml`: system information, operating system guide, network status, and device inventory.
- `lab_classroom_setup.yaml`: class schedule, roster, learning platform, and classroom materials.
- `browser_admin_console_workspace.yaml`: admin console, monitoring console, audit page, and runbook.

These templates are samples only. `ritualist init` still installs only `gaming_mode.yaml`; the workspace and helpdesk templates are not run or imported automatically. Each template uses variables for local app paths and URLs, includes confirmation before opening its workspace or runbook surfaces, avoids passwords and destructive actions, and uses only structured recipe actions.

See `docs\helpdesk_templates.md` for helpdesk/runbook template notes.

Validate and dry-run a template before using it:

```powershell
python -m ritualist validate .\ritualist\sample_recipes\coding_mode.yaml
python -m ritualist dry-run .\ritualist\sample_recipes\coding_mode.yaml
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

## Performance

See [PERFORMANCE.md](PERFORMANCE.md) for Ritualist's UI responsiveness contract, runtime event rules, and performance budgets. See [RUNTIME.md](RUNTIME.md) for Runtime v2 run states, step states, events, controls, waits, and GUI/Home integration rules.

Home model performance smoke checks are advisory only; they print warnings
instead of failing on noisy CI wall-clock timing:

```powershell
python -m ritualist perf home-model --mock-cards 100 --json
python -m ritualist perf home-model --mock-cards 300 --json
```

Helpdesk-oriented recipes must also follow the local evidence policy in
[docs/helpdesk_privacy_evidence.md](docs/helpdesk_privacy_evidence.md): default
evidence is limited to timestamps, action names, statuses, window titles, and
operator notes; passwords, cookies, page contents, screenshots, and clipboard
contents are forbidden by default.

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

Recipes can still be edited directly as YAML. The backend recipe builder uses the same validation path before saving GUI-authored edits, then writes YAML with the current YAML library. That rewrite may not preserve comments or original formatting, so keep notes outside edited recipes if they must survive a GUI save.

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

- Coordinate clicks are not implemented.
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
- `imported-packs`
- `canvases`
- `imported-canvas-packs`
- `themes`
- `imported-theme-packs`
- `logs`
- `runs`
- `browser-profiles`

Per-run logs are written to `runs/<timestamp>_<recipe_id>/run.json` and `steps.jsonl`. Add user-entered operator notes during or after a run with `ritualist note-run <run-id-or-path> "note text"`; notes are stored in the run folder as `operator_notes.jsonl` and are shown by `ritualist show-run`. Browser URLs are redacted in run step messages; Ritualist does not log cookies, screenshots, page contents, passwords, or secrets.

Helpdesk summaries use the same privacy boundary. They may include timestamps,
action names, statuses, scoped window titles, and operator notes, but default
templates must not capture passwords, cookies, page contents, screenshots, or
clipboard contents.

Run history uses `success` for completed runs, `stopped` for cleanly cancelled or failed workflows, and `interrupted` when a previous Ritualist process exited before finalizing `run.json`. `ritualist runs` repairs stale `running` records automatically; use `ritualist runs --no-repair` to inspect raw statuses without reconciliation.

## Browser Lifecycle

Playwright owns the browser process it launches. When a CLI run exits, the browser it opened may close with the Playwright driver. For media workflows, set `keep_open: true` on `browser.open` or pass `ritualist run <recipe> --keep-alive`; Ritualist will keep the CLI process alive after execution until you press `Ctrl+C`. Recipe-level `keep_open: true` activates only after that browser step succeeds. The `--keep-alive` option keeps the CLI alive after execution regardless of workflow success, unless the run is a dry-run.

GUI/tray mode is the better long-running shape for media rituals because the app process naturally stays alive. Recipes still expose only structured browser actions such as `browser.open` and `browser.media`; arbitrary recipe-supplied JavaScript is not supported.

`browser.open` uses Ritualist-managed browser profile folders under the local
`browser-profiles` directory. Set `clean_start: true` to launch with safe
Chromium startup flags that reduce first-run and session-restore prompts without
deleting profile data. `dismiss_restore_prompt: true` is accepted for forward
compatibility, but this release treats it as a safe no-op unless Ritualist has a browser
UI-scoped mechanism available. Ritualist does not use webpage text or buttons to
dismiss Chrome restore prompts, because page content can imitate browser prompts.
`use_dedicated_profile: false` is rejected so Ritualist cannot silently
operate on a user's normal browser profile.

## Structured Browser Runbooks

Ritualist supports a narrow browser runbook surface for pages it opened through
`browser.open`. These actions operate on the current Ritualist-managed page:

- `browser.wait_text`
- `browser.wait_title`
- `browser.wait_url`
- `browser.element_visible`
- `browser.click_text`
- `browser.click_role`
- `browser.click_test_id`

Browser waits are read-only and can use `timeout_seconds` and `on_timeout`.
Browser clicks are structured and reviewable: they target visible text, ARIA
role plus `accessible_name`, or test id. Ritualist does not support arbitrary
recipe-supplied JavaScript, browser clicking by raw CSS selector, password
typing, credential storage, or Google/YouTube login automation. Click targets
such as `Buy`, `Purchase`, `Pay`, `Send`, `Delete`, `Submit`, and `Confirm`
must include `requires_confirmation: true`. Browser click actions remain blocked
by default for imported recipe packs.

Use persistent profiles plus an operator handoff for sign-in:

```yaml
steps:
  - action: browser.open
    url: https://example.test/dashboard
    profile: work_dashboard
    keep_open: true
    clean_start: true
    dismiss_restore_prompt: true
    use_dedicated_profile: true

  - action: browser.wait_text
    text: Sign in
    optional: true
    timeout_seconds: 5

  - action: human.prompt
    prompt: Sign in manually if the page asks, then return to Ritualist.

  - action: wait.for_user
    prompt: Continue after the browser is signed in.

  - action: browser.wait_text
    text: Dashboard
    timeout_seconds: 30
```

This pattern keeps credentials with the user and the browser profile. Ritualist
only waits for structured page state or clicks explicit, reviewable controls.

## Building A Local Windows App

Use a PyInstaller one-folder build for alpha packaging. One-folder mode leaves the executable and its support files visible under `dist\Ritualist`, which makes missing data files and DLL issues easier to diagnose than a one-file bundle.

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

`Ritualist.exe` launches Home through `ritualist.desktop_entry`; it does not run any ritual automatically. The classic GUI remains available with `dist\Ritualist\Ritualist.exe --classic-gui` or `dist\Ritualist\Ritualist.exe --gui`. The normal development CLI stays available through `python -m ritualist` and the `ritualist` console command.

Home QML files and bundled sample recipes are collected into the app bundle so Home can load and **Initialize App** in the classic GUI can still install `gaming_mode.yaml`; starter workspace templates remain available as packaged samples. User data still belongs in the platform user-data directory shown by `ritualist paths`; recipes, logs, runs, and browser profiles should not be stored inside `dist\Ritualist`.

Manual packaged-build smoke checks:

```text
Dev CLI: pytest, compileall, init, Doctor JSON, dry-run, actions JSON, perf fake-run, perf home-model 100/300, and pack export/import/list.
Home/QML: python -m ritualist home --help, python -m ritualist home --mock, and offscreen optional-dependency tests where available.
Packaged one-folder: build dist\Ritualist\Ritualist.exe, launch Home, launch --classic-gui, open diagnostics, initialize, refresh recipes, load installed recipes, dry-run gaming_mode, and open logs/runs.
Real Windows UIA/Battle.net: run gaming_mode from Home, pause/resume a wait action, stop an active ritual, hard-kill during a run, relaunch, and verify interrupted repair.
```

Playwright browser binaries and persistent profile behavior should be retested after packaging. Keep the one-folder build working before attempting a one-file executable.

### Packaged App Troubleshooting

If `dist\Ritualist\Ritualist.exe` opens but a workflow fails, launch `dist\Ritualist\Ritualist.exe --classic-gui` and use **About / Diagnostics** first. It shows whether the app is running from a PyInstaller bundle, where user data/logs/runs/browser profiles live, and whether PySide6, Playwright, and Windows UI Automation dependencies are importable. Use **Copy Diagnostics** when filing a bug diary entry.

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
