# Setpiece Theme Tokens

Theme tokens are declarative visual data for built-in Setpiece UI surfaces.
They are not executable code and must not load arbitrary QML, HTML, JavaScript,
or Python.

## Theme Document Model

Initial theme documents should use a typed YAML shape:

```yaml
schema: setpiece.theme.v1
id: setpiece.paper
name: Setpiece Paper
version: 0.1.0
tokens:
  color.background: "#f6f2ea"
assets: {}
component_variants: {}
```

All values must validate before a theme can be used. Remote asset URLs are out
of scope. Asset references must resolve inside the theme pack.

## Token Categories

Start with these namespaces:

- `color.*`
- `font.*`
- `radius.*`
- `spacing.*`
- `shadow.*`
- `motion.*`
- `opacity.*`
- `material.*`

Token values should be typed. Colors should be validated as supported color
strings. Numeric values should have bounded ranges. Token references should be
explicit and acyclic.

## Inheritance Order

Resolved style should follow this order:

1. app defaults
2. selected theme
3. canvas overrides
4. component variant
5. component overrides
6. runtime state styling

Missing optional tokens fall back to app defaults. Missing required tokens,
recursive references, malformed values, or unsafe fields produce diagnostics.

## Theme Pack Format

A Theme Pack contains:

- `theme.yaml`
- local visual assets
- optional metadata

A Theme Pack must not contain behavior bindings, recipes, executable code,
remote URLs, arbitrary custom components, or auto-run hooks. Importing a theme
must never run behavior.

## Canvas And Room Format

Canvas files remain the implementation format. Room-facing metadata can be added
without renaming the core schema:

```yaml
room:
  name: Gaming Room
  description: Setup and control a gaming session safely.
theme: setpiece.paper
components: []
```

Canvas validation should treat `room` metadata as product-facing presentation
data and continue to validate behavior through existing policy gates.

## Snapshot And Perf Evidence

Theme changes should be accompanied by:

- theme validation JSON
- canvas validation JSON
- 100/300 component perf output
- packaged acceptance screenshots or frame captures when UI rendering changes

Visual ambiguity remains a human-review item until there is a reliable oracle.
