# Setpiece identity kit — v1

## Brand idea

**Setpiece** means a carefully arranged, repeatable sequence of coordinated actions.

The mark uses two opposing pieces that settle around a central cue. Together they create an abstract **S**, an open path, and a stable container for operational state.

**Tagline:** Everything in place. Ready to run.

## Included

- Primary, reverse, stacked, monochrome, and wordmark SVG/PNG assets
- Windows application icon master, PNG size set, and multi-resolution ICO
- Tray icons for Ready, Running, Waiting, Confirmation, Failure, Recovery, Paused, and Stopped
- Light-background, dark-background, black, and white tray variants
- Favicon, social avatar, documentation header, social card, and optional package/file icon
- Motion storyboard and restrained logo-assembly GIF
- Contact sheet, design tokens, and implementation manifest

## Logo behavior

The two outer pieces never change. They are the product identity. The center cue may change only when the mark is functioning as an operational status icon.

Use the static diamond cue for all brand, marketing, installer, documentation, and Store contexts.

## Tray mapping

| State | Center cue | Persistent tray use |
|---|---|---|
| Ready | Diamond | Yes |
| Running | Play | Yes |
| Waiting | Ellipsis | Yes |
| Confirmation | Exclamation | Yes |
| Failure | X | Yes |
| Recovery | Return arrow | Yes |
| Paused | Pause bars | Yes, when explicitly paused |
| Stopped | Square | No by default; return to Ready after the run is recorded |

A non-blocking warning remains in the tooltip or flyout. A warning requiring action maps to Confirmation. Completion returns to Ready.

## Tray theme selection

- `for_light_background`: dark outer mark with semantic center cue
- `for_dark_background`: light outer mark with brighter semantic center cue
- `monochrome_black` and `monochrome_white`: High Contrast and fallback assets

The tooltip remains authoritative. The icon communicates only broad state and urgency.

## Clear space and minimum size

- Brand lockups: clear space equal to the center diamond's diagonal on all sides.
- Symbol-only brand use: 20 px minimum for ordinary digital use.
- Tray use: supplied exact-size assets down to 16 px.
- Do not mechanically shrink the plated application icon into the tray.

## Typography

- Wordmark: outlined Inter Display Medium with a custom diamond over the `i`.
- Product UI: Segoe UI Variable.
- Paths, timestamps, and diagnostics: Cascadia Mono.

Font files are not included.

## Color

The identity is primarily graphite, warm paper, and mineral blue. State colors are secondary and never carry meaning alone.

## Motion

The brand motion is an assembly, not a performance:

1. The upper piece establishes position.
2. The lower piece settles opposite it.
3. The center cue appears.
4. The mark rests.

Target duration: 520–680 ms. Use once on onboarding, About, or launch marketing. Never animate continuously in the notification area.

## Interface icon policy

Use this custom family only for:

- Product identity
- Tray state
- Application/installer/Store icon
- Notification identity
- Optional Setpiece package/file type

Use Segoe Fluent Icons for ordinary actions such as Open, Edit, Settings, Retry, Delete, Pause, and Search.

## Prohibited treatments

- Film frames, clapperboards, cameras, curtains, spotlights, or “take” language
- Gamer neon, glow, chromatic aberration, or RGB effects
- Arbitrary gradients or glass effects
- A play triangle as the standalone logo
- State communicated through color alone
- Distortion, rotation, outline changes, or adding badges to the outer pieces
- Decorative animation in the tray

## Windows production notes

The kit includes exact tray sizes at 16, 20, 24, 32, 40, 48, and 64 px and a Windows ICO with 16, 24, 32, 48, and 256 px application assets. Select light/dark tray assets based on the actual taskbar background and provide black/white fallbacks for High Contrast.

Sources consulted for Windows production requirements:

- Microsoft Learn — Construct your Windows app's icon: https://learn.microsoft.com/windows/apps/design/iconography/app-icon-construction
- Microsoft Learn — Notifications and the Notification Area: https://learn.microsoft.com/windows/win32/shell/notification-area
- Microsoft Learn — Design guidelines for Windows app icons: https://learn.microsoft.com/windows/apps/design/iconography/app-icon-design

## Status

This is a production-shaped **v1 direction**, not a legal trademark clearance. Run small-size recognition, state-comprehension, and confusion testing before freezing geometry.
