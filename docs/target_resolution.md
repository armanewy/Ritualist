# Target Resolution Engine

Target Resolution v1 lets Setpiece answer, "what local evidence says this
target can be started?" It is a deterministic discovery and planning layer on
top of the Primitive Kernel. It is not a launcher-specific feature, not AI
planning, and not an installer.

The current pipeline is:

```text
target id or alias -> TargetSpec -> read-only providers -> TargetResolutionResult -> PrimitivePlan preview -> Doctor/policy report
```

Discovery is read-only. It must not launch apps, click UI, install software,
download installers, type passwords, or mutate local state.

## Target Models

The target layer exposes:

- `TargetSpec`
- `TargetIdentity`
- `TargetAlias`
- `TargetHint`
- `TargetCandidate`
- `TargetProvider`
- `TargetState`
- `TargetTransition`
- `TargetResolutionResult`
- `TargetProviderResult`
- `TargetMemoryRecord`
- `TargetPlanSummary`

`TargetPlanSummary` is the small Home-facing model. It includes the target
state, best candidate summary, risk summary, confirmation count, unresolved
questions, recommended next action, and prior local source when user memory was
used.

## States

v1 can represent:

- `unknown`
- `not_found`
- `running`
- `launchable`
- `launcher_missing`
- `launcher_available`
- `login_required`
- `install_source_available`
- `install_media_present`
- `install_available`
- `installing`
- `update_available`
- `updating`
- `ready`
- `launching`
- `blocked`
- `failed`

Most states are descriptive in v1. Only running and launchable candidates can
compile into focus/launch plan steps. Installer, update, media, and login states
compile to human handoff or unresolved questions.

## Providers

Read-only providers currently include:

- `RunningProcessProvider` through `app.process`
- `StartMenuShortcutProvider`
- `DesktopShortcutProvider`
- `ExecutablePathProvider`
- `InstalledAppsProvider`
- `RemovableMediaProvider`
- `UserMemoryProvider`

Providers return candidates with evidence. Candidate ranking is deterministic:
state priority first, then provider priority, confidence, and label. User memory
is preferred over generic shortcut/path providers when both are equivalent,
because it records a prior successful local path. If equally plausible
candidates remain ambiguous, the compiled plan asks the user to choose instead
of silently selecting one.

## Built-In Catalog

The built-in catalog includes `diablo_iv`:

```yaml
id: diablo_iv
kind: game
display_name: Diablo IV
aliases:
  - Diablo 4
  - D4
hints:
  executable_names:
    - Diablo IV.exe
  window_titles:
    - Diablo IV
  shortcut_names:
    - Diablo IV
  media_volume_labels:
    - DIABLO_IV
    - DIABLO4
  launcher_hints:
    - battle_net
```

`launcher_hints` are metadata only. Battle.net is not a user-facing target
action, not a special provider, and not a bespoke automation path.

## CLI

Use discovery when you want local evidence:

```powershell
python -m setpiece target discover diablo_iv --json
```

Use target plan when you want a side-effect-free primitive plan preview:

```powershell
python -m setpiece target plan diablo_iv --json
```

Use Intent Plan preview when Home-style intent routing is desired:

```powershell
python -m setpiece plan preview target.start:diablo_iv --json
```

Use Doctor for target plan compatibility:

```powershell
python -m setpiece doctor target:diablo_iv --json --no-strict
```

All of these commands are preview/diagnostic operations. They do not execute
the plan.

## Safety Boundaries

Target Resolution v1 does not add:

- launcher-specific user-facing actions
- automatic installer execution
- automatic updates
- browser downloads
- password/login automation
- arbitrary Python, shell, PowerShell, or JavaScript
- coordinate clicks
- remote execution
- cloud sync
- marketplace behavior
- gameplay automation

If a target is not found, Setpiece should suggest choosing a local executable
or shortcut, inserting media, inspecting visible windows, or using future local,
review-only Ritual Suggestions from consented Activity Signals. It must not
infer a download URL, silently install anything, or rely on recording.
