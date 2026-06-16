# Ritualist v0.1.0-alpha.1 Release Checklist

Use this checklist for a local v0.1.0-alpha.1 release build.

## Build

- [ ] Confirm clean git status.
- [ ] Run `python -m pytest -q`.
- [ ] Run `python -m pip install -e ".[dev]"`.
- [ ] Run `python -m ritualist --help`.
- [ ] Run `python -m pip install -e ".[all,dev]"`.
- [ ] Run `python -m playwright install chromium`.
- [ ] Run `.\scripts\build_windows_app.ps1`.

## Dev CLI / Home / Pack Dogfood Commands

Run this block from the development checkout before packaging. It does not run
the real runtime smoke tests unless `RITUALIST_RUNTIME_SMOKE=1` is set.

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
$env:PYTHONFAULTHANDLER = "1"
python -m pip install -e ".[all,dev]"
python -m playwright install chromium
python -m pytest -q
python -m compileall -q ritualist tests
python -m ritualist init
python -m ritualist doctor gaming_mode --json --no-strict
python -m ritualist dry-run gaming_mode
python -m ritualist actions --json
python -m ritualist home --help
python -m ritualist pack --help
python -m ritualist perf fake-run gaming_mode --json
python -m ritualist perf home-model --mock-cards 100 --json
python -m ritualist perf home-model --mock-cards 300 --json
$packDir = Join-Path $env:TEMP "ritualist-pack-dogfood"
New-Item -ItemType Directory -Force -Path $packDir | Out-Null
$packPath = Join-Path $packDir "gaming_mode.ritualistpack"
python -m ritualist pack export gaming_mode --out $packPath
python -m ritualist pack import $packPath
python -m ritualist pack list-imports
Remove-Item Env:\QT_QPA_PLATFORM -ErrorAction SilentlyContinue
Remove-Item Env:\PYTHONFAULTHANDLER -ErrorAction SilentlyContinue
```

On Linux CI, keep `QT_QPA_PLATFORM=offscreen` for optional GUI/Home tests.

## Dogfood Findings - 2026-06-16

Automated Windows development-checkout checks passed:

- `python -m pip install -e ".[all,dev]"`.
- `python -m playwright install chromium`.
- `QT_QPA_PLATFORM=offscreen PYTHONFAULTHANDLER=1 python -m pytest -q`:
  `402 passed, 1 skipped`.
- `python -m compileall -q ritualist tests`.
- `python -m ritualist init`.
- `python -m ritualist doctor gaming_mode --json --no-strict`.
- `python -m ritualist dry-run gaming_mode`.
- `python -m ritualist perf home-model --mock-cards 100 --json`:
  100 cards, 6 categories, 10.915 ms, no warnings.
- `python -m ritualist perf home-model --mock-cards 300 --json`:
  300 cards, 6 categories, 12.545 ms, no warnings.
- `python -m ritualist pack export gaming_mode --out <temp>`.
- `python -m ritualist pack import <temp>`.
- `.\scripts\build_windows_app.ps1`.

Packaged app observations:

- `dist\Ritualist\Ritualist.exe` launched a `Ritualist Home` window.
- Cold packaged Home launch was observed between about 1.0 and 2.6 seconds.
- Home rendered installed recipes after a QML fix that selects the first populated
  category instead of leaving an empty default category selected.
- `dist\Ritualist\Ritualist.exe --classic-gui` launched and showed installed
  recipe, Run, Dry Run, Doctor, Pause, Resume, Stop, Close Browser, folder, and
  About / Diagnostics controls.
- About / Diagnostics was hardened to keep a persistent non-modal dialog and
  report construction failures instead of silently dropping the request.
- PyInstaller build completed, with Conda-environment DLL warnings recorded in
  `build\Ritualist\warn-Ritualist.txt`; no packaged startup failure was observed.

Manual Windows-only checks still required:

- Synthetic mouse/UIA input from this Codex desktop session could not reliably
  activate packaged Qt/QML buttons, so Home Dry Run, Home Run, Pause/Resume/Stop,
  Play-decline, Diagnostics click-through, and hard-kill interrupted repair must
  still be verified by a human on the packaged desktop.
- Category switch, card hover/focus, visible jitter, and CPU/GPU feel need a human
  pass in the packaged app because synthetic input did not exercise them.
- Real Battle.net/UIA trace remains manual: confirm YouTube, Battle.net launch,
  Diablo IV selection, Play confirmation decline, stopped status, and next-launch
  interrupted repair after hard kill.

## Packaged App Smoke

- [ ] Launch `dist\Ritualist\Ritualist.exe` and confirm Home opens.
- [ ] Launch `dist\Ritualist\Ritualist.exe --classic-gui`.
- [ ] Open About / Diagnostics.
- [ ] Confirm diagnostics reports version `0.1.0-alpha.1`.
- [ ] Copy diagnostics and save it with the release notes.
- [ ] Click Initialize App.
- [ ] Click Refresh Recipes.
- [ ] Confirm Home loads installed recipes after initialization.
- [ ] Select `gaming_mode`.
- [ ] Click Doctor and confirm checks are printed.
- [ ] Click Dry Run for `gaming_mode` and confirm it completes.

## Home Alpha Dogfood

- [ ] Launch the packaged app with `dist\Ritualist\Ritualist.exe`.
- [ ] Confirm Home opens by default.
- [ ] Launch `dist\Ritualist\Ritualist.exe --classic-gui` and open diagnostics.
- [ ] Run mock Home with `python -m ritualist home --mock`.
- [ ] Run `gaming_mode` from Home.
- [ ] Pause a visible `window.wait` action from Home, then resume it.
- [ ] Stop the active ritual from Home.
- [ ] Confirm interrupted recovery by hard-killing the packaged app during a run, relaunching it, and checking that the abandoned run is marked `interrupted`.
- [ ] Inspect logs from Home and confirm the matching run folder contains `run.json` and `steps.jsonl`.

## Home Performance Checklist

- [ ] Home opens without blocking while recipes, run history, and card assets load.
- [ ] Card navigation, hover/focus, and selection remain responsive during a running ritual.
- [ ] Runtime status updates arrive through events or queued state changes, not broad synchronous reloads.
- [ ] Pause, Resume, and Stop respond promptly during waits and adapter activity.
- [ ] Mock Home handles 100+ generated cards and coalesced fake status updates without visible stutter.
- [ ] Opening logs or diagnostics does not freeze Home while filesystem paths are resolved.
- [ ] No Windows UI Automation scan, Playwright call, YAML directory scan, run-log repair, or thumbnail decode runs on the GUI thread.

## Real Trace

- [ ] Click Run for `gaming_mode`.
- [ ] Confirm YouTube opens and loops.
- [ ] Confirm Battle.net launches.
- [ ] Confirm Diablo IV is selected.
- [ ] Decline Play.
- [ ] Confirm the latest run status is `stopped`.
- [ ] Confirm the final step is `cancelled | Ask before clicking Play | user declined confirmation`.

## Stale-Run Recovery

- [ ] Start `gaming_mode` from the packaged app.
- [ ] Wait until the Play confirmation is visible.
- [ ] Kill `Ritualist.exe` from Task Manager or PowerShell.
- [ ] Relaunch `dist\Ritualist\Ritualist.exe`.
- [ ] Confirm Home startup or Refresh reconciles the abandoned run.
- [ ] Run `python -m ritualist runs` and confirm the abandoned run is `interrupted`.
- [ ] Run `python -m ritualist show-run <run-id>` and confirm `final_message` explains that Ritualist exited before finalizing the run.

## Release Artifacts

- [ ] Keep `dist\Ritualist` as the release folder.
- [ ] Include `README.md`, `CHANGELOG.md`, `RELEASE_NOTES.md`, and this checklist.
- [ ] Include known limitations from `RELEASE_NOTES.md`.
- [ ] Do not include `build`, `.pytest_cache`, `__pycache__`, or `Ritualist.spec`.
