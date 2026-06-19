# Setpiece Suite Packs

Suite Packs (`.setpiecesuite`) are local whole-Room bundles. They are a wrapper
around existing pack types:

- one Canvas/Room pack (`.setpiececanvas`)
- optional Theme pack (`.setpiecetheme`)
- zero or more behavior-bearing Ritual packs (`.setpiecepack`)
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
setpiece suite export --canvas-pack room.setpiececanvas --theme-pack theme.setpiecetheme --ritual-pack setup.setpiecepack --out room.setpiecesuite
setpiece suite validate room.setpiecesuite --json
setpiece suite import room.setpiecesuite --json
setpiece suite import room.setpiecesuite --visuals-only
setpiece suite list-imports
```

There is intentionally no `suite enable` command. Enabling behavior remains a
separate recipe-pack review decision.
