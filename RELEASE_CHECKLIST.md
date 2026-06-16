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

## Packaged App Smoke

- [ ] Launch `dist\Ritualist\Ritualist.exe`.
- [ ] Open About / Diagnostics.
- [ ] Confirm diagnostics reports version `0.1.0-alpha.1`.
- [ ] Copy diagnostics and save it with the release notes.
- [ ] Click Initialize App.
- [ ] Click Refresh Recipes.
- [ ] Select `gaming_mode`.
- [ ] Click Doctor and confirm checks are printed.
- [ ] Click Dry Run and confirm it completes.

## Home Alpha Dogfood

- [ ] Launch the packaged app with `dist\Ritualist\Ritualist.exe`.
- [ ] Open Home from the packaged app.
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
- [ ] Confirm startup or Refresh Recipes reconciles the abandoned run.
- [ ] Run `python -m ritualist runs` and confirm the abandoned run is `interrupted`.
- [ ] Run `python -m ritualist show-run <run-id>` and confirm `final_message` explains that Ritualist exited before finalizing the run.

## Release Artifacts

- [ ] Keep `dist\Ritualist` as the release folder.
- [ ] Include `README.md`, `CHANGELOG.md`, `RELEASE_NOTES.md`, and this checklist.
- [ ] Include known limitations from `RELEASE_NOTES.md`.
- [ ] Do not include `build`, `.pytest_cache`, `__pycache__`, or `Ritualist.spec`.
