# North-Star Packaged Dogfood

This note tracks the packaged north-star acceptance flow. It is intentionally
evidence-driven: a check is `PASS` only when the harness writes structured
machine evidence, and ambiguous visual/taskbar claims stay
`NEEDS_HUMAN_REVIEW`.

## Flow

The packaged acceptance harness covers this north-star path:

1. Open non-fullscreen Room picker.
2. Open Gaming Room, Project Room, and Support Desk on Desktop Work-Area.
3. Confirm taskbar-preserving bounds and wallpaper passthrough where observable.
4. Exercise Gaming state lifecycle, confirmation decline, no auto-run, and
   hard-kill recovery with fake adapters and fixture windows.
5. Exercise Project Room ritual and shortcut controls without VS Code,
   Terminal, or external docs dependencies.
6. Exercise Support Desk dry-run workflows without VPN software, support
   portals, or account logins.
7. Enable Local Learning only with explicit local source consent.
8. Produce fixture journal events.
9. Scan Suggestions on demand.
10. Confirm repeated folder-only activity becomes a reviewed shortcut draft.
11. Confirm repeated multi-step activity becomes a disabled ritual draft.
12. Review and create drafts without installing, enabling, writing recipe files,
    or running behavior.
13. Confirm no run logs are created by Suggestions or Suite Pack import.
14. Delete local learning journal and suggestion data.
15. Import a Suite Pack into quarantine.
16. Confirm Suite Pack visual contents stay quarantined and ritual contents stay
    disabled with `auto_run=false` and `auto_enable=false`.
17. Confirm blank-area click-through remains honestly unimplemented rather than
    faked by coordinate input.

## Evidence Boundaries

- The harness uses isolated fixture app data under
  `artifacts\release-acceptance\evidence\fixtures`.
- The harness does not use real VS Code, Terminal, Battle.net, VPN software,
  support portals, game login, browser history, screenshots/OCR as learning
  sources, global hooks, keylogging, Watch Me, recording, or coordinate capture.
- Suite Pack import evidence is quarantine-only. There is no enable command in
  the acceptance path.
- Click-through remains a limitation. The Desktop Work-Area evidence must keep
  `click_through_implemented=false`,
  `blank_area_click_through_machine_verified=false`, and
  `blank_area_click_through_status=NEEDS_HUMAN_REVIEW`.

## Current Evidence

The latest local packaged run in this branch used:

```powershell
.\scripts\ritualist_release_acceptance.ps1 -Packaged -RecordScreen -EvidenceDir artifacts\release-acceptance
```

It produced `31 PASS`, `0 FAIL`, and `0 NEEDS_HUMAN_REVIEW` in
`artifacts\release-acceptance\acceptance-summary.json`. No tag was created.
