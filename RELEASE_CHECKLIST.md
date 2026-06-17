# Ritualist v0.2.0-alpha.1 Release Checklist

Use this checklist for the local v0.2.0-alpha.1 Canvas-era release candidate.

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

## Historical v0.1.0-alpha.1 Release Candidate Validation - 2026-06-16

Validation commit: `2d83b66`.

Repository and environment:

- `git status`: clean on `main`, up to date with `origin/main`.
- `git pull --ff-only`: already up to date.
- Project version confirmed in `pyproject.toml`: `0.1.0-alpha.1`.
- `python -m pip install -e ".[all,dev]"`: passed.
- `python -m playwright install chromium`: passed.
- `QT_QPA_PLATFORM=offscreen PYTHONFAULTHANDLER=1 python -m pytest -q`:
  `402 passed, 1 skipped`.
- `python -m compileall -q ritualist tests`: passed.

CLI validation:

- `python -m ritualist init`: passed; app data was already up to date.
- `python -m ritualist doctor gaming_mode --json --no-strict`: passed;
  compatibility status `compatible`, `errors_count: 0`, `warnings_count: 0`.
- `python -m ritualist dry-run gaming_mode`: passed; final run state `success`,
  keep-open inactive.
- `python -m ritualist actions --json`: passed.
- `python -m ritualist perf fake-run gaming_mode --json`: passed in 18.219 ms,
  7/7 fake steps successful.
- `python -m ritualist perf home-model --mock-cards 100 --json`: passed in
  12.827 ms, 100 cards, 6 categories, no warnings.
- `python -m ritualist perf home-model --mock-cards 300 --json`: passed in
  13.425 ms, 300 cards, 6 categories, no warnings.

Packaged build validation:

- `.\scripts\build_windows_app.ps1`: passed and built
  `dist\Ritualist\Ritualist.exe`.
- Verified `dist\Ritualist\Ritualist.exe` exists.
- Verified bundled sample recipe exists:
  `dist\Ritualist\_internal\ritualist\sample_recipes\gaming_mode.yaml`.
- Verified bundled Home QML exists:
  `dist\Ritualist\_internal\ritualist\home\qml\Home.qml`.
- Brief packaged launch created a `Ritualist Home` window.
- Existing old `startup-error.log` was not modified by the normal packaged launch.
- PyInstaller still reports Conda-environment warnings in
  `build\Ritualist\warn-Ritualist.txt`, including optional/platform-specific
  missing modules and MKL/SYCL/MSMPI-related DLL warnings. No startup failure was
  observed from those warnings in this validation.

Manual release gates:

- Not passed in this validation. Per the release hard rule, no manual packaged
  Home checks are marked complete because they require real desktop input.
- Synthetic launch/process inspection confirmed Home starts, but it does not
  satisfy the real-input checks for Home buttons, category switching, hover/focus
  feel, Doctor, Dry Run, Run, Pause, Resume, Stop, Diagnostics copy, logs/runs
  folder opening, real `gaming_mode` trace, Play decline, or hard-kill repair.
- Release tag `v0.1.0-alpha.1` was not created. Tagging is blocked until a human
  completes the manual packaged Home and real `gaming_mode` checks below.

## Dogfood Findings - 2026-06-16

Packaged Home confirmation trust regression:

- Manual packaged Home testing on 2026-06-16 found the Play confirmation still
  appeared as the inline QML panel behind the Battle.net / Diablo screen. This
  was treated as a release blocker because a risky desktop action confirmation
  must remain visible above the target app.
- Fix applied for the next rebuild: Home now creates a `QApplication` for widget
  support, packaged builds explicitly include `ritualist.home.confirmation`, the
  Qt confirmation dialog is promoted with topmost/foreground Win32 calls, and a
  topmost Win32 MessageBox fallback is available if Qt dialog presentation fails.
