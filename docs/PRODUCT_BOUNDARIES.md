# Ritualist Product Boundaries

Ritualist turns Windows into activity-specific Rooms powered by safe local
rituals that can be previewed, checked, run, paused, logged, recovered, and
improved over time.

Ritualist is a local ritual/runbook engine with a desktop-native body. Recipes
and rituals are the center of gravity. Rooms and Canvas make those rituals
visible and daily-usable, but they must not become an independent desktop
customizer, widget platform, shell, or wallpaper product.

The product hierarchy is:

```text
Rituals are the brain.
Rooms and Canvas are the body.
Safety, Doctor, dry-run, logs, and recovery are the soul.
Shortcuts are connective tissue.
Suggestions are the helper.
Windows remains the world underneath.
```

Every roadmap item must improve at least one of:

- ritual quality
- Room usefulness
- trust and safety
- the Suggestion-to-draft loop
- pack and template reuse

If a feature does not improve one of those, it does not ship.

## Core Product Nouns

Ritualist has six product nouns:

- **Room**: user-facing desktop for an activity.
- **Ritual**: multi-step local procedure with Doctor, dry-run, confirmation,
  logs, and recovery.
- **Component**: visual, control, or status block in a Room.
- **Shortcut**: instant native handoff with no run log or ritual controller.
- **Suggestion**: review-only recommendation from local signals.
- **Pack**: portable bundle quarantined and reviewed before use.

Avoid adding more product nouns unless the feature cannot be explained through
these six.

## Containment Doctrine

Ritualist is allowed to be excellent at:

- preparing a PC for repeated activities
- running attended local procedures
- making ritual state visible
- showing target readiness
- asking for confirmation at risk boundaries
- logging what happened
- recovering interrupted runs
- letting users build Rooms for activities
- suggesting safe drafts from local patterns
- sharing and reusing safe templates after quarantine and review

Ritualist is not allowed to become:

- a Windows shell replacement
- a file manager
- a live wallpaper renderer
- a generic widget marketplace
- a general RPA suite
- a macro recorder
- a screen recorder, OCR tool, or Recall clone
- a remote execution tool
- a cloud automation service
- a gameplay automation system
- a password or credential automation system
- an arbitrary-code component platform

## Feature Freeze

The v0.2 release line is in feature freeze. Do not add new product systems,
primitive families, desktop-host experiments, browser-history collection,
marketplace behavior, recording surfaces, or generic widgets while release
acceptance is still open.

After Desktop Work-Area Mode and wallpaper passthrough, desktop-host expansion
is frozen. Do not pursue native blank-area click-through, component-island
windows, WorkerW/Progman attachment, desktop icon integration, fullscreen couch
mode, shell replacement, or taskbar manipulation until the ritual/Room loop is
proven.

Browser history and Recall-like sources are frozen. They are sensitive and not
needed for the core loop.

New primitive families are frozen unless a hero Room or runbook requires them
and they pass the full gate: Doctor can check them, dry-run can explain them,
policy can classify them, risky boundaries are confirmed, logs are useful,
failure is recoverable, and imported packs remain safe.

Marketplace behavior is frozen. Packs are allowed; marketplace distribution is
not.

Recording remains frozen permanently for this product direction: no Watch Me,
record mode, teach-by-watching, macro recorder, global hooks, keylogging,
screenshots, screen recording, OCR, or coordinate capture.

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
