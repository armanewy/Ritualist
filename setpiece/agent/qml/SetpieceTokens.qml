import QtQuick

QtObject {
    id: tokens

    readonly property string contractId: "setpiece.agent.quiet_instrument.v1"
    readonly property string baseThemeId: "setpiece.paper"
    readonly property string fontFamily: "Segoe UI Variable"
    readonly property string fallbackFontFamily: "Segoe UI"
    readonly property int minFontEpx: 12
    readonly property int bodyFontEpx: 13
    readonly property int captionFontEpx: 12
    readonly property int titleFontEpx: 18
    readonly property string textCase: "sentence case"

    readonly property color canvas: "#F7F4EE"
    readonly property color shell: "#FFFFFF"
    readonly property color panel: "#FFFFFF"
    readonly property color panelAlt: "#DDE7E8"
    readonly property color panelMuted: "#DDE7E8"
    readonly property color text: "#22272B"
    readonly property color textMuted: "#687278"
    readonly property color border: "#DDE7E8"
    readonly property color borderStrong: "#70777C"
    readonly property color focusRing: "#3C6F82"
    readonly property color accent: "#3C6F82"
    readonly property color onAccent: "#FFFFFF"

    readonly property color running: "#3C6F82"
    readonly property color runningPanel: "#DDE7E8"
    readonly property color waiting: "#A36B25"
    readonly property color waitingPanel: "#F7F4EE"
    readonly property color confirmation: "#6E5A8A"
    readonly property color confirmationPanel: "#DDE7E8"
    readonly property color failure: "#A84942"
    readonly property color failurePanel: "#F7F4EE"
    readonly property color recovery: "#45715F"
    readonly property color recoveryPanel: "#DDE7E8"

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
            return down ? "#243A43" : (hovered ? "#243A43" : accent)
        }
        if (role === "confirmation") {
            return down || hovered ? "#5f4d78" : confirmation
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