- Post-fix validation: `QT_QPA_PLATFORM=offscreen PYTHONFAULTHANDLER=1 python -m
  pytest -q` passed with `455 passed, 1 skipped`; `python -m compileall -q
  ritualist tests`, `python -m ritualist dry-run gaming_mode`, `python -m
  ritualist actions --json`, `python -m ritualist doctor gaming_mode --json
  --no-strict`, and `python -m ritualist perf fake-run gaming_mode --json`
  passed; `.\scripts\build_windows_app.ps1` rebuilt `dist\Ritualist\Ritualist.exe`;
  a brief packaged launch smoke opened a `Ritualist Home` window.
- Re-test requirement: after rebuilding `dist\Ritualist\Ritualist.exe`, start
  `gaming_mode` from Home and verify the Play confirmation appears as a separate
  top-level/native dialog above Battle.net, not as the inline Home panel.

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

## Canvas Use Mode Packaged Dogfood - 2026-06-17

Validation commit: `2b87489` plus local packaged Canvas fixes.

Repository and environment:

- `git status`: clean before Prompt 1 changes.
- `git pull --ff-only`: already up to date.
- `python -m pip install -e ".[all,dev]"`: passed.
- `python -m playwright install chromium`: passed.
- `QT_QPA_PLATFORM=offscreen PYTHONFAULTHANDLER=1 python -m pytest -q`:
  `628 passed, 1 skipped`.
- `python -m compileall -q ritualist tests`: passed.
- `python -m ritualist canvas validate gaming_desktop`: passed.
- `python -m ritualist canvas runtime gaming_desktop --json`: passed.
- `python -m ritualist canvas action gaming_desktop diablo_night doctor --dry-run --json`: passed.
- `python -m ritualist perf canvas-use --mock-components 100 --json`: passed.
- `python -m ritualist perf canvas-use --mock-components 300 --json`: passed.

Release-blocking packaged Canvas issue found and fixed:

- The Windows build script collected Home QML and sample recipes, but not Canvas
  QML, Canvas submodules, or bundled sample canvases. Packaged Canvas Use Mode
  could not be treated as release-ready without those bundled resources.
- Fix applied: `scripts\build_windows_app.ps1` now collects `ritualist.canvas`,
  `ritualist.canvas.qml`, and `ritualist.sample_canvases`.
- Fix applied: `Ritualist.exe --canvas [canvas-id-or-path]` and
  `Ritualist.exe --canvas-use [canvas-id-or-path]` launch packaged Canvas Use
  Mode. Home remains the default, and `--classic-gui` remains available.
- Packaging tests now assert Canvas QML/sample-canvas collection and packaged
  Canvas launch routing.

Packaged build validation:

- `.\scripts\build_windows_app.ps1`: passed and built
  `dist\Ritualist\Ritualist.exe`.
- Verified packaged files exist:
  - `dist\Ritualist\Ritualist.exe`
  - `dist\Ritualist\_internal\ritualist\canvas\qml\CanvasUse.qml`
  - `dist\Ritualist\_internal\ritualist\sample_canvases\gaming_desktop.yaml`
  - `dist\Ritualist\_internal\ritualist\home\qml\Home.qml`
  - `dist\Ritualist\_internal\ritualist\sample_recipes\gaming_mode.yaml`
- `Ritualist.exe --canvas gaming_desktop` with `QT_QPA_PLATFORM=offscreen`
  stayed alive for 8 seconds, which confirms packaged Canvas Use Mode loads its
  event loop and bundled QML path. The smoke process was then killed.

Automated observations:

- Canvas Use Mode launch path is packaged and smoke-tested.
- Canvas runtime/action/performance JSON checks pass from the development
  checkout.
- PyInstaller still reports Conda-environment optional DLL warnings in
  `build\Ritualist\warn-Ritualist.txt`. These warnings were already present in
  earlier packaged Home builds and did not block the Canvas offscreen launch.

Manual checks still required:

- A human must still visually confirm the packaged Canvas surface is not blank
  or white, `gaming_desktop` components render correctly, and there is no
  obvious jitter.
