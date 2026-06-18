# Ritualist Suite Packs

Suite Packs (`.ritualistsuite`) are local whole-Room bundles. They are a wrapper
around existing pack types:

- one Canvas/Room pack (`.ritualistcanvas`)
- optional Theme pack (`.ritualisttheme`)
- zero or more behavior-bearing Ritual packs (`.ritualistpack`)
- optional `README.md` review notes

Suite import is deliberately inert. Importing a suite validates every nested
pack independently and places content into quarantine. It does not enable a
recipe, activate a canvas, run a ritual, preserve remembered approvals, or trust
any previous review state.

## Safety Rules

- Nested packs must pass their existing validators.
- Ritual packs must be disclosed as behavior-bearing in the suite manifest.
- Imported rituals remain disabled in recipe-pack quarantine until reviewed and
  enabled through the existing pack flow.
- Visual packs remain quarantined and are not copied into active canvases or
  themes by suite import.
- Suite archives cannot include loose executable assets, arbitrary code, remote
  execution behavior, marketplace metadata, or remembered approvals.
- A visuals-only import can skip behavior-bearing ritual packs while importing
  the Canvas/theme portions into quarantine.

## Commands

```powershell
ritualist suite export --canvas-pack room.ritualistcanvas --theme-pack theme.ritualisttheme --ritual-pack setup.ritualistpack --out room.ritualistsuite
ritualist suite validate room.ritualistsuite --json
ritualist suite import room.ritualistsuite --json
ritualist suite import room.ritualistsuite --visuals-only
ritualist suite list-imports
```

There is intentionally no `suite enable` command. Enabling behavior remains a
separate recipe-pack review decision.
