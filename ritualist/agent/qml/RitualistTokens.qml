import QtQuick

QtObject {
    id: tokens

    readonly property string contractId: "ritualist.agent.quiet_instrument.v1"
    readonly property string baseThemeId: "ritualist.paper"
    readonly property string fontFamily: "Segoe UI Variable"
    readonly property string fallbackFontFamily: "Segoe UI"
    readonly property int minFontEpx: 12
    readonly property int bodyFontEpx: 13
    readonly property int captionFontEpx: 12
    readonly property int titleFontEpx: 18
    readonly property string textCase: "sentence case"

    readonly property color canvas: "#f6f2ea"
    readonly property color shell: "#fbf8f2"
    readonly property color panel: "#ffffff"
    readonly property color panelAlt: "#f0ebe2"
    readonly property color panelMuted: "#ebe4d8"
    readonly property color text: "#24211c"
    readonly property color textMuted: "#675f53"
    readonly property color border: "#d8d0c3"
    readonly property color borderStrong: "#bfb5a6"
    readonly property color focusRing: "#1d5f99"
    readonly property color accent: "#2f6f8f"
    readonly property color onAccent: "#ffffff"

    readonly property color running: "#2f6f8f"
    readonly property color runningPanel: "#e7f1f5"
    readonly property color waiting: "#8a6a1f"
    readonly property color waitingPanel: "#fff3d8"
    readonly property color confirmation: "#2f7d57"
    readonly property color confirmationPanel: "#eaf7ee"
    readonly property color failure: "#a23a3a"
    readonly property color failurePanel: "#fdeaea"
    readonly property color recovery: "#4f6f8f"
    readonly property color recoveryPanel: "#e8f2f0"

    readonly property int baseEpx: 4
    readonly property int spaceXs: 4
    readonly property int spaceSm: 8
    readonly property int spaceMd: 12
    readonly property int spaceLg: 16
    readonly property int spaceXl: 24
    readonly property int spaceXxl: 32
    readonly property int outerRadiusEpx: 10
    readonly property int controlRadiusEpx: 6
    readonly property int primaryHitTargetEpx: 40

    readonly property color outerShadowColor: "#26000000"
    readonly property int outerShadowBlurEpx: 24
    readonly property int outerShadowYOffsetEpx: 10

    readonly property int flyoutDurationMs: 140
    readonly property int flyoutDurationMinMs: 120
    readonly property int flyoutDurationMaxMs: 160
    readonly property int stateDurationMs: 200
    readonly property int stateDurationMinMs: 180
    readonly property int stateDurationMaxMs: 220
    readonly property int reducedMotionDurationMs: 0
    readonly property int reducedMotionFadeMs: 60
    readonly property real disabledOpacity: 0.56

    function duration(kind, reducedMotion) {
        if (reducedMotion && kind === "fade") {
            return reducedMotionFadeMs
        }
        if (reducedMotion) {
            return reducedMotionDurationMs
        }
        if (kind === "flyout") {
            return flyoutDurationMs
        }
        return stateDurationMs
    }

    function semanticColor(state) {
        if (state === "running") {
            return running
        }
        if (state === "waiting") {
            return waiting
        }
        if (state === "confirmation") {
            return confirmation
        }
        if (state === "failure") {
            return failure
        }
        if (state === "recovery") {
            return recovery
        }
        return textMuted
    }

    function semanticPanel(state) {
        if (state === "running") {
            return runningPanel
        }
        if (state === "waiting") {
            return waitingPanel
        }
        if (state === "confirmation") {
            return confirmationPanel
        }
        if (state === "failure") {
            return failurePanel
        }
        if (state === "recovery") {
            return recoveryPanel
        }
        return panelAlt
    }

    function buttonBackground(role, enabled, hovered, down) {
        if (!enabled) {
            return panelAlt
        }
        if (role === "primary") {
            return down ? focusRing : (hovered ? "#286681" : accent)
        }
        if (role === "confirmation") {
            return down || hovered ? "#286d4c" : confirmation
        }
        if (role === "danger") {
            return down || hovered ? failurePanel : panel
        }
        return down || hovered ? panelAlt : panel
    }

    function buttonText(role, enabled) {
        if (!enabled) {
            return textMuted
        }
        if (role === "primary" || role === "confirmation") {
            return onAccent
        }
        if (role === "danger") {
            return failure
        }
        return text
    }

    function buttonBorder(role, enabled, focused) {
        if (focused) {
            return focusRing
        }
        if (!enabled) {
            return border
        }
        if (role === "primary") {
            return accent
        }
        if (role === "confirmation") {
            return confirmation
        }
        if (role === "danger") {
            return failure
        }
        return border
    }
}