- A human must still run Doctor, Dry Run, and Run from the packaged Canvas
  surface with real desktop input.
- A human must still verify Pause/Resume/Stop during a real wait, target plan
  preview from `target.card`, recent activity updates, Play confirmation trust,
  declined confirmation stopping, and hard-kill interrupted recovery.
- No v0.2 release tag should be created from this automated dogfood alone.

## Packaged App Smoke

- [ ] Launch `dist\Ritualist\Ritualist.exe` and confirm Home opens.
- [ ] Launch `dist\Ritualist\Ritualist.exe --classic-gui`.
- [ ] Open About / Diagnostics.
- [ ] Confirm diagnostics reports version `0.2.0-alpha.1`.
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
- [ ] Confirm the Play confirmation is a separate top-level/native dialog that
  stays visible above Battle.net / Diablo.
- [ ] Decline Play.
- [ ] Confirm the latest run status is `stopped`.
- [ ] Confirm the final step is `cancelled | Ask before clicking Play | user declined confirmation`.

## Stale-Run Recovery

- [ ] Start `gaming_mode` from the packaged app.
- [ ] Wait until the Play confirmation is visible.
- [ ] Confirm the Play confirmation is a separate top-level/native dialog above
  Battle.net, not the inline QML panel inside Home.
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

## v0.2.0-alpha.1 Release Candidate Validation - 2026-06-17

Validation state: local `main` workspace after Prompt 8 (`efedfa1`) plus
release-candidate version/docs updates.

Automated development-checkout gate:

- `python -m pip install -e ".[all,dev]"`: passed.
- `python -m playwright install chromium`: passed.
- Project version and diagnostics version: `0.2.0-alpha.1`.
- `QT_QPA_PLATFORM=offscreen PYTHONFAULTHANDLER=1 python -m pytest -q`:
  `702 passed, 1 skipped`.
- `python -m compileall -q ritualist tests`: passed.
- `python -m ritualist init`: passed; migrated installed `gaming_mode.yaml`
  browser clean-start fields.
- `python -m ritualist doctor gaming_mode --json --no-strict`: passed;
  compatibility `compatible`, `errors_count: 0`, `warnings_count: 0`.
- `python -m ritualist dry-run gaming_mode`: passed; final state `success`.
- `python -m ritualist canvas validate gaming_desktop`: passed.
- `python -m ritualist canvas runtime gaming_desktop --json`: passed. Live
  user-data runtime build reported about 1680 ms with 20 recent activity rows.
- `python -m ritualist canvas action gaming_desktop diablo_night doctor --dry-run --json`: passed.
- `python -m ritualist perf canvas-use --mock-components 100 --json`: passed,
  4.324 ms, no warnings.
- `python -m ritualist perf canvas-use --mock-components 300 --json`: passed,
  11.379 ms, no warnings.
- `python -m ritualist perf canvas-runtime --mock-components 100 --json`: passed,
  5.827 ms, no warnings.
- `python -m ritualist perf canvas-runtime --mock-components 300 --json`: passed,
  9.638 ms, no warnings.
- `python -m ritualist target plan diablo_iv --json`: passed; local state
  `not_found` on this machine.
- `python -m ritualist plan preview target.start:diablo_iv --json`: passed.
- `python -m ritualist pack export gaming_mode --out <temp>`: passed.
- `python -m ritualist pack import <temp>`: passed into quarantine. Temporary
  `gaming_mode-3` validation import was removed afterward.
- `python -m ritualist canvas pack export <visual-test-canvas> --out <temp> --json`: passed.
- `python -m ritualist canvas pack import <temp> --json`: passed into quarantine.
  Temporary `rc_visual` validation import was removed afterward.

Packaged build and smoke:

- `.\scripts\build_windows_app.ps1`: passed and built
  `dist\Ritualist\Ritualist.exe`.
