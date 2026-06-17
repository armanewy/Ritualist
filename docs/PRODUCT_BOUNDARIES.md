# Ritualist Product Boundaries

Ritualist is a local, visible, policy-gated Windows command surface for Rooms
and rituals. It sits on top of the user's desktop; it does not become the
desktop.

## Current Desktop Baseline

Desktop Work-Area Use Mode is the current seamless desktop target. It is a
transparent component layer sized to the Windows work area, with the taskbar
visible and Explorer still running as the Windows shell and file manager.

The default Desktop Work-Area background is wallpaper or system-background
passthrough. Windows and the user's wallpaper app own the wallpaper. Ritualist
does not render live, video, web, app, or executable wallpapers, and it does
not manage, pause, stop, or replace Wallpaper Engine, Lively Wallpaper, or
similar wallpaper tools.

Blank-area click-through is not implemented yet in Use Mode. Release evidence
must keep that check as `NEEDS_HUMAN_REVIEW` until native hit-test behavior is
implemented and proven. The acceptance harness must not fake click-through by
synthesizing coordinate clicks, forwarding mouse events, or replaying pointer
positions.

## Ownership

- Windows remains the operating system, shell host, taskbar owner, window
  manager, wallpaper owner, and trust/recovery surface.
- Explorer remains the file manager and desktop shell.
- Wallpaper Engine, Lively Wallpaper, Windows Personalization, or another user
  wallpaper app owns wallpaper rendering and playback.
- Ritualist owns built-in Room/Canvas components, ritual cards, runtime status,
  explicit confirmations, logs, pack validation, and local policy checks.

## Shortcuts And Rituals

Shortcut components are not rituals. Opening a folder, app, URL, or file is an
instant native handoff when that component type is supported. It should not
create a recipe, create a run log, show the ritual controller, or require
Doctor/Dry Run ceremony by default.

Rituals are for multi-step intent: readable recipes, validation, dry-run
support, confirmation gates, pause/resume/stop controls, logs, and recovery.

The shortcut boundary is documented in
[Shortcut Components](SHORTCUT_COMPONENTS.md). Folder shortcuts hand off to
File Explorer on Windows; Ritualist must not replace Explorer, build a file
manager, recursively index folders, provide folder tree or context-menu UI, or
turn single-step folder/app/URL/file access into recipe execution.

## Local Learning Direction

Future Ritual Suggestions must be local, opt-in, and review-only. Ritualist may
suggest useful desktop components or rituals from consented local activity
signals and Ritualist's own Activity Journal, but it must not create or run
anything automatically. The user reviews every suggestion before it becomes a
component or ritual.

Local Learning is not Watch Me, recording, teach-by-watching, live observation,
macro capture, keylogging, screenshot capture, OCR, screen recording, or
coordinate logging.

## Non-Goals

Ritualist does not provide:

- Watch Me or recording mode.
- Macro recording, teach-by-watching, global click/keyboard capture, keylogging,
  screenshots, screen recording, OCR, or coordinate-click automation.
- Arbitrary recipe-supplied Python, JavaScript, QML, HTML, shell snippets, or
  remote widgets.
- Cloud sync, remote execution, network command channels, or marketplace
  behavior.
- Password automation, gameplay automation, firmware/driver/storage/network
  mutation, shell replacement, taskbar hiding, kiosk mode, Explorer
  replacement, file-manager replacement, or Wallpaper Engine replacement.
