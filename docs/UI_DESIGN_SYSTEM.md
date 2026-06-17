# Ritualist UI Design System Plan

The Room UI should make Ritualist feel like a local, visible, policy-gated
desktop command surface rather than a generic card dashboard. The design system
must start with built-in components, declarative tokens, and measurable
performance budgets before visual polish expands.

## Product Frame

- User-facing term: Room.
- Implementation term: Canvas.
- Room Builder is the product-facing name for Canvas Edit Mode.
- Use Mode is the live Room surface.
- Run Mode is the active ritual state with status, controls, and logs.

## Component Families

The first design-system pass should standardize existing built-in component
families:

- `ritual.card`
- `ritual.status`
- `ritual.controller`
- `target.card`
- `recent.activity`
- dock/category components
- clock/text/image components when already supported safely

New visual variants must not add new automation capability. Variants should
change presentation, density, and hierarchy only.

## Style Schema

Component style schema should be declarative and typed:

- `variant`: built-in values such as `hero`, `standard`, `compact`
- `accent`: reference to a theme token, not arbitrary code
- `radius`: token reference or bounded numeric value
- `shadow`: token reference or built-in shadow level
- `density`: built-in values such as `comfortable` or `compact`
- `state_style`: built-in runtime states only

Component overrides should be validated before render and before save. Unknown
or executable-looking fields must be rejected.

## Runtime State Styling

State styling must remain clear for:

- ready
- running
- waiting
- confirming
- paused
- stopping
- stopped
- failed
- interrupted

Confirmation and risky-action states need stronger visual treatment than normal
status updates. Risk surfaces should be visible without relying on color alone.

## Accessibility And Contrast

Validation should check at least:

- text on surface
- muted text on surface
- text on accent
- warning/danger/success badge text
- focus ring visibility

Low contrast should produce warnings by default. Malformed or unsafe values
should produce errors.

## Performance Budgets

Every component should have a lightweight performance profile:

- update rate: `static`, `low`, `medium`, `high`
- image usage
- animation usage
- estimated cost: `low`, `medium`, `high`

The UI should record budgets for 100 and 300 component scenarios before adding
heavier visuals. Low-resource mode can be schema/config first; it should not
auto-detect games or fullscreen windows unless a safe foundation already exists.

## Testing Strategy

Use these evidence layers:

- unit tests for schema and token validation
- CLI validation for themes, canvases, and perf
- packaged acceptance harness for launch, runtime controls, confirmations,
  recovery, screenshots, window trees, and runtime events
- screenshot/frame evidence for visual review

Ambiguous smoothness or subjective visual quality remains `NEEDS_HUMAN_REVIEW`
until there is a reliable machine oracle.

## Out Of Scope

The design system must not introduce arbitrary user-supplied QML/HTML/JS/Python,
remote execution, marketplace behavior, shell replacement, taskbar hiding,
kiosk mode, password automation, coordinate clicks in product runtime, or
gameplay automation.