- Verified packaged files exist:
  - `dist\Ritualist\Ritualist.exe`
  - `dist\Ritualist\_internal\ritualist\canvas\qml\CanvasUse.qml`
  - `dist\Ritualist\_internal\ritualist\sample_canvases\gaming_desktop.yaml`
  - `dist\Ritualist\_internal\ritualist\home\qml\Home.qml`
  - `dist\Ritualist\_internal\ritualist\sample_recipes\gaming_mode.yaml`
- `dist\Ritualist\Ritualist.exe` with `QT_QPA_PLATFORM=offscreen` stayed alive
  for 8 seconds.
- `dist\Ritualist\Ritualist.exe --canvas gaming_desktop` with
  `QT_QPA_PLATFORM=offscreen` stayed alive for 8 seconds.
- `dist\Ritualist\Ritualist.exe --classic-gui` with `QT_QPA_PLATFORM=offscreen`
  stayed alive for 8 seconds.
- Release-candidate artifact created:
  `dist\Ritualist-v0.2.0-alpha.1-rc.zip` (packaged app plus README,
  CHANGELOG, RELEASE_NOTES, and RELEASE_CHECKLIST).
- PyInstaller still reports Conda-environment optional DLL warnings in
  `build\Ritualist\warn-Ritualist.txt` (`impi.dll`, `sycl8.dll`, `msmpi.dll`,
  `UR_LOADER.dll`, `ze_loader.dll`) plus hidden-import warnings already seen in
  prior builds. Offscreen packaged startup smokes passed despite these warnings.

Manual release blockers still open:

- A human still needs to visually confirm packaged Home and Canvas are not blank,
  category switching/hover/focus feel acceptable, and no obvious jitter.
- A human still needs to run packaged Home/Canvas Doctor, Dry Run, Run,
  Pause/Resume/Stop, target plan preview, logs/recent activity, and About /
  Diagnostics.
- A human still needs to run the real `gaming_mode` trace, decline Play, confirm
  stopped status, hard-kill during wait/confirmation, and confirm next launch
  repairs the run as `interrupted`.
- No `v0.2.0-alpha.1` tag was created. Tagging remains blocked until the manual
  packaged desktop dogfood checks above pass.

## v0.2.0-alpha.1 Release Candidate Validation Refresh - 2026-06-17

Validation commit: `edcf54a` (`Check Git blobs in line ending guard`).

Source hygiene release blocker:

- Public raw GitHub was rechecked for the watched Canvas files after push:
  - `ritualist/canvas/runtime.py`: 539 LF-delimited lines, longest line 114 bytes.
  - `ritualist/canvas/controller.py`: 255 LF-delimited lines, longest line 112 bytes.
  - `ritualist/canvas/view_model.py`: 122 LF-delimited lines, longest line 106 bytes.
  - `tests/test_canvas_runtime.py`: 668 LF-delimited lines, longest line 107 bytes.
- `scripts/check_line_endings.py` now checks working-tree bytes, Git `HEAD`
  blobs, and Git index blobs.
- CI now runs `python scripts/check_line_endings.py --check-git-head --check-git-index`.
- `python scripts/check_line_endings.py --stats --check-git-head --check-git-index`:
  passed for 34 managed files.

Automated development-checkout gate:

- `git pull --ff-only`: already up to date.
- `python -m pip install -e ".[all,dev]"`: passed.
- `python -m playwright install chromium`: passed.
- `python -m pytest -q`: `711 passed, 1 skipped`.
- `python -m compileall -q ritualist tests`: passed.
- `python -m ritualist --help`: passed.
- `python -m ritualist actions --json`: passed.
- `python -m ritualist primitives --json`: passed.
- `python -m ritualist policy show --json`: passed.
- `python -m ritualist init`: passed; app data already up to date.
- `python -m ritualist doctor gaming_mode --json --no-strict`: passed.
- `python -m ritualist dry-run gaming_mode`: passed; final state `success`.
- Bundled sample recipe dry-run sweep: 12/12 sample YAML recipes passed.
- `python -m ritualist canvas validate gaming_desktop`: passed.
- `python -m ritualist canvas runtime gaming_desktop --json`: passed. Live
  user-data runtime build reported about 1225 ms with 20 recent activity rows.
