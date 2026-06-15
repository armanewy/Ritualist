# Runtime v2 Concepts

Runtime v2 is the contract between recipe execution, run logs, and the GUI/Home
experience. It keeps Ritualist local-first and event-driven: runtime work happens
off the GUI thread, and Home updates from small runtime events instead of
polling logs or scanning recipes synchronously.

This document describes the target concepts for new runtime work. The current
v0.1 executor already emits step callbacks and writes run records; Runtime v2
formalizes the states, events, and control surface that future Home work should
use.

## Core Rules

- Recipes expose structured actions only. Do not add arbitrary recipe-supplied
  Python, shell snippets, or JavaScript.
- Imported or shared recipes must never run automatically. Listing, indexing,
  importing, displaying, or receiving runtime events cannot start execution.
- Runtime adapters may touch browsers, windows, processes, and files, but that
  work must run in a worker, service, or runtime thread, never on the GUI thread.
- GUI/Home consumes events and sends control requests. It does not directly call
  slow adapters, parse large recipe sets, scan run logs, or sleep.
- Safety gates stay in force: `desktop.click_text` requires
  `window_title_contains`, clicking visible text exactly equal to `Play` requires
  confirmation, and confirmation prompts must be explicit.
- Windows-specific imports stay lazy and inside adapter methods so tests and
  non-Windows runs remain portable.

## Run States

Runtime v2 treats a run as a state machine. A run has one active state at a time.

| State | Meaning |
| --- | --- |
| `idle` | No run is active. |
| `running` | A step is executing. |
| `waiting` | The run is waiting for a structured condition such as a window, file, process, or timer. |
| `paused` | No further recipe actions are being started because the user paused the run. |
| `confirming` | The run is blocked on an explicit user decision. |
| `stopping` | Stop was requested and the runtime is cancelling at the next safe point. |
| `success` | All required steps completed successfully, with optional failures represented as skipped steps. Terminal. |
| `stopped` | The user declined confirmation or requested Stop before completion. Terminal. |
| `failed` | A required step failed. Terminal. |
| `interrupted` | A previous process exited before finalizing its run record. Terminal after reconciliation. |

Valid control transitions:

- `idle -> running`
- `running -> waiting -> running`
- `running -> confirming -> running|stopped`
- `running|waiting|confirming -> paused -> running|waiting|confirming`
- `running|waiting|paused|confirming -> stopping -> stopped`
- `running -> success|failed`
- stale `running|waiting|paused|confirming|stopping` records may be reconciled to `interrupted`
  after process/heartbeat checks.

## Step States

Each executable step also has a state. Step state changes are user-visible and
must be emitted as ordered runtime events.

| State | Meaning |
| --- | --- |
| `pending` | The step has not started. |
| `running` | The handler is actively executing. |
| `waiting` | The step is waiting for a file, path, process, window, browser text, timer, or user confirmation. |
| `paused` | The run is paused while this step is active. |
| `confirming` | The step is blocked on an explicit user decision. |
| `success` | The step completed. Terminal for the step. |
| `failed` | A required step failed. Terminal for the step and normally for the run. |
| `cancelled` | The user declined confirmation or Stop cancelled the step. Terminal for the step. |
| `skipped` | An optional step failed and the run continued. Terminal for the step. |

The current executor still writes `dry-run` as a legacy step result status in
`steps.jsonl`. Runtime v2 state models keep dry-run behavior as run metadata and
terminal step outcomes rather than as a separate step state.

State transitions that affect correctness must not be coalesced away. Progress
inside a long `waiting` state can be coalesced.

## Runtime Events

Runtime events are the source of truth for active Home state. They should be
small, structured, fast to apply, and safe to log.

Every event includes:

- `type`, such as `run.state_changed`.
- `run_id`.
- `sequence`, monotonically increasing within a run.
- `occurred_at`, preferably UTC ISO 8601.
- event-specific state fields, such as `state`, `previous_state`,
  `run_state`, or `step_state`.
- step-scoped fields such as `step_index`, `step_name`, and `action` when
  relevant.
- a short redacted `message` where useful for UI display.

Common event types:

