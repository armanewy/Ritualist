# Local Learning Privacy Contract

This document defines the privacy contract for Ritualist Local Learning. It is
a specification and test target, not a claim that a user-facing Local Learning
Suggestions UI is currently shipped.

Local Learning exists only to support local, review-only ritual and Room
suggestions from consented sources. It must not introduce recording, hidden
collection, remote telemetry, or automatic creation or execution behavior.

## Contract

- Local Learning is off by default.
- Local Learning is local only. Consented data stays on the user's machine and
  is not sent to cloud services, marketplace services, remote execution
  services, or network command channels.
- Local Learning requires explicit source-level consent. Enabling one source
  must not enable any other source.
- Users must have controls to view the sources and local learning records that
  Local Learning uses.
- Users must have controls to delete local learning records.
- Local Learning must not provide Watch Me, recording, teach-by-watching, or
  live observation.
- Local Learning must not collect or ingest browser history.
- Local Learning must not collect screenshots, OCR text, screen recordings,
  keystrokes, global keyboard hooks, click coordinates, or coordinate logs.
- Local Learning must not auto-create rituals, recipes, Rooms, components,
  packs, or shortcuts.
- Local Learning must not auto-run rituals, recipes, actions, shortcuts, packs,
  scripts, or desktop automation.

## Allowed Sources

The current source registry is intentionally small:

- `ritualist_journal`: local Ritualist run summaries and user-authored notes.
- `open_windows`: current top-level app/window names observed only during
  explicit use.
- `recent_items`: local recent Ritualist Rooms, shortcuts, and recipes.

Every source is disabled by default. A source is usable only when Local Learning
is enabled, the source is selected, and the consent record explicitly includes
that source.

## Consent

Consent is source-specific. A valid consent record identifies the consent
version, timestamp, and approved source IDs. A global enabled flag without a
valid consent record does not enable Local Learning. A consent record for one
source does not authorize another source.

Configuration and import paths must ignore unknown or forbidden learning
sources instead of creating new collection behavior.

## View And Delete Controls

Any user-facing Local Learning surface must make its local records inspectable
and removable. View controls should show which source produced a record and
what local record would be used for a suggestion. Delete controls must remove
local learning records without requiring cloud access or a desktop automation
session.

This section is a product requirement for Local Learning surfaces. It should
not be read as evidence that a Suggestions UI has already shipped.

## Creation And Run Boundaries

Suggestions may propose a draft change only after source-level consent. The
user must review before any suggestion becomes a local ritual, recipe, Room,
component, pack, or shortcut.

Local Learning must never run desktop automation automatically. Running a
ritual or recipe remains an explicit user action and still follows Doctor,
dry-run, policy, confirmation, logging, and recovery boundaries.

## Forbidden Sources And Methods

The following capabilities are outside the Local Learning contract:

- Watch Me, watch-me, or teach-by-watching.
- Browser history ingestion or Recall-like history collection.
- Screenshots, screen capture, screen recording, OCR, or visual text capture.
- Keystroke capture, keylogging, global keyboard hooks, or password/credential
  automation.
- Click-coordinate capture, coordinate replay, pointer recording, or hidden
  live observation.
- Cloud sync, remote execution, marketplace behavior, arbitrary code execution,
  or network command channels.
