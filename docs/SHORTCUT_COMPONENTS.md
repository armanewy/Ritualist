# Setpiece Shortcut Components

Shortcut Components are Room/Canvas components for instant native access. They
are not rituals, recipes, runbooks, macros, or automation recordings.

Core rule:

```text
Rituals are for multi-step intent.
Shortcuts are for instant native access.
```

This document defines the product and UX boundary for future Shortcut
Components. It does not require the dedicated `shortcut.*` component types to
exist yet.

## Component Family

The Shortcut Component family should use explicit component types:

- `shortcut.folder`: opens a local folder with the native file manager.
- `shortcut.app`: opens a local application or trusted OS application shortcut.
- `shortcut.url`: opens a URL with the user's default browser.
- `shortcut.file`: later; opens a local file with the OS-associated app.
- Folder stack: later; groups several folder shortcuts without becoming a file
  browser.

Existing launch-oriented components, such as `app.launcher`, should follow the
same user-facing boundary when they act as instant native access: they are not
ritual cards and they must not look or behave like recipe execution.

## Native Handoff

Opening a shortcut hands control to the operating system or the user's existing
native app:

- A folder opens in File Explorer on Windows, or the platform file manager on
  other supported platforms.
- An app opens through the OS-supported app launch path.
- A URL opens in the user's default browser.
- A future file shortcut opens through the OS file association.

Setpiece should not stay in the middle after the handoff. It may show a small
status or warning if the target cannot be opened, but it should not create a
runtime workflow around the action.

## UX Behavior

Shortcut open behavior:

- No recipe is created.
- No run log is created.
- No ritual controller appears.
- No pause, resume, or stop controls appear.
- No Doctor or Dry Run ceremony appears by default.
- Missing or invalid targets show a lightweight warning and an edit affordance.
- Imported or shared Room packs must not open shortcuts automatically.

Shortcut surfaces should use compact native-access affordances: icon, label,
target hint, and an explicit Open affordance where needed. They should not use
ritual status colors, run progress, step lists, or recovery language.

## Interaction Model

In Desktop Work-Area Use Mode:

- Single click selects or focuses a shortcut component.
- Double click or an explicit Open command opens the shortcut.
- Keyboard activation may open the focused shortcut when that matches platform
  conventions.

In Edit Mode:

- Single click selects the shortcut component for editing.
- Dragging, resizing, property editing, and target repair stay in the editor.
- Opening is not the default edit interaction.

Shortcut open behavior may become configurable later, for example single-click
open for users who prefer launcher-style behavior. The default must stay easy
to distinguish from editing and from ritual execution.

## Ritual Boundary

A shortcut can be part of a Room, but it is not a ritual. A Room can contain
both shortcut components and ritual cards:

- Use a shortcut for "open Downloads", "open the project folder", "open Slack",
  or "open docs URL".
- Use a ritual for multi-step intent such as "prepare for support shift",
  "start streaming setup", or "begin gaming night" where validation,
  confirmations, waits, run controls, logs, and recovery matter.

Repeated single folder, app, or URL access should suggest a Shortcut Component,
not a recipe. Multi-step patterns may become ritual suggestions only after the
user reviews and creates them.

## Non-Goals

Shortcut Components must not turn Setpiece into:

- a file manager
- an Explorer replacement
- a recursive indexing service
- a folder tree UI
- a rename, delete, move, or copy UI
- an Explorer context-menu replacement
- a thumbnail-heavy file browser
- a shell replacement, taskbar replacement, kiosk surface, or desktop security
  boundary

Shortcut Components also must not add arbitrary recipe-supplied Python,
JavaScript, QML, HTML, shell snippets, coordinate clicks, screen recording,
OCR, cloud sync, remote execution, marketplace behavior, password automation,
gameplay automation, click-through or native hit-test work, Watch Me or
recording mode, taskbar hiding, or taskbar replacement.

## Implementation Slice

The recommended first implementation slice is `shortcut.folder`:

- validate a local folder path
- render a small shortcut tile in Use Mode
- open the folder through the native file manager on explicit activation
- show a lightweight missing-folder warning and edit affordance
- create no recipe, no run log, no ritual controller, and no Doctor/Dry Run path

That slice should use fakes/mocks in tests and must not require a Windows
desktop session.