| Event | Purpose |
| --- | --- |
| `run.started` | A run record/control object exists and execution started. |
| `run.state_changed` | The run entered a new state. |
| `step.started` | A step entered active execution. |
| `step.waiting` | A wait node began or remains waiting. |
| `step.paused` | A step is paused. |
| `step.resumed` | A paused step resumed. |
| `confirmation.requested` | The runtime needs an explicit user decision. |
| `confirmation.resolved` | The user accepted, declined, or Stop rejected the pending action. |
| `step.finished` | A step reached a terminal step state. |
| `log.message` | Non-fatal runtime information, such as overlay unavailable. |
| `heartbeat` | Liveness and current state while a run is active. |
| `run.finished` | Terminal run summary is available. |

Do not put secrets, cookies, page contents, screenshots, full URLs with tokens,
or broad environment dumps in runtime events. Event handlers must not execute
recipes or trigger adapter actions as side effects.

## RuntimeControl

`RuntimeControl` is the control plane for one active run. It is owned by the
runtime worker/service and exposed to the GUI/Home as a narrow, non-blocking API.

Current control requests:

- `pause()` requests a cooperative pause and returns quickly.
- `resume()` wakes a paused run.
- `stop()` requests cancellation and returns quickly.
- `is_paused()` returns the current pause flag.
- `is_stopping()` returns whether Stop has been requested.
- `wait_if_paused()` blocks only the runtime worker until Resume or Stop.
- `raise_if_stopped()` raises a clear stopped-run exception.
- `heartbeat()` gives long waits a single cooperative checkpoint for pause/stop.

`RuntimeControl` is not a remote command channel, plugin surface, or arbitrary
automation API. It only controls a run that the local user explicitly started.
It must not accept recipe-provided code or network-sourced commands.

Controls should be idempotent where practical:

- Calling `pause()` while already paused keeps the run paused.
- Calling `resume()` while running has no effect.
- Calling `stop()` multiple times keeps the run on the stopping/stopped path.

## Cooperative Pause And Resume

Pause/resume is cooperative. Runtime v2 does not kill an adapter in the middle of
an unsafe operation. Instead:

- The runtime checks control requests before starting each step.
- Wait nodes check control requests between polls or event waits.
- Confirmation waits remain responsive to Stop and Resume/Pause state changes.
- Long adapter calls should use adapter-level cancellation or bounded waits when
  available; otherwise pause takes effect after the call returns.
- While paused, the runtime emits `run.state_changed` with `state: paused` and keeps enough
  heartbeat/state alive for Home to show that the run is intentionally paused.
- Stop must remain available while paused.
- Wait timeout budgets should exclude time spent in `paused` so pausing a long
  wait does not accidentally consume its timeout.

Resume returns the active step to `waiting` or `running` and emits state changes
before doing more work.

## Wait Nodes

A wait node is any runtime step or sub-step that blocks until a condition is met,
the timeout expires, the user answers, or Stop cancels the run. Wait nodes keep
the recipe structured; they are not scripts.

Examples include:

- `assert.file_exists` or `assert.path_exists` with `timeout_seconds`.
- `app.wait_process`.
- `window.wait`.
- `assert.window_exists`, `assert.window_text_visible`, or
  `assert.browser_text_visible`.
- `confirm.ask` and `desktop.click_text` confirmation gates.

Wait node rules:

- Run off the GUI thread.
- Emit `step.waiting` and a terminal `step.finished`.
- Emit coalesced `heartbeat` or `log.message` events for visible timers or progress text.
- Poll with bounded intervals or adapter-native waits so Pause/Stop can be
  noticed promptly.
- Preserve safety gates. Waiting for text or a window is read-only; clicking or
  typing still requires the existing structured action and confirmation policy.
- Use fake adapters in tests. Tests must not require a Windows desktop session.

## GUI/Home Relationship

Home is a projection of runtime state. It should be able to render active runs,
recipe cards, Pause/Resume/Stop controls, confirmations, and recent outcomes
from events plus already-loaded state.

Responsibilities:

- Runtime emits ordered events and writes run logs.
- Home subscribes to events and applies small incremental updates keyed by
  `run_id`, `recipe_id`, and `step_id`.
- Home sends Pause, Resume, Stop, and confirmation answers through
  `RuntimeControl`.