- `python -m ritualist canvas action gaming_desktop diablo_night doctor --dry-run --json`: passed.
- `python -m ritualist perf canvas-use --mock-components 100 --json`: passed,
  3.944 ms, no warnings.
- `python -m ritualist perf canvas-use --mock-components 300 --json`: passed,
  11.462 ms, no warnings.
- `python -m ritualist perf canvas-runtime --mock-components 100 --json`: passed,
  3.570 ms, no warnings.
- `python -m ritualist perf canvas-runtime --mock-components 300 --json`: passed,
  10.844 ms, no warnings.
- `python -m ritualist target discover diablo_iv --json`: passed.
- `python -m ritualist target plan diablo_iv --json`: passed; local state
  `not_found` on this machine.
- `python -m ritualist plan preview target.start:diablo_iv --json`: passed.
- Isolated app-data pack smoke passed:
  - `python -m ritualist pack export gaming_mode --out <temp>` and import passed.
  - `python -m ritualist canvas pack export minimal_desktop --out <temp> --json`
    and import passed.
  - `python -m ritualist canvas theme export default --out <temp> --json` and
    import passed.
- `gaming_desktop` export as a visual Canvas pack is intentionally blocked
  because it contains behavior-bound components (`ritual.card`,
  `ritual.controller`, and `target.card`). This is expected pack-governance
  behavior, not a release failure.

Packaged build and non-visual smoke:

- `.\scripts\build_windows_app.ps1`: passed and built
  `dist\Ritualist\Ritualist.exe`.
- Verified packaged files exist:
  - `dist\Ritualist\Ritualist.exe`
  - `dist\Ritualist\_internal\ritualist\canvas\qml\CanvasUse.qml`
  - `dist\Ritualist\_internal\ritualist\sample_canvases\gaming_desktop.yaml`
  - `dist\Ritualist\_internal\ritualist\home\qml\Home.qml`
  - `dist\Ritualist\_internal\ritualist\sample_recipes\gaming_mode.yaml`
- With `QT_QPA_PLATFORM=offscreen`, these packaged modes stayed alive for 8
  seconds and were then force-stopped:
  - `dist\Ritualist\Ritualist.exe`
  - `dist\Ritualist\Ritualist.exe --canvas gaming_desktop`
  - `dist\Ritualist\Ritualist.exe --classic-gui`
- Release-candidate artifact refreshed:
  `dist\Ritualist-v0.2.0-alpha.1-rc.zip` (395,188,611 bytes).
- PyInstaller still reports Conda-environment optional DLL warnings in
  `build\Ritualist\warn-Ritualist.txt` (`impi.dll`, `sycl8.dll`, `msmpi.dll`,
  `UR_LOADER.dll`, `ze_loader.dll`) plus hidden-import warnings already seen in
  prior builds. Offscreen packaged startup smokes passed despite these warnings.

Manual release blockers still open:

- A human still needs to visually confirm packaged Home and Canvas are not blank,
  category switching/hover/focus feel acceptable, and no obvious jitter.
- A human still needs to run packaged Home/Canvas Doctor, Dry Run, Run,
  Pause/Resume/Stop, target plan preview, logs/recent activity, and About /
  Diagnostics with real desktop input.
- A human still needs to run the real `gaming_mode` trace, decline Play, confirm
  stopped status, hard-kill during wait/confirmation, and confirm next launch
  repairs the run as `interrupted`.
- No `v0.2.0-alpha.1` tag was created. Tagging remains blocked until the manual
  packaged desktop dogfood checks above pass.

## Source Blob / Line-Ending Verification - 2026-06-17

Status: Passed.

