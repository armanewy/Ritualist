# Ritualist v0.1.0-alpha.1 Release Notes

Ritualist v0.1.0-alpha.1 is an alpha release of a local Windows personal workflow app for the proven `gaming_mode` routine.

## What Works

- Run recipes from the CLI with `ritualist run <recipe-id-or-path>`.
- Dry-run recipes from the CLI or GUI.
- Initialize local app directories and install the bundled `gaming_mode` sample.
- Discover installed recipes by id.
- Launch and use the GUI from development or the packaged Windows executable.
- Run Doctor checks without side effects.
- Inspect Windows UI Automation windows with `inspect-window`.
- Keep browser media open with recipe-level `keep_open: true` or CLI `--keep-alive`.
- Write per-run logs and inspect them with `ritualist runs` and `ritualist show-run`.
- Recover abandoned `running` histories as `interrupted` after hard process termination.
- Use About / Diagnostics in the packaged GUI to copy version, environment, dependency, and path information.
- Open the experimental Home dashboard for installed recipe cards, local run status, dry-run, Doctor, edit, log access, and guarded run controls.
- Run the generated-data Home mock for card-grid and event-update dogfooding without launching recipes or desktop automation.

## Build The Packaged App

Build on Windows from the repository root:

```powershell
python -m pip install -e ".[all,dev]"
python -m playwright install chromium
.\scripts\build_windows_app.ps1
```

The output is:

```text
dist\Ritualist\Ritualist.exe
```

The packaged app launches the GUI. It does not run any ritual automatically.

## Home Alpha Dogfood

Home is an alpha dashboard for local recipes. It should be dogfooded from both the packaged app and the development checkout before a Home-focused release:

```text
1. Launch dist\Ritualist\Ritualist.exe
2. Open Home
3. Run python -m ritualist home --mock from the development checkout
4. Run gaming_mode from Home
5. Pause a visible window.wait action, then resume it
6. Stop an active ritual from Home
7. Hard-kill Ritualist.exe during a run, relaunch it, and confirm the abandoned run is interrupted
8. Inspect logs from Home and confirm run.json and steps.jsonl are present for the run
```

## First Real Trace

Use this sequence for the first packaged `gaming_mode` trace:

```text
1. Launch dist\Ritualist\Ritualist.exe
2. Open About / Diagnostics and copy diagnostics
3. Initialize App
4. Refresh Recipes
5. Select gaming_mode
6. Click Doctor
7. Dry Run
8. Run
9. Confirm YouTube opens and loops
10. Confirm Battle.net launches
11. Confirm Diablo IV is selected
12. Decline Play once
13. Confirm the run appears as stopped
14. Run again and accept Play only if you actually want to
```

## Known Limitations

- This is an alpha build intended for local personal use.
- The packaged app is a one-folder PyInstaller build, not an installer.
- Home is an experimental alpha surface. CLI and classic GUI flows remain the fallback for release-critical validation.
- Home mock data is generated locally for UI dogfooding only; it does not validate real recipe execution.
- Home performance depends on keeping recipe loading, run-history repair, thumbnail work, Playwright calls, and Windows UI Automation scans off the GUI thread.
- Pause and Resume are meaningful only while a running workflow is in a pausable wait or runtime state that supports those controls.
- Stop requests are cooperative; adapter work that is already inside an external app or browser call may finish before the stop is reflected.
- Playwright browser binaries and persistent profiles should be tested on the target Windows machine after building.
- UI Automation labels can vary between Battle.net states, languages, and updates.
- Stale-run recovery can mark hard-killed runs as `interrupted`, but it cannot reconstruct a step result that was never written.
- Long-running browser media is best kept inside the GUI or with `keep_open: true`; CLI exit may close the Playwright-owned browser.
- Windows-specific desktop actions are not supported on non-Windows systems.

## Explicit Non-Goals

- No AI features.
- No macro recording.
- No OCR.
- No arbitrary recipe-supplied Python or JavaScript actions.
- No coordinate clicks.
- No cloud sync.
- No plugin system.
- No gameplay automation.
- No telemetry or remote execution.
