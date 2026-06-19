# Setpiece v0.2.0-alpha.1 Release Candidate Notes

Setpiece v0.2.0-alpha.1 is a Canvas-era alpha candidate for local, personal PC runbooks. It keeps the existing CLI/classic GUI workflow and adds a typed Canvas command surface, deterministic planning, read-only diagnostics primitives, and local visual pack separation.

## What Works

- CLI recipe run, dry-run, Doctor, run history, notes, stale-run repair, and inspect-window diagnostics.
- Packaged Windows one-folder app at `dist\Setpiece\Setpiece.exe`.
- Packaged Home, packaged Canvas Use Mode, and classic GUI launch paths.
- Bundled `gaming_mode` sample and `gaming_desktop` Canvas.
- Canvas typed components, runtime model, Edit Mode model/UI MVP, theme tokens, performance modes, and perf smoke commands.
- Deterministic intent plan preview and generic target resolution preview.
- Primitive Kernel metadata, policy/governance, read-only primitive families, and Doctor visibility.
- Structured browser runbook actions plus clean-start options for Setpiece-managed browser profiles.
- Local `.setpiececanvas` and `.setpiecetheme` export/import into quarantine.

## Build The Packaged App

Build on Windows from the repository root:

```powershell
python -m pip install -e ".[all,dev]"
python -m playwright install chromium
.\scripts\build_windows_app.ps1
```

The output is:

```text
dist\Setpiece\Setpiece.exe
```

The packaged app launches Home by default. Use:

```powershell
dist\Setpiece\Setpiece.exe --canvas gaming_desktop
dist\Setpiece\Setpiece.exe --classic-gui
```

## First Real Trace

Use this sequence for a real packaged `gaming_mode` trace:

```text
1. Launch dist\Setpiece\Setpiece.exe.
2. Confirm Home opens and installed recipes load.
3. Launch dist\Setpiece\Setpiece.exe --canvas gaming_desktop.
4. Confirm Canvas renders gaming_desktop components.
5. Run Doctor for gaming_mode.
6. Dry-run gaming_mode.
7. Run gaming_mode only when it is safe to open browser media and Battle.net.
8. Confirm YouTube opens and loops.
9. Confirm Battle.net launches and Diablo IV is selected.
10. Confirm the Play confirmation is a separate top-level dialog above Battle.net.
11. Decline Play once.
12. Confirm the run appears as stopped and recent activity/logs show the stopped reason.
13. Hard-kill during a later wait/confirmation and confirm next launch repairs the run as interrupted.
```

## Known Limitations

- This is an alpha candidate, not a signed installer or stable release.
- The packaged app is a one-folder PyInstaller build.
- The packaged acceptance harness now records build/startup/runtime/perf dogfood evidence; no `v0.2.0-alpha.1` tag has been created yet.
- Canvas Use/Edit Mode is functional but still an alpha surface.
- Desktop Work-Area preserves the taskbar/work area and wallpaper passthrough, but blank-area click-through remains intentionally unimplemented and frozen.
- Real Battle.net/UIA labels can change by locale, app state, and launcher updates.
- Target resolution can report `not_found` if Diablo IV is not discoverable through running processes, shortcuts, explicit paths, installed-app metadata, removable media, or local memory.
- Local Learning, Activity Journal, Activity Signals, Ritual Suggestions, and
  Review Before Create are product direction, not implemented behavior in this
  alpha candidate.
- Theme packs reject assets in this candidate until explicit theme asset references exist.
- PyInstaller may report Conda-environment optional DLL warnings; the release checklist records whether startup still works.

## Explicit Non-Goals

- No AI features or AI planning.
- No macro recording.
- No OCR.
- No arbitrary recipe-supplied Python, shell, PowerShell, JavaScript, QML, HTML, or plugin code.
- No coordinate clicks.
- No cloud sync, network marketplace, remote execution, telemetry, or auto-install.
- No password/login automation.
- No firmware, driver, storage, registry, firewall, service-control, or package-install mutation.
- No gameplay automation.