Evidence:

- At verification time, HEAD and `origin/main` were at `24da7c2`
  (`Allow safe browser wait pack imports without browser extras`).
- Working tree clean before this checklist note was added.
- Canvas source/test files verified LF-delimited in working tree, Git index, and
  Git HEAD.
- Key files:
  - `ritualist/canvas/runtime.py`: 538 LF, 0 CR, longest line 114.
  - `ritualist/canvas/controller.py`: 254 LF, 0 CR, longest line 112.
  - `ritualist/canvas/view_model.py`: 121 LF, 0 CR, longest line 106.
  - `tests/test_canvas_runtime.py`: 667 LF, 0 CR, longest line 107.
- `python scripts\check_line_endings.py --stats --check-git-head --check-git-index`
  passed for 34 managed files.
- No source normalization diff was produced; release validation should proceed to
  manual packaged desktop dogfood rather than another line-ending rewrite.

## Manual Packaged Dogfood Kickoff - 2026-06-17

Status: Automated setup passed; real desktop dogfood still required.

Validation commit: `24da7c2`
(`Allow safe browser wait pack imports without browser extras`).

Automated command path:

- `git pull --ff-only`: already up to date.
- `python -m pip install -e ".[all,dev]"`: passed.
- `python -m playwright install chromium`: passed.
- `python -m pytest -q`: `713 passed, 1 skipped`.
- `python -m compileall -q ritualist tests`: passed.
- `python -m ritualist --help`: passed.
- `.\scripts\build_windows_app.ps1`: passed and built
  `dist\Ritualist\Ritualist.exe`.

Packaged file checks:

- `dist\Ritualist\Ritualist.exe`: present.
- `dist\Ritualist\_internal\ritualist\canvas\qml\CanvasUse.qml`: present.
- `dist\Ritualist\_internal\ritualist\sample_canvases\gaming_desktop.yaml`:
  present.
- `dist\Ritualist\_internal\ritualist\home\qml\Home.qml`: present.
- `dist\Ritualist\_internal\ritualist\sample_recipes\gaming_mode.yaml`: present.

Non-visual packaged smokes:

- `dist\Ritualist\Ritualist.exe` with `QT_QPA_PLATFORM=offscreen` stayed alive
  for 8 seconds.
- `dist\Ritualist\Ritualist.exe --canvas gaming_desktop` with
  `QT_QPA_PLATFORM=offscreen` stayed alive for 8 seconds.
- `dist\Ritualist\Ritualist.exe --classic-gui` with `QT_QPA_PLATFORM=offscreen`
  stayed alive for 8 seconds.

Manual gate remains open:

- Do not tag `v0.2.0-alpha.1` yet.
- A human still needs to validate packaged Home, Canvas Use Mode, classic GUI,
  real `gaming_mode` run control, native confirmation z-order over
  Chrome/Battle.net, declined Play status, interrupted repair after hard kill,
  Watch Me preview privacy, Canvas/theme pack behavior, and 100/300 component
  performance feel on the real Windows desktop.

## UIA-Assisted Real Desktop Dogfood - 2026-06-17

Status: Partial real-desktop evidence. Packaged Canvas/run/recovery paths passed
on the real Windows desktop, but this is not a complete tag-ready manual gate
closeout. Home card-button hand-click validation, dedicated visible
`ritual.status`/Recent activity checks, subjective 100/300 component feel, and
live Canvas/theme pack import/export remain caveats unless separately verified.

Workspace state at start:

- `main` and `origin/main` were in sync at `e4d0dd2`
  (`Record packaged dogfood kickoff evidence`).
- Working tree was clean before this checklist note was added.

Visible packaged launch checks:

- `dist\Ritualist\Ritualist.exe` opened a visible `Ritualist Home` window.
- `dist\Ritualist\Ritualist.exe --canvas gaming_desktop` opened a visible
  `Ritualist Canvas` window. `gaming_desktop` rendered real components and was
  not blank or white.
