import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Window

Window {
    id: root

    SetpieceTokens {
        id: tokens
    }

    property var instrumentController: typeof setpieceInstrumentController === "undefined" ? null : setpieceInstrumentController
    property var instrumentPayload: instrumentController && instrumentController.payload ? instrumentController.payload : ({
        "title": "Quiet Instrument",
        "state": "ready",
        "summary": "Ready when you are.",
        "steps": []
    })
    property bool collapsed: false
    property bool focusCollapseArmed: false
    property bool keepVisibleForRitual: false
    property bool technicalDetailsOpen: false
    property bool reducedMotion: instrumentPayload && instrumentPayload.reduced_motion === true
    property int defaultWidthEpx: 420
    property int expandedWidthEpx: 560
    property int collapsedWidthEpx: 112
    property real maxWorkAreaRatio: 0.70
    property int workAreaWidth: Screen.desktopAvailableWidth > 0 ? Screen.desktopAvailableWidth : Screen.width
    property int workAreaHeight: Screen.desktopAvailableHeight > 0 ? Screen.desktopAvailableHeight : Screen.height
    readonly property int maxSurfaceWidth: Math.floor(workAreaWidth * maxWorkAreaRatio)
    readonly property int maxSurfaceHeight: Math.floor(workAreaHeight * maxWorkAreaRatio)
    readonly property string currentState: normalizedState()
    readonly property bool expandedState: currentState === "failure" || currentState === "recovery" || technicalDetailsOpen
    readonly property int targetSurfaceWidth: expandedState ? expandedWidthEpx : defaultWidthEpx

    signal primaryActionRequested(string state)
    signal collapseRequested(string reason)
    signal expandRequested()
    signal technicalDetailsToggled(bool expanded)
    signal keepVisibleRequested(bool keepVisible)

    width: root.collapsed ? root.collapsedWidthEpx : Math.min(root.targetSurfaceWidth, root.maxSurfaceWidth)
    height: root.collapsed ? 104 : Math.min(root.expandedState ? 640 : 520, root.maxSurfaceHeight)
    minimumWidth: root.collapsed ? root.collapsedWidthEpx : Math.min(336, root.maxSurfaceWidth)
    maximumWidth: root.maxSurfaceWidth
    maximumHeight: root.maxSurfaceHeight
    visible: false
    flags: Qt.Window | Qt.FramelessWindowHint
    color: "transparent"
    title: "Setpiece Quiet Instrument"

    Behavior on width {
        NumberAnimation { duration: tokens.duration("flyout", root.reducedMotion) }
    }

    Behavior on height {
        NumberAnimation { duration: tokens.duration("flyout", root.reducedMotion) }
    }

    Shortcut {
        sequence: "Esc"
        context: Qt.WindowShortcut
        onActivated: root.collapse("escape")
    }

    function normalizedState() {
        var state = String(instrumentPayload.state || instrumentPayload.status || "ready").toLowerCase()
        if (state === "run" || state === "active" || state === "executing") {
            return "running"
        }
        if (state === "confirming" || state === "confirmation" || state === "blocked") {
            return "confirmation"
        }
        if (state === "failed" || state === "error") {
            return "failure"
        }
        if (state === "recovering" || state === "interrupted") {
            return "recovery"
        }
        if (state === "idle" || state === "queued") {
            return "ready"
        }
        return state
    }

    function titleText() {
        return instrumentPayload.title || instrumentPayload.name || "Quiet Instrument"
    }

    function stateLabel() {
        var state = root.currentState || "ready"
        return state.charAt(0).toUpperCase() + state.slice(1)
    }

    function summaryText() {
        return instrumentPayload.summary || instrumentPayload.message || instrumentPayload.description || "Ritual status is available."
    }

    function allSteps() {
        return instrumentPayload.steps || instrumentPayload.plan_steps || []
    }

    function stepStatus(step) {
        return String(step.status || step.state || "").toLowerCase()
    }

    function stepTitle(step, fallback) {
        if (!step) {
            return fallback
        }
        return step.title || step.name || step.label || step.summary || fallback
    }

    function currentStep() {
        var source = allSteps()
        for (var i = 0; i < source.length; i += 1) {
            var status = stepStatus(source[i])
            if (status === "current" || status === "running" || status === "waiting" || status === "failure" || status === "recovery") {
                return source[i]
            }
        }
        if (instrumentPayload.current_step) {
            return instrumentPayload.current_step
        }
        return source.length > 0 ? source[0] : ({ "title": summaryText(), "status": currentState })
    }

    function completedSteps() {
        var source = allSteps()
        var done = []
        for (var i = 0; i < source.length; i += 1) {
            var status = stepStatus(source[i])
            if (status === "complete" || status === "completed" || status === "done" || status === "success" || status === "passed") {
                done.push(source[i])
            }
        }
        return done
    }

    function futureSteps() {
        var source = allSteps()
        var upcoming = []
        for (var i = 0; i < source.length; i += 1) {
            var status = stepStatus(source[i])
            if (status === "" || status === "ready" || status === "queued" || status === "pending" || status === "future") {
                upcoming.push(source[i])
            }
        }
        return upcoming
    }

    function technicalText() {
        var details = instrumentPayload.technical_details || instrumentPayload.diagnostics || instrumentPayload.raw_diagnostics || ""
        if (details instanceof Array) {
            return details.join("\n")
        }
        if (typeof details === "object" && details !== null) {
            return JSON.stringify(details, null, 2)
        }
        return String(details)
    }

    function primaryActionLabel() {
        if (instrumentPayload.primary_action_label) {
            return instrumentPayload.primary_action_label
        }
        if (currentState === "waiting") {
            return "Continue"
        }
        if (currentState === "confirmation") {
            return "Approve once"
        }
        if (currentState === "paused") {
            return "Resume"
        }
        if (currentState === "failure") {
            return "Review recovery"
        }
        if (currentState === "recovery") {
            return "Resume"
        }
        if (currentState === "running") {
            return "View progress"
        }
        return "Begin"
    }

    function stateComponentSource() {
        if (currentState === "running") {
            return "InstrumentRunning.qml"
        }
        if (currentState === "waiting") {
            return "InstrumentWaiting.qml"
        }
        if (currentState === "confirmation") {
            return "InstrumentConfirmation.qml"
        }
        if (currentState === "paused") {
            return "InstrumentPaused.qml"
        }
        if (currentState === "failure") {
            return "InstrumentFailure.qml"
        }
        if (currentState === "recovery") {
            return "InstrumentRecovery.qml"
        }
        return "InstrumentReady.qml"
    }

    function syncStateItem() {
        if (!stateLoader.item) {
            return
        }
        stateLoader.item.tokens = tokens
        stateLoader.item.payload = instrumentPayload
        stateLoader.item.currentStep = currentStep()
        stateLoader.item.completedSteps = completedSteps()
        stateLoader.item.futureSteps = futureSteps()
        stateLoader.item.reducedMotion = reducedMotion
    }

    function collapse(reason) {
        root.collapsed = true
        if (root.instrumentController && root.instrumentController.collapseInstrument) {
            root.instrumentController.collapseInstrument(reason)
        }
        root.collapseRequested(reason)
    }

    function expand() {
        root.collapsed = false
        root.focusCollapseArmed = false
        if (root.instrumentController && root.instrumentController.expandInstrument) {
            root.instrumentController.expandInstrument()
        }
        root.expandRequested()
    }

    function invokePrimaryAction() {
        if (root.instrumentController && root.instrumentController.primaryAction) {
            root.instrumentController.primaryAction(root.currentState)
        }
        root.primaryActionRequested(root.currentState)
    }

    onInstrumentPayloadChanged: syncStateItem()
    onReducedMotionChanged: syncStateItem()
    onCurrentStateChanged: syncStateItem()
    onKeepVisibleForRitualChanged: {
        if (root.instrumentController && root.instrumentController.setKeepVisibleForRitual) {
            root.instrumentController.setKeepVisibleForRitual(root.keepVisibleForRitual)
        }
        root.keepVisibleRequested(root.keepVisibleForRitual)
    }
    onTechnicalDetailsOpenChanged: root.technicalDetailsToggled(root.technicalDetailsOpen)
    onCollapsedChanged: {
        if (!root.collapsed) {
            root.focusCollapseArmed = false
        }
    }
    onActiveChanged: {
        if (active) {
            root.focusCollapseArmed = true
        } else if (root.focusCollapseArmed && !root.keepVisibleForRitual && !root.collapsed) {
            root.collapse("focus")
        }
    }
    onVisibleChanged: {
        if (visible) {
            surface.forceActiveFocus()
        }
    }
    Component.onCompleted: surface.forceActiveFocus()

    Rectangle {
        id: collapsedTab

        anchors.fill: parent
        visible: root.collapsed
        radius: tokens.outerRadiusEpx
        color: tokens.panel
        border.color: tokens.border
        border.width: 1
        Accessible.role: Accessible.Button
        Accessible.name: "Expand quiet instrument"

        MouseArea {
            anchors.fill: parent
            hoverEnabled: true
            acceptedButtons: Qt.LeftButton
            onClicked: root.expand()
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: tokens.spaceSm
            spacing: tokens.spaceSm

            QuietStatusIcon {
                Layout.alignment: Qt.AlignHCenter
                tokens: tokens
                status: root.currentState
                reducedMotion: root.reducedMotion
            }

            Text {
                Layout.fillWidth: true
                text: root.stateLabel()
                color: tokens.textMuted
                font.family: tokens.fontFamily
                font.pixelSize: tokens.captionFontEpx
                horizontalAlignment: Text.AlignHCenter
                elide: Text.ElideRight
            }
        }
    }

    Rectangle {
        id: surface

        anchors.fill: parent
        visible: !root.collapsed
        focus: true
        radius: tokens.outerRadiusEpx
        color: tokens.panel
        border.color: tokens.border
        border.width: 1
        clip: true
        Accessible.role: Accessible.Pane
        Accessible.name: "Quiet instrument"
        Accessible.description: root.titleText() + " " + root.currentState

        Keys.onPressed: function(event) {
            if (event.key === Qt.Key_Escape) {
                root.collapse("escape")
                event.accepted = true
            }
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: tokens.spaceLg
            spacing: tokens.spaceMd

            RowLayout {
                Layout.fillWidth: true
                spacing: tokens.spaceMd

                QuietStatusIcon {
                    tokens: tokens
                    status: root.currentState
                    reducedMotion: root.reducedMotion
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2

                    Text {
                        Layout.fillWidth: true
                        text: root.titleText()
                        color: tokens.text
                        font.family: tokens.fontFamily
                        font.pixelSize: tokens.titleFontEpx
                        font.weight: Font.DemiBold
                        elide: Text.ElideRight
                    }

                    Text {
                        Layout.fillWidth: true
                        text: root.summaryText()
                        color: tokens.textMuted
                        font.family: tokens.fontFamily
                        font.pixelSize: tokens.captionFontEpx
                        elide: Text.ElideRight
                    }
                }

                CheckBox {
                    id: keepVisibleCheck

                    Layout.maximumWidth: 128
                    text: "Keep visible"
                    checked: root.keepVisibleForRitual
                    font.family: tokens.fontFamily
                    font.pixelSize: tokens.captionFontEpx
                    Accessible.name: text
                    Accessible.description: "Keep visible for this ritual"
                    onToggled: root.keepVisibleForRitual = checked

                    indicator: Rectangle {
                        implicitWidth: 18
                        implicitHeight: 18
                        x: keepVisibleCheck.leftPadding
                        y: keepVisibleCheck.topPadding + (keepVisibleCheck.availableHeight - height) / 2
                        radius: 4
                        color: keepVisibleCheck.checked ? tokens.accent : tokens.panel
                        border.color: keepVisibleCheck.activeFocus ? tokens.focusRing : tokens.borderStrong
                        border.width: keepVisibleCheck.activeFocus ? 2 : 1

                        Rectangle {
                            anchors.centerIn: parent
                            width: 8
                            height: 8
                            radius: 2
                            visible: keepVisibleCheck.checked
                            color: tokens.accentText
                        }
                    }

                    contentItem: Text {
                        text: keepVisibleCheck.text
                        color: tokens.textMuted
                        font.family: tokens.fontFamily
                        font.pixelSize: tokens.captionFontEpx
                        verticalAlignment: Text.AlignVCenter
                        leftPadding: keepVisibleCheck.indicator.width + tokens.spaceSm
                        elide: Text.ElideRight
                    }
                }

                ToolButton {
                    Layout.preferredWidth: tokens.primaryHitTargetEpx
                    Layout.preferredHeight: tokens.primaryHitTargetEpx
                    text: "X"
                    Accessible.name: "Collapse quiet instrument"
                    onClicked: root.collapse("close")
                }
            }

            QuietDivider {
                Layout.fillWidth: true
                tokens: tokens
            }

            Loader {
                id: stateLoader

                Layout.fillWidth: true
                Layout.fillHeight: true
                source: root.stateComponentSource()
                onLoaded: root.syncStateItem()
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: tokens.spaceSm
                visible: root.technicalDetailsOpen

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 132
                    radius: tokens.controlRadiusEpx
                    color: tokens.panelAlt
                    border.color: tokens.border
                    border.width: 1

                    TextArea {
                        anchors.fill: parent
                        anchors.margins: tokens.spaceSm
                        readOnly: true
                        selectByMouse: true
                        wrapMode: TextEdit.Wrap
                        text: root.technicalText()
                        color: tokens.text
                        font.family: "Consolas"
                        font.pixelSize: tokens.captionFontEpx
                        Accessible.name: "Raw diagnostics"
                        background: Rectangle {
                            color: "transparent"
                        }
                    }
                }
            }

            QuietDivider {
                Layout.fillWidth: true
                tokens: tokens
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: tokens.spaceSm

                ToolButton {
                    text: root.technicalDetailsOpen ? "Hide technical details" : "Technical details"
                    Accessible.name: text
                    enabled: root.technicalText().length > 0
                    onClicked: root.technicalDetailsOpen = !root.technicalDetailsOpen
                }

                Item {
                    Layout.fillWidth: true
                }

                QuietButton {
                    role: "primary"
                    tokens: tokens
                    reducedMotion: root.reducedMotion
                    text: root.primaryActionLabel()
                    Accessible.name: root.primaryActionLabel()
                    onClicked: root.invokePrimaryAction()
                }
            }
        }
    }
}
