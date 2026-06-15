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