- `dist\Ritualist\Ritualist.exe --classic-gui` opened a visible classic
  `Ritualist` window.
- Packaged Canvas buttons were exposed through Windows UI Automation and were
  invoked by accessible name, not by coordinate clicks. Packaged Home exposed
  only the card container through UI Automation, so Home card buttons still need
  literal human click validation if that remains a release requirement.

Packaged Canvas action checks:

- `doctor` on the `Diablo Night` card completed in packaged Canvas and updated
  the card state.
- `dry_run` on the `Diablo Night` card completed in packaged Canvas. Run
  `20260617T143914Z_gaming_mode` ended `success`, `dry_run: true`, with all
  7 steps recorded as dry-run `would ...` actions.
- `preview_plan` on `diablo_target` completed in packaged Canvas and returned a
  Diablo IV target plan preview without launching apps, clicking UI, installing
  software, or writing target-start files. On this desktop the target state was
  `not_found`, with local-resolution suggestions.
- Watch Me was started, stopped, drafted, and discarded from packaged Canvas.
  Session `20260617T143930Z_7a7f9328` produced a disabled/review-only draft,
  did not install or auto-run behavior, recorded no browser URL, and matched no
  forbidden markers (`password`, `secret`, `token`, `cookie`, `clipboard`,
  `screenshot`, `keystroke`, `keylog`, `html`, or `dom`) in draft/session files.

Real `gaming_mode` run checks:

- A real packaged Canvas `Run` opened the managed Chrome ambience profile,
  launched/surfaced Battle.net, selected Diablo IV, and reached the final Play
  confirmation.
- Pause, Resume, and Stop controls worked during the real run. Run
  `20260617T144157Z_gaming_mode` records state history:
  `running -> waiting -> paused -> running -> confirming -> stopping -> stopped`.
- Runtime state updates were visible on the `Diablo Night` card/top Canvas
  event text during the real run. This did not separately validate the
  dedicated `ritual.status` component after each transition, and
  `gaming_desktop` does not include a dedicated `recent.activity` component.
- The native `Ritualist Confirmation Required` dialog appeared as a separate
  top-level dialog above Battle.net before the Play click.
- Declining/stopping the Play confirmation ended as `stopped` with
  `stopped_reason: stopped_user_declined_confirmation`. `show-run
  20260617T144157Z_gaming_mode` clearly reports the final step
  `Ask before clicking Play` as `cancelled` with message
  `user declined confirmation`; no confirmed risky Play action was performed.
- Hard-killing packaged Canvas during an active run and then relaunching
  packaged Home repaired abandoned run `20260617T144316Z_gaming_mode` to
  `interrupted`. `show-run 20260617T144316Z_gaming_mode --no-repair` reports
  `final_message: Ritualist exited before finalizing this run. Last recorded
  step: Ask before clicking Play.`

Performance and pack-safety checks:

- `python -m ritualist perf canvas-use --mock-components 100 --json`: passed in
  3.852 ms with 0 warnings.
- `python -m ritualist perf canvas-use --mock-components 300 --json`: passed in
  10.916 ms with 0 warnings.
- These are command-path timings only, not a human subjective feel pass for
  visible 100/300 component desktop interaction.
- Focused pack-safety and run-log tests passed:
  `python -m pytest -q tests/test_canvas_packs.py tests/test_watch_me.py
  tests/test_canvas_runtime.py
  tests/test_cli.py::test_runs_repairs_and_reports_interrupted_records
  tests/test_cli.py::test_show_run_prints_runtime_v2_state_metadata
  tests/test_cli.py::test_cancelled_final_confirmation_after_keep_open_browser_keeps_alive`
  reported `55 passed`.
- Canvas/theme pack import/export safety was covered by focused tests in this
  turn, not by live desktop import/export commands. Treat that checklist item as
  not revalidated here if the release gate requires an actual command-path or
  visual desktop pack import/export pass.