- Background services may reconcile or load run history, then publish results
  back to Home; the GUI thread does not scan `runs/` synchronously.
- Runtime events may update card status, badges, progress rows, and waiting HUDs.
  They must never start imported/shared recipes automatically.

The current Qt GUI follows this shape by running `WorkflowExecutor` on
`RunnerThread`, forwarding step events through Qt signals, and answering
confirmations from the GUI. Runtime v2 should keep that split as Home becomes
more event-driven.

## No UI-Thread Blocking

The GUI thread is for rendering, input, and applying already-computed state. It
must not perform slow runtime work.

Forbidden on the GUI thread:

- Playwright calls.
- Windows UI Automation scanning.
- YAML parsing across many files.
- Large image decoding.
- Run-log scanning or stale-run reconciliation.
- Subprocess waits.
- Sleeps or polling loops.

If a UI action needs slow work, dispatch it to a worker/service/runtime component
and return control to the GUI immediately. Progress must come back through
runtime events or queued model updates. Pause and Stop should remain responsive
even when adapters are busy; the performance target is under 100 ms for visible
control feedback.

## Examples

### Waiting For A File

Recipe shape:

```yaml
preflight:
  - name: Wait for exported settings
    action: assert.file_exists
    path: "%USERPROFILE%\\Documents\\Ritualist\\exports\\settings.json"
    timeout_seconds: 60
```

Runtime sequence:

1. `step.started` with `state: running`.
2. `step.waiting` with kind `file_exists` and a redacted/display path.
3. Coalesced `heartbeat` or `log.message` events update elapsed/remaining time.
4. If the file appears, `step.finished` with `state: success`.
5. If the timeout expires, the step becomes `failed`, unless it was optional, in
   which case it becomes `skipped`.

The file checks run in the runtime worker, not Home. Home only applies the wait
events to status text or a waiting indicator.

### Waiting For User

Recipe shape:

```yaml
steps:
  - name: Confirm monitor change
    action: confirm.ask
    prompt: Switch to the gaming monitor profile?
```

Runtime sequence:

1. The step enters `confirming`.
2. Runtime emits `confirmation.requested` with a `confirmation_id`.
3. Home shows the prompt and returns immediately to the event loop.
4. The user decision is sent through the runtime confirmation channel.
5. Accepted continues the step to `success`; declined moves the step to
   `cancelled` and the run to `stopped`.

The GUI does not block waiting for the answer. A worker or runtime wait object
waits for the control response and continues to heartbeat.

### Pausing During Wait

Scenario: a `window.wait` step is waiting for a local launcher window.

Runtime sequence:

1. Step enters `waiting`; Home shows "Waiting for Battle.net..." from
   `step.waiting`.
2. The user presses Pause. Home calls `RuntimeControl.pause()` and immediately
   disables Pause/enables Resume.
3. The wait node observes the pause request between polls, emits
   `run.state_changed` with `state: paused` and `step.paused`, and stops
   spending timeout budget.
4. The user presses Resume. Home calls `RuntimeControl.resume()`.
5. Runtime returns the step to `waiting` and continues the
   window wait with the remaining active timeout.
6. If the window appears, the step finishes `success`.

Stop remains available the whole time. If Stop is pressed while paused, the run
goes to `stopping` then `stopped`.

### Stop During Confirmation

Scenario: a recipe reaches a guarded `desktop.click_text` step targeting visible
text exactly equal to `Play`.

Recipe shape:

```yaml
steps:
  - name: Ask before Play
    action: desktop.click_text
    text: Play
    window_title_contains: Battle.net
    requires_confirmation: true
```

Runtime sequence:

1. The runtime may emit an action preview event, then enters
   `confirming`.
2. Home shows the confirmation prompt. No click has happened yet.
3. The user presses Stop instead of accepting. Home calls
   `RuntimeControl.stop()` and resolves the pending confirmation as declined.
4. Runtime emits `confirmation.resolved` with `approved: false`,
   `step.finished` with `state: cancelled`, `run.state_changed` with
   `state: stopped`, and `run.finished`.
5. The desktop click is never executed.

This preserves the existing safety rule: a `Play` click requires explicit
confirmation, and Stop during that confirmation must take the safe path.
