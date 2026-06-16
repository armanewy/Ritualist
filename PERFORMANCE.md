# Ritualist Performance Contract

Ritualist is a local-first desktop app. Runtime work can touch browsers, native windows, run logs, and recipe files, but the Home UI must stay responsive while that work happens. This contract defines the rules and budgets for changes that affect startup, Home, cards, run status, logging, and runtime events.

## Performance Non-Negotiables

- Keep slow work off the GUI thread.
- Prefer event-driven updates over polling.
- Keep imported and shared recipes inert until the user explicitly chooses to run them.
- Preserve confirmation gates for risky desktop actions.
- Keep Windows-specific imports lazy and inside adapter methods.
- Keep tests portable and independent of a Windows desktop session.

## UI Thread Rules

The UI thread is for rendering, input handling, and applying already-computed state. It must not perform blocking runtime, filesystem, adapter, or process work.

Explicitly forbidden UI-thread work:

- Playwright calls.
- Windows UI Automation scanning.
- YAML parsing across many files.
- Image decoding of large assets.
- Run-log scanning.
- Subprocess waits.
- Sleeps.

If a UI action needs any of that work, dispatch it to a worker, service, or already-running runtime component and return control to the UI immediately. Report progress back through events or queued state updates.

## Runtime Event Rules

Runtime events are the bridge between workflow execution and UI state. They should be small, structured, and fast to apply.

- Emit events when run state changes instead of requiring Home to poll run logs.
- Include enough data for the UI to update affected cards or status rows without reloading broad state.
- Coalesce noisy progress updates where possible.
- Do not block runtime cancellation paths while formatting logs or refreshing Home data.
- Pause and Stop must travel through a responsive control path that is independent from slow adapter work.
- Imported or shared recipes must never run automatically as a side effect of event handling, indexing, or display.

## Event Coalescing Helper

Use `ritualist.event_coalescing.EventCoalescer` for noisy UI-facing updates such as progress ticks, wait timers, or repeated status refreshes. It keeps only the newest state for each key, emits at a bounded target rate, and can be flushed explicitly when a final state must be delivered.

- The default target is 60 Hz.
- Prefer 30-60 Hz for UI updates.
- Coalesce progress-style events, not state transitions that must be observed individually.
- Keep the helper GUI-independent so it remains unit-testable without a display server.

## QML and Home Performance Rules

Home should behave like a resident console dashboard: showing, hiding, and moving through cards should feel immediate.

- Keep Home data models resident where practical.
- Avoid rebuilding the full card model for narrow status changes.
- Avoid synchronous file scans while showing Home.
- Avoid blocking QML bindings, delegates, and signal handlers with heavy JavaScript or Python callbacks.
- Prefer incremental model updates keyed by recipe id or run id.
- Keep animations cheap and interruptible.
- Preserve keyboard, gamepad, and pointer input responsiveness during runtime activity.

## Card Asset Rules

Card visuals should be predictable, bounded, and cheap to present.

- Use stable asset dimensions so cards do not relayout after images load.
- Keep large image decoding off the UI thread.
- Prepare Home card images through `ritualist.home.assets.HomeThumbnailCache` and pass QML only cached local thumbnail URLs or an empty image value.
- Build thumbnails from a worker, setup task, or other non-GUI path; `ensure_thumbnail()` may decode image data and must not run from QML bindings or UI signal handlers.
- The default Home thumbnail bound is 512x288. Increase it only with a measured reason and keep dimensions explicit.
- Cache decoded or scaled assets when cards are reused.
- Prefer pre-sized thumbnails for Home cards.
- Avoid loading remote assets. Ritualist should remain local-first.
- Missing or invalid assets should fall back quickly without blocking card rendering.
- Animated card backgrounds are intentionally out of scope for now.

## Logging and Run-History Loading Rules

Logs and run history are append-heavy runtime data. The UI should not scan them synchronously.

- Write runtime logs incrementally without blocking cancellation controls.
- Load recent run history through bounded queries or background workers.
- Avoid scanning every run directory to render Home.
- Repair stale run records outside the initial Home render path.
- Keep log formatting and redaction out of latency-sensitive UI handlers.
- Prefer explicit runtime events for fresh status over reading run logs back from disk.

## Performance Budgets

These are targets for review and regression testing. They are not excuses to block the UI until the budget is exhausted.

| Interaction | Target |
| --- | ---: |
| Home show/hide when resident | <100ms |
| Card input response | <50ms |
| UI status update after runtime event | <100ms |
| Pause/Stop response | <100ms |
| Frame rate | 60 FPS |
| Frame budget | 16.67ms |
| Cold packaged visible window | <2s soft target |

When a change cannot reasonably meet a budget, document the tradeoff in the pull request or issue and keep the slow work outside the UI thread.