Release note:

- No `v0.2.0-alpha.1` tag was created.

## Packaged Release Acceptance Harness - 2026-06-17

Status: Machine-verifiable packaged GUI/runtime acceptance plus source CLI
supplemental command evidence passed all objective checks the harness can
assert. Two release gates remain `NEEDS_HUMAN_REVIEW`; do not tag
`v0.2.0-alpha.1` yet.

Harness/spec added:

- `tests/acceptance/release_v0_2_alpha_1.yaml`
- `scripts/ritualist_release_acceptance.ps1`
- E2E instrumentation is opt-in through `RITUALIST_E2E=1`,
  `RITUALIST_E2E_ARTIFACT_DIR`, and `RITUALIST_E2E_APP_DATA_DIR`.
- Fixture mode uses an isolated app-data root plus a fake `Battle.net Fixture`
  window. It does not depend on real game login and does not run gameplay
  automation.

Command evidence:

- `git pull --ff-only`: already up to date.
- `python scripts/check_line_endings.py --stats --check-git-head --check-git-index`:
  passed for 35 managed files.
- `python -m pytest -q`: `721 passed, 1 skipped`.
- `python -m compileall -q ritualist tests`: passed.
- `.\scripts\build_windows_app.ps1`: passed and built
  `dist\Ritualist\Ritualist.exe`.
- `.\scripts\ritualist_release_acceptance.ps1 -Packaged -RecordScreen`: passed
  with no machine `FAIL` checks.
- Command scope: the packaged executable is used for Home, Canvas Use Mode,
  classic GUI, and runtime scenarios. Source-tree `python -m ritualist` is used
  for supplemental CLI-only safety, perf, run-log, and visual-pack command
  evidence because the Windows app bundle is a GUI entry point.

Acceptance artifacts:

- Summary JSON:
  `artifacts\release-acceptance\acceptance-summary.json`
- Summary Markdown:
  `artifacts\release-acceptance\acceptance-summary.md`
- Evidence root:
  `artifacts\release-acceptance\evidence`
- Screen-frame manifests were written under
  `artifacts\release-acceptance\evidence\screen-frames`.
- E2E runtime JSONL events were written under
  `artifacts\release-acceptance\evidence\e2e-events`.
- E2E event merge reported `0` JSONL parse errors.
- Run logs were copied under
  `artifacts\release-acceptance\evidence\run-logs`.

Acceptance summary:

- `PASS`: 19
- `FAIL`: 0
- `NEEDS_HUMAN_REVIEW`: 2
- `taggable`: `false`
- `tag_created`: `false`

Objective checks that passed:

- Packaged Home, Canvas Use Mode, and classic GUI opened and stayed alive.
- Packaged `gaming_desktop` rendered with expected Canvas controls.
- Packaged Canvas produced machine evidence for Doctor, Dry Run, safe Run,
  `ritual.status` transitions, Pause/Resume/Stop, target preview status, native
  confirmation z-order over the fake Battle.net fixture, declined Play stop
  handling, hard-kill repair to `interrupted`, and Watch Me preview privacy.
- Source CLI supplemental checks produced machine evidence for structured target
  plan JSON, `show-run` declined-confirmation output, Canvas/theme pack
  import/export quarantine behavior, arbitrary component-code rejection, and
  100/300 component perf command outputs.

Release blockers still open:

- `ui_heartbeat_no_obvious_freeze`: `NEEDS_HUMAN_REVIEW`. The harness captured
  frame/e2e timing evidence, but subjective smoothness still needs a human
  visual pass.
- `recent_activity_updates`: `NEEDS_HUMAN_REVIEW`. Run history was captured, but
  packaged Home Recent activity was not exposed through UI Automation for a
  machine assertion.

Release note:

- No `v0.2.0-alpha.1` tag was created. The release is not taggable until the two
  `NEEDS_HUMAN_REVIEW` items above are resolved or explicitly accepted by a
  human release owner.
