# Live Gaming Acceptance

This procedure is the opt-in live integration companion to the packaged fixture acceptance suite. It is only for the real Windows desktop when an operator deliberately arranges one Gaming state at a time.

Fixture acceptance is not live integration. A fake Battle.net window can prove Setpiece contracts, but it cannot prove real Battle.net, Chrome, YouTube, or Diablo IV behavior.

## Safety Contract

The live harness:

- requires `-Live -IUnderstandThisIsLive`
- never enters credentials
- never installs, locates, or updates Diablo IV
- never automates gameplay
- never uses coordinate clicks
- never sends synthetic keyboard input
- records read-only process, window, UI Automation, run-log, screenshot, and human-note evidence

## Command

```powershell
.\scripts\setpiece_live_gaming_acceptance.ps1 -Live -IUnderstandThisIsLive -Case play_enabled -RecordScreen -HumanNotes "Battle.net showed Diablo IV Play enabled before running Gaming Mode."
```

Use one case per desktop state where possible. The script writes:

- `artifacts\live-gaming-acceptance\live-gaming-summary.json`
- `artifacts\live-gaming-acceptance\live-gaming-summary.md`
- `artifacts\live-gaming-acceptance\evidence\process-tree.json`
- `artifacts\live-gaming-acceptance\evidence\window-tree.json`
- `artifacts\live-gaming-acceptance\evidence\battlenet-uia-tree.json`
- `artifacts\live-gaming-acceptance\evidence\commands\runs-no-repair.txt`

## Cases

The live case schema is in `tests\acceptance\live_gaming_v0_2_alpha_1.yaml`.

Cases cover Battle.net absent, login required, Install visible, Locate the game visible, Update visible/updating, Play visible but disabled, Play enabled, target disappears after approval, Diablo already running, approved Play succeeds, postcondition fails, native browser handoff, managed browser selected, managed media starts, managed media stalls, optional ambience failure, and no premature minimize.

Most cases remain `NEEDS_HUMAN_REVIEW` because the harness captures evidence without mutating the desktop. A `PASS` requires the evidence and human observation to match the case rule. `v0.2.0-alpha.1` is not taggable from fixture acceptance alone.
