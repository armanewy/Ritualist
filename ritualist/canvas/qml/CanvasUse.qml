import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ApplicationWindow {
    id: root
    width: 1280
    height: 760
    visible: true
    title: "Ritualist Canvas"
    color: backgroundPassthrough ? "transparent" : token("background", "#070c13")

    property var canvasController: typeof ritualistCanvasUseController === "undefined" ? null : ritualistCanvasUseController
    property var canvasPayload: typeof ritualistCanvasPayload === "undefined" ? ({}) : ritualistCanvasPayload
    property var editPayload: canvasController ? canvasController.editPayload : ritualistCanvasEditPayload
    property var performanceSettings: typeof ritualistCanvasPerformance === "undefined" ? ({}) : ritualistCanvasPerformance
    property var hostSettings: typeof ritualistCanvasHost === "undefined" ? ({ mode: "windowed", taskbar_policy: "respect" }) : ritualistCanvasHost
    property bool e2eEnabled: typeof ritualistE2EEnabled === "undefined" ? false : ritualistE2EEnabled
    property bool editMode: canvasController ? canvasController.editMode : false
    property bool mockMode: typeof ritualistMockMode === "undefined" ? false : ritualistMockMode
    property bool desktopWorkAreaHost: hostSettings.mode === "desktop_work_area"
    property bool backgroundPassthrough: hostSettings.background_passthrough === true
    property bool animationsEnabled: performanceSettings.animations === undefined ? true : performanceSettings.animations
    property bool showPerformanceOverlay: performanceSettings.show_performance_overlay === true
    property int liveUpdateRateHz: Math.max(1, performanceSettings.live_update_rate_hz || 30)
    property int liveUpdateIntervalMs: Math.max(16, Math.round(1000 / liveUpdateRateHz))
    property int maxAnimatedComponents: performanceSettings.max_animated_components === undefined ? 48 : performanceSettings.max_animated_components
    property int imageResolutionCap: Math.max(320, performanceSettings.image_resolution_cap || 1440)
    property string shadowMode: performanceSettings.shadows || canvasTheme().tokens.shadow || "simple"
    property bool richShadows: shadowMode === "rich"
    property int payloadVersion: 0
    property double lastPayloadUpdateMs: 0
    property int payloadUpdatesThisSecond: 0
    property int measuredPayloadUpdates: 0
    property int frameTicksThisSecond: 0
    property int measuredFps: 0
    property int motionFastMs: performanceSettings.mode === "low" ? 0 : (canvasTheme().tokens.motion_fast_ms || 90)
    property int motionNormalMs: performanceSettings.mode === "low" ? 0 : (canvasTheme().tokens.motion_normal_ms || 160)
    property bool actionBusy: canvasController ? canvasController.actionBusy : false
    property bool runtimeActive: canvasController ? canvasController.runtimeActive : false
    property bool runtimePaused: canvasController ? canvasController.runtimePaused : false
    property string footerText: canvasController ? canvasController.lastEventLabel : "Canvas ready"
    property string pendingEditDecision: ""
    property int spaceSm: Number(token("spacing_sm", 6))
    property int spaceMd: Number(token("spacing_md", 12))
    property int spaceLg: Number(token("spacing_lg", 18))
    property int radiusSm: Number(token("radius_sm", 4))
    property int radiusMd: Number(token("radius_md", 8))
    property int radiusLg: Number(token("radius_lg", 12))

    function components() {
        if (!canvasPayload || !canvasPayload.components) {
            return []
        }
        return canvasPayload.components
    }

    function canvasName() {
        if (!canvasPayload || !canvasPayload.canvas) {
            return "Canvas"
        }
        return canvasPayload.canvas.name || canvasPayload.canvas.id || "Canvas"
    }

    function canvasTheme() {
        if (!canvasPayload || !canvasPayload.canvas || !canvasPayload.canvas.theme) {
            return { tokens: {} }
        }
        return canvasPayload.canvas.theme
    }

    function token(name, fallback) {
        var tokens = canvasTheme().tokens || {}
        if (tokens[name] !== undefined && tokens[name] !== null) {
            return tokens[name]
        }
        return fallback
    }

    function performanceCounters() {
        if (!canvasPayload || !canvasPayload.runtime || !canvasPayload.runtime.performance_counters) {
            return {}
        }
        return canvasPayload.runtime.performance_counters
    }

    function componentDataValue(component, key, fallback) {
        var data = component.data || {}
        if (data[key] !== undefined && data[key] !== null) {
            return data[key]
        }
        var props = component.props || {}
        if (props[key] !== undefined && props[key] !== null) {
            return props[key]
        }
        return fallback
    }

    function detailText(component) {
        return component.message || component.subtitle || component.type || ""
    }

    function textHorizontalAlignment(component) {
        var align = String(root.componentDataValue(component, "align", "left")).toLowerCase()
        if (align === "center") {
            return Text.AlignHCenter
        }
        if (align === "right") {
            return Text.AlignRight
        }
        return Text.AlignLeft
    }

    function imageFillMode(component) {
        var fit = String(root.componentDataValue(component, "fit", "cover")).toLowerCase()
        if (fit === "contain") {
            return Image.PreserveAspectFit
        }
        if (fit === "stretch") {
            return Image.Stretch
        }
        return Image.PreserveAspectCrop
    }

    function stateIsDanger(status) {
        return status === "failed" || status === "incompatible" || status === "interrupted"
    }

    function stateIsWarning(status) {
        return status === "warning" || status === "warnings" || status === "stopped"
    }

    function stateIsActive(status) {
        return status === "running" || status === "waiting" || status === "paused" ||
               status === "confirming" || status === "confirmation"
    }

    function stateIsSuccess(status) {
        return status === "success" || status === "compatible"
    }

    function componentColor(status, typeName) {
        if (stateIsDanger(status)) {
            return root.token("danger_panel", "#28151c")
        }
        if (stateIsWarning(status)) {
            return root.token("warning_panel", "#252014")
        }
        if (stateIsActive(status)) {
            return root.token("focus_panel", "#132235")
        }
        if (stateIsSuccess(status)) {
            return root.token("success_panel", "#12251f")
        }
        if (typeName === "shape") {
            return root.token("panel_alt", "#182233")
        }
        return root.token("panel", "#101720")
    }

    function borderColor(status) {
        if (stateIsDanger(status)) {
            return root.token("danger", "#ff6b7a")
        }
        if (stateIsWarning(status)) {
            return root.token("warning", "#f5c45b")
        }
        if (stateIsActive(status)) {
            return root.token("focus_ring", "#7fb8ff")
        }
        if (stateIsSuccess(status)) {
            return root.token("success", root.token("accent", "#3dd6a5"))
        }
        return root.token("border", "#2c3c53")
    }

    function actionRole(actionId) {
        if (actionId === "stop" || actionId === "Cancel Ritual") {
            return "danger"
        }
        if (actionId === "pause") {
            return "warning"
        }
        if (actionId === "run" || actionId === "resume" || actionId === "dry_run" ||
                actionId === "doctor" || actionId === "preview_plan") {
            return "primary"
        }
        return "neutral"
    }

    function buttonBackground(role, enabled, hovered, down) {
        if (!enabled) {
            return root.token("panel_alt", "#0e151f")
        }
        if (role === "danger") {
            return down || hovered ? root.token("danger_panel", "#28151c") : root.token("panel", "#101720")
        }
        if (role === "warning") {
            return down || hovered ? root.token("warning_panel", "#252014") : root.token("panel", "#101720")
        }
        if (role === "primary") {
            return down || hovered ? root.token("focus_panel", "#132235") : root.token("panel", "#101720")
        }
        return down || hovered ? root.token("panel_alt", "#0e151f") : root.token("panel", "#101720")
    }

    function buttonBorder(role, enabled, focused) {
        if (focused) {
            return root.token("focus_ring", "#7fb8ff")
        }
        if (!enabled) {
            return root.token("border", "#203044")
        }
        if (role === "danger") {
            return root.token("danger", "#ff6b7a")
        }
        if (role === "warning") {
            return root.token("warning", "#f5c45b")
        }
        if (role === "primary") {
            return root.token("accent", "#3dd6a5")
        }
        return root.token("border", "#203044")
    }

    function delegateFor(typeName) {
        if (typeName === "image") {
            return imageDelegate
        }
        if (typeName === "shape" || typeName === "divider" || typeName === "spacer/divider") {
            return shapeDelegate
        }
        if (typeName === "text.label") {
            return textDelegate
        }
        if (typeName === "clock") {
            return clockDelegate
        }
        if (typeName === "recent.activity") {
            return activityDelegate
        }
        if (typeName === "category.dock") {
            return dockDelegate
        }
        if (typeName === "ritual.status" || typeName === "target.status" || typeName === "doctor.badge" || typeName === "ritual.controller") {
            return statusDelegate
        }
        return cardDelegate
    }

    function applyControllerPayload() {
        if (!canvasController) {
            return
        }
        var started = Date.now()
        canvasPayload = canvasController.payload
        lastPayloadUpdateMs = Math.max(0, Date.now() - started)
        payloadVersion += 1
        payloadUpdatesThisSecond += 1
    }

    function requestPayloadUpdate(immediate) {
        if (!canvasController) {
            return
        }
        if (immediate) {
            payloadDrainTimer.stop()
            applyControllerPayload()
            return
        }
        if (!payloadDrainTimer.running) {
            payloadDrainTimer.start()
        }
    }

    function dispatch(componentId, actionId) {
        if (!canvasController || actionBusy || mockMode || editMode) {
            return
        }
        canvasController.dispatchAction(componentId, actionId)
    }

    function selectedComponentId() {
        if (!editPayload || !editPayload.selection) {
            return ""
        }
        return editPayload.selection.component_id || ""
    }

    function selectedComponent() {
        if (!editPayload || !editPayload.selected_component) {
            return {}
        }
        return editPayload.selected_component
    }

    function selectedProps() {
        var selected = selectedComponent()
        return selected.props || {}
    }

    function selectedBinding() {
        var selected = selectedComponent()
        return selected.binding || {}
    }

    function paletteEntries() {
        if (!editPayload || !editPayload.palette) {
            return []
        }
        return editPayload.palette
    }

    function selectedPropertySchema() {
        var selected = selectedComponent()
        return selected.property_schema || []
    }

    function selectedSupportedBindings() {
        var selected = selectedComponent()
        return selected.supported_bindings || []
    }

    function editInspector() {
        if (!editPayload || !editPayload.property_inspector) {
            return {}
        }
        return editPayload.property_inspector
    }

    function layoutPropertySchema() {
        if (selectedComponentId().length === 0) {
            return []
        }
        return editInspector().layout_properties || []
    }

    function contentPropertySchema() {
        if (selectedComponentId().length === 0) {
            return []
        }
        return editInspector().content_properties || selectedPropertySchema()
    }

    function appearancePropertySchema() {
        if (selectedComponentId().length === 0) {
            return []
        }
        return editInspector().appearance_properties || []
    }

    function editSnapGrid() {
        if (!editPayload || !editPayload.snap_grid) {
            return { enabled: true, size: 16, unit: "px" }
        }
        return editPayload.snap_grid
    }

    function requestEditDecision(decision) {
        if (!root.canvasController) {
            return
        }
        if (decision === "save" && (!root.editPayload || !root.editPayload.dirty)) {
            root.canvasController.setEditMode(false)
            return
        }
        if (decision === "discard" && (!root.editPayload || !root.editPayload.dirty)) {
            root.canvasController.setEditMode(false)
            return
        }
        root.pendingEditDecision = decision
    }

    function confirmEditDecision() {
        if (!root.canvasController) {
            root.pendingEditDecision = ""
            return
        }
        if (root.pendingEditDecision === "save") {
            if (root.canvasController.saveCanvas()) {
                root.canvasController.setEditMode(false)
                root.pendingEditDecision = ""
            }
            return
        } else if (root.pendingEditDecision === "discard") {
            root.canvasController.discardEdit()
            root.canvasController.setEditMode(false)
        }
        root.pendingEditDecision = ""
    }

    component PaperButton: Button {
        id: control
        property string role: "neutral"
        property bool compact: false

        implicitHeight: compact ? 30 : 36
        leftPadding: root.spaceMd
        rightPadding: root.spaceMd
        topPadding: root.spaceSm
        bottomPadding: root.spaceSm
        font.family: root.token("font_family", "Segoe UI")
        font.pixelSize: root.token("font_size_body", 13)
        focusPolicy: Qt.StrongFocus

        contentItem: Text {
            text: control.text
            color: control.enabled ? root.token("foreground", "#f4f7fb") : root.token("muted", "#91a2b8")
            font: control.font
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }

        background: Rectangle {
            radius: root.radiusMd
            color: root.buttonBackground(control.role, control.enabled, control.hovered, control.down)
            border.color: root.buttonBorder(control.role, control.enabled, control.activeFocus)
            border.width: control.activeFocus ? 2 : 1
            opacity: control.enabled ? 1.0 : 0.56
        }
    }

    component PaperTextField: TextField {
        id: field
        implicitHeight: 34
        color: root.token("foreground", "#f4f7fb")
        placeholderTextColor: root.token("muted", "#91a2b8")
        selectedTextColor: root.token("background", "#070c13")
        selectionColor: root.token("accent", "#3dd6a5")
        font.family: root.token("font_family", "Segoe UI")
        font.pixelSize: root.token("font_size_body", 13)
        leftPadding: root.spaceSm
        rightPadding: root.spaceSm
        background: Rectangle {
            radius: root.radiusSm
            color: root.token("panel_alt", "#101720")
            border.color: field.activeFocus ? root.token("focus_ring", "#7fb8ff") : root.token("border", "#203044")
            border.width: field.activeFocus ? 2 : 1
        }
    }

    component PaperComboBox: ComboBox {
        id: combo
        implicitHeight: 34
        font.family: root.token("font_family", "Segoe UI")
        font.pixelSize: root.token("font_size_body", 13)
        contentItem: Text {
            text: combo.displayText
            color: combo.enabled ? root.token("foreground", "#f4f7fb") : root.token("muted", "#91a2b8")
            font: combo.font
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
            leftPadding: root.spaceSm
            rightPadding: root.spaceLg
        }
        background: Rectangle {
            radius: root.radiusSm
            color: root.token("panel_alt", "#101720")
            border.color: combo.activeFocus ? root.token("focus_ring", "#7fb8ff") : root.token("border", "#203044")
            border.width: combo.activeFocus ? 2 : 1
        }
    }

    Connections {
        target: root.canvasController

        function onPayloadChanged() {
            root.requestPayloadUpdate(false)
        }

        function onEditPayloadChanged() {
            root.editPayload = root.canvasController.editPayload
        }

        function onEditModeChanged() {
            root.editMode = root.canvasController.editMode
        }

        function onMetricsChanged() {
            root.footerText = root.canvasController.lastEventLabel
        }

        function onActionStateChanged() {
            root.actionBusy = root.canvasController.actionBusy
            root.runtimeActive = root.canvasController.runtimeActive
            root.runtimePaused = root.canvasController.runtimePaused
            root.requestPayloadUpdate(true)
        }

        function onActionCompleted(_componentId, _result) {
            root.requestPayloadUpdate(true)
        }

        function onActionFailed(_componentId, _message) {
            root.requestPayloadUpdate(true)
        }

        function onConfirmationRequested(_componentId, _request) {
            root.requestPayloadUpdate(true)
        }
    }

    Timer {
        id: payloadDrainTimer
        interval: root.liveUpdateIntervalMs
        repeat: false
        onTriggered: root.applyControllerPayload()
    }

    Timer {
        id: performanceMeasureTimer
        interval: 1000
        repeat: true
        running: root.showPerformanceOverlay
        onTriggered: {
            root.measuredPayloadUpdates = root.payloadUpdatesThisSecond
            root.payloadUpdatesThisSecond = 0
            root.measuredFps = root.frameTicksThisSecond
            root.frameTicksThisSecond = 0
        }
    }

    Timer {
        id: e2eHeartbeatTimer
        interval: 250
        repeat: true
        running: root.e2eEnabled && root.canvasController !== null
        triggeredOnStart: true
        onTriggered: root.canvasController.recordUiHeartbeat(
            Date.now(),
            root.payloadVersion,
            root.lastPayloadUpdateMs,
            root.payloadUpdatesThisSecond,
            root.measuredFps
        )
    }

    Timer {
        id: frameApproximationTimer
        interval: 16
        repeat: true
        running: root.showPerformanceOverlay
        onTriggered: root.frameTicksThisSecond += 1
    }

    Component.onCompleted: root.requestPayloadUpdate(true)

    Shortcut {
        enabled: root.desktopWorkAreaHost
        sequence: "Esc"
        onActivated: root.close()
    }

    Rectangle {
        anchors.fill: parent
        color: root.token("background", "#070c13")
        visible: !root.backgroundPassthrough
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: root.spaceLg
        spacing: root.spaceMd

        RowLayout {
            Layout.fillWidth: true
            spacing: root.spaceMd

            ColumnLayout {
                Layout.fillWidth: true
                spacing: root.spaceSm

                Text {
                    text: root.canvasName()
                    color: root.token("foreground", "#f4f7fb")
                    font.family: root.token("font_family", "Segoe UI")
                    font.pixelSize: root.token("font_size_title", 26)
                    font.weight: Font.DemiBold
                }

                Text {
                    text: root.footerText
                    color: root.token("muted", "#91a2b8")
                    font.family: root.token("font_family", "Segoe UI")
                    font.pixelSize: root.token("font_size_body", 13)
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
            }

            PaperButton {
                text: "Exit Desktop Canvas"
                role: "danger"
                visible: root.desktopWorkAreaHost
                enabled: root.desktopWorkAreaHost
                onClicked: root.close()
            }

            PaperButton {
                text: root.editMode ? "Done" : "Edit Room"
                role: root.editMode ? "primary" : "neutral"
                enabled: root.canvasController && !root.runtimeActive
                onClicked: {
                    if (root.editMode) {
                        root.requestEditDecision("save")
                    } else {
                        root.canvasController.setEditMode(true)
                    }
                }
            }

            PaperButton {
                text: "Cancel"
                role: "danger"
                visible: root.editMode
                enabled: root.canvasController && !root.runtimeActive
                onClicked: root.requestEditDecision("discard")
            }

            PaperButton {
                text: "Pause"
                role: "warning"
                enabled: root.runtimeActive && !root.runtimePaused && root.canvasController
                onClicked: root.canvasController.pauseCurrentRun()
            }

            PaperButton {
                text: "Resume"
                role: "primary"
                enabled: root.runtimeActive && root.runtimePaused && root.canvasController
                onClicked: root.canvasController.resumeCurrentRun()
            }

            PaperButton {
                text: "Stop"
                role: "danger"
                enabled: root.runtimeActive && root.canvasController
                onClicked: root.canvasController.stopCurrentRun()
            }

            PaperButton {
                text: "Create from what I do"
                enabled: root.canvasController && !root.mockMode && !root.canvasController.watchMeRecording
                onClicked: root.canvasController.startWatchMe()
            }

            PaperButton {
                text: "Stop Watch Me"
                role: "warning"
                enabled: root.canvasController && root.canvasController.watchMeRecording
                onClicked: root.canvasController.stopWatchMe()
            }

            PaperButton {
                text: "Create Draft"
                role: "primary"
                enabled: root.canvasController && root.canvasController.watchMeDraftAvailable
                onClicked: root.canvasController.createWatchMeDraft()
            }

            PaperButton {
                text: "Discard"
                role: "danger"
                enabled: root.canvasController && (root.canvasController.watchMeRecording || root.canvasController.watchMeDraftAvailable || root.canvasController.watchMeDraftSummary.length > 0)
                onClicked: root.canvasController.discardWatchMe()
            }
        }

        Rectangle {
            Layout.fillWidth: true
            height: root.pendingEditDecision.length > 0 ? 56 : 0
            radius: root.radiusLg
            color: root.pendingEditDecision === "discard" ? root.token("danger_panel", "#28151c") : root.token("focus_panel", "#132235")
            border.color: root.pendingEditDecision === "discard" ? root.token("danger", "#ff6b7a") : root.token("accent", "#3dd6a5")
            visible: root.pendingEditDecision.length > 0

            RowLayout {
                anchors.fill: parent
                anchors.margins: root.spaceMd
                spacing: root.spaceMd

                Text {
                    text: root.pendingEditDecision === "discard" ? "Discard Room edits?" : "Save Room edits?"
                    color: root.token("foreground", "#f4f7fb")
                    font.pixelSize: root.token("font_size_body", 13)
                    font.weight: Font.DemiBold
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                }

                PaperButton {
                    text: "Confirm"
                    role: root.pendingEditDecision === "discard" ? "danger" : "primary"
                    onClicked: root.confirmEditDecision()
                }

                PaperButton {
                    text: "Keep Editing"
                    onClicked: root.pendingEditDecision = ""
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            height: watchMeStatus.visible ? (watchMePreview.visible ? 132 : 48) : 0
            radius: root.radiusLg
            color: root.canvasController && root.canvasController.watchMeRecording ? root.token("warning_panel", "#252014") : root.token("panel", "#101720")
            border.color: root.canvasController && root.canvasController.watchMeRecording ? root.token("warning", "#f5c45b") : root.token("border", "#203044")
            visible: root.canvasController && (root.canvasController.watchMeRecording || root.canvasController.watchMeDraftAvailable || root.canvasController.watchMeDraftSummary.length > 0)

            ColumnLayout {
                id: watchMeStatus
                anchors.fill: parent
                anchors.margins: root.spaceMd
                visible: parent.visible
                spacing: root.spaceSm

                RowLayout {
                    Layout.fillWidth: true
                    spacing: root.spaceSm

                    Rectangle {
                        width: 10
                        height: 10
                        radius: 5
                        color: root.canvasController && root.canvasController.watchMeRecording ? root.token("warning", "#f5c45b") : root.token("accent", "#3dd6a5")
                    }

                    Text {
                        text: root.canvasController ? root.canvasController.watchMeStatusLabel : ""
                        color: root.token("foreground", "#f4f7fb")
                        font.pixelSize: 12
                        font.weight: Font.DemiBold
                        elide: Text.ElideRight
                        Layout.preferredWidth: 260
                    }

                    Text {
                        text: root.canvasController ? root.canvasController.watchMeDraftSummary : ""
                        color: root.token("muted", "#91a2b8")
                        font.pixelSize: 12
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                }

                Text {
                    id: watchMePreview
                    text: root.canvasController ? root.canvasController.watchMeDraftPreview : ""
                    color: root.token("muted", "#91a2b8")
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                    maximumLineCount: 4
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    visible: text.length > 0
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: root.spaceMd

            Rectangle {
                Layout.preferredWidth: root.editMode ? 248 : 0
                Layout.fillHeight: true
                visible: root.editMode
                color: root.token("panel", "#0e151f")
                border.color: root.token("border", "#203044")
                border.width: 1
                radius: root.radiusLg

                ScrollView {
                    anchors.fill: parent
                    anchors.margins: root.spaceMd

                    ColumnLayout {
                        width: parent.width
                        spacing: root.spaceMd

                        Text {
                            text: "Add components"
                            color: root.token("foreground", "#f4f7fb")
                            font.pixelSize: 18
                            font.bold: true
                            Layout.fillWidth: true
                        }

                        Text {
                            text: "Safe Room components only"
                            color: root.token("muted", "#91a2b8")
                            font.pixelSize: 12
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }

                        Repeater {
                            model: root.paletteEntries()

                            PaperButton {
                                text: modelData.display_name
                                Layout.fillWidth: true
                                onClicked: root.canvasController.addComponent(modelData.type_id)
                            }
                        }
                    }
                }
            }

            Flickable {
                id: scroll
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                contentWidth: Math.max(width, 1280)
                contentHeight: Math.max(height, 760)

                Rectangle {
                    width: scroll.contentWidth
                    height: scroll.contentHeight
                    color: root.backgroundPassthrough ? "transparent" : root.token("background", "#070c13")
                    border.color: root.editMode ? root.token("accent", "#3dd6a5") : (root.backgroundPassthrough ? "transparent" : root.token("border", "#1d2a3a"))
                    border.width: root.editMode ? 2 : (root.backgroundPassthrough ? 0 : 1)
                    radius: root.radiusLg

                    Repeater {
                        model: root.editMode && root.editSnapGrid().enabled ? Math.floor(parent.width / Math.max(1, root.editSnapGrid().size)) : 0

                        Rectangle {
                            x: index * Math.max(1, root.editSnapGrid().size)
                            y: 0
                            width: 1
                            height: parent.height
                            color: root.token("border", "#203044")
                            opacity: 0.18
                        }
                    }

                    Repeater {
                        model: root.editMode && root.editSnapGrid().enabled ? Math.floor(parent.height / Math.max(1, root.editSnapGrid().size)) : 0

                        Rectangle {
                            x: 0
                            y: index * Math.max(1, root.editSnapGrid().size)
                            width: parent.width
                            height: 1
                            color: root.token("border", "#203044")
                            opacity: 0.18
                        }
                    }

                    Repeater {
                        model: root.components()

                        Item {
                            id: componentShell
                            property string componentId: modelData.id
                            property bool selected: root.editMode && root.selectedComponentId() === componentId

                            x: modelData.x
                            y: modelData.y
                            z: modelData.z
                            width: modelData.width
                            height: modelData.height
                            visible: modelData.visible

                            Rectangle {
                                id: componentShadow
                                x: root.shadowMode === "rich" ? 5 : 3
                                y: root.shadowMode === "rich" ? 6 : 4
                                width: parent.width
                                height: parent.height
                                radius: root.radiusLg
                                color: root.token("border", "#203044")
                                opacity: root.shadowMode === "rich" ? 0.22 : 0.12
                                visible: root.shadowMode !== "none" && index < root.maxAnimatedComponents
                            }

                            Rectangle {
                            id: componentFrame
                            property string componentId: componentShell.componentId
                            property bool selected: componentShell.selected

                            anchors.fill: parent
                            radius: root.radiusLg
                            color: root.componentColor(modelData.status, modelData.type)
                            border.color: selected ? root.token("accent", "#3dd6a5") : root.borderColor(modelData.status)
                            border.width: selected ? 3 : 1
                            opacity: root.actionBusy && !selected ? 0.92 : 1.0

                            Behavior on opacity {
                                enabled: root.animationsEnabled && index < root.maxAnimatedComponents
                                NumberAnimation { duration: root.motionFastMs }
                            }

                            MouseArea {
                                id: moveArea
                                anchors.fill: parent
                                enabled: root.editMode
                                drag.target: componentShell
                                drag.axis: Drag.XAndYAxis
                                onClicked: root.canvasController.selectComponent(componentShell.componentId)
                                onReleased: root.canvasController.moveComponent(componentShell.componentId, componentShell.x, componentShell.y)
                            }

                            Loader {
                                id: componentContentLoader
                                anchors.fill: parent
                                anchors.margins: root.spaceMd
                                property var componentData: modelData
                                sourceComponent: root.delegateFor(modelData.type)
                                onLoaded: item.componentData = componentData
                            }

                            Rectangle {
                                width: 18
                                height: 18
                                radius: root.radiusSm
                                color: root.token("accent", "#3dd6a5")
                                anchors.right: parent.right
                                anchors.bottom: parent.bottom
                                anchors.margins: 4
                                visible: componentFrame.selected

                                MouseArea {
                                    anchors.fill: parent
                                    property real startX: 0
                                    property real startY: 0
                                    property real startWidth: 0
                                    property real startHeight: 0
                                    onPressed: {
                                        startX = mouse.x
                                        startY = mouse.y
                                        startWidth = componentFrame.width
                                        startHeight = componentFrame.height
                                    }
                                    onPositionChanged: {
                                        componentShell.width = Math.max(32, startWidth + mouse.x - startX)
                                        componentShell.height = Math.max(24, startHeight + mouse.y - startY)
                                    }
                                    onReleased: root.canvasController.resizeComponent(componentShell.componentId, componentShell.width, componentShell.height)
                                }
                            }
                        }
                        }
                    }
                }
            }

            Rectangle {
                Layout.preferredWidth: root.editMode ? 360 : 0
                Layout.fillHeight: true
                visible: root.editMode
                color: root.token("panel", "#0e151f")
                border.color: root.token("border", "#203044")
                border.width: 1
                radius: root.radiusLg

                ScrollView {
                    anchors.fill: parent
                    anchors.margins: 12

                    ColumnLayout {
                        width: parent.width
                        spacing: 10

                        Text {
                            text: "Properties"
                            color: root.token("foreground", "#f4f7fb")
                            font.pixelSize: 20
                            font.bold: true
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            PaperButton { text: "Save"; role: "primary"; enabled: root.canvasController && root.editPayload && root.editPayload.dirty; onClicked: root.canvasController.saveCanvas() }
                            PaperButton { text: "Discard"; role: "danger"; enabled: root.canvasController && root.editPayload && root.editPayload.dirty; onClicked: root.canvasController.discardEdit() }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            PaperButton { text: "Undo"; enabled: root.canvasController && root.editPayload && root.editPayload.history && root.editPayload.history.can_undo; onClicked: root.canvasController.undoEdit() }
                            PaperButton { text: "Redo"; enabled: root.canvasController && root.editPayload && root.editPayload.history && root.editPayload.history.can_redo; onClicked: root.canvasController.redoEdit() }
                        }

                        Text {
                            text: root.selectedComponentId() ? (root.selectedComponent().id + " | " + root.selectedComponent().type) : "Select a component"
                            color: root.token("foreground", "#f4f7fb")
                            font.pixelSize: 15
                            font.bold: true
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            visible: root.selectedComponentId().length > 0
                            PaperButton { text: "Duplicate"; onClicked: root.canvasController.duplicateSelectedComponent() }
                            PaperButton { text: "Delete"; role: "danger"; onClicked: root.canvasController.deleteSelectedComponent() }
                        }

                        Text {
                            text: "Layout"
                            color: root.token("muted", "#91a2b8")
                            font.pixelSize: 13
                            font.bold: true
                            visible: root.selectedComponentId().length > 0
                        }

                        Repeater {
                            model: root.layoutPropertySchema()

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 4

                                Text {
                                    text: modelData.label
                                    color: root.token("muted", "#91a2b8")
                                    font.pixelSize: 11
                                }

                                PaperComboBox {
                                    Layout.fillWidth: true
                                    visible: (modelData.allowed_values || []).length > 0
                                    model: modelData.allowed_values || []
                                    currentIndex: Math.max(0, (modelData.allowed_values || []).indexOf(String(root.selectedProps()[modelData.name] || modelData.default || "")))
                                    onActivated: root.canvasController.editComponentProperty(root.selectedComponentId(), modelData.name, currentText)
                                }

                                PaperTextField {
                                    Layout.fillWidth: true
                                    text: String(root.selectedComponent()[modelData.name] === undefined || root.selectedComponent()[modelData.name] === null ? "" : root.selectedComponent()[modelData.name])
                                    readOnly: true
                                }
                            }
                        }

                        Text {
                            text: "Content"
                            color: root.token("muted", "#91a2b8")
                            font.pixelSize: 13
                            font.bold: true
                            visible: root.selectedComponentId().length > 0
                        }

                        Repeater {
                            model: root.contentPropertySchema()

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 4

                                Text {
                                    text: modelData.label
                                    color: root.token("muted", "#91a2b8")
                                    font.pixelSize: 11
                                }

                                PaperComboBox {
                                    Layout.fillWidth: true
                                    visible: (modelData.allowed_values || []).length > 0
                                    model: modelData.allowed_values || []
                                    currentIndex: Math.max(0, (modelData.allowed_values || []).indexOf(String(root.selectedProps()[modelData.name] || modelData.default || "")))
                                    onActivated: root.canvasController.editComponentProperty(root.selectedComponentId(), modelData.name, currentText)
                                }

                                PaperTextField {
                                    Layout.fillWidth: true
                                    visible: (modelData.allowed_values || []).length === 0
                                    text: String(root.selectedProps()[modelData.name] === undefined || root.selectedProps()[modelData.name] === null ? (modelData.default || "") : root.selectedProps()[modelData.name])
                                    onEditingFinished: root.canvasController.editComponentProperty(root.selectedComponentId(), modelData.name, text)
                                }
                            }
                        }

                        Text {
                            text: "Appearance"
                            color: root.token("muted", "#91a2b8")
                            font.pixelSize: 13
                            font.bold: true
                            visible: root.selectedComponentId().length > 0 && root.appearancePropertySchema().length > 0
                        }

                        Repeater {
                            model: root.appearancePropertySchema()

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 4

                                Text {
                                    text: modelData.label
                                    color: root.token("muted", "#91a2b8")
                                    font.pixelSize: 11
                                }

                                PaperComboBox {
                                    Layout.fillWidth: true
                                    visible: (modelData.allowed_values || []).length > 0
                                    model: modelData.allowed_values || []
                                    currentIndex: Math.max(0, (modelData.allowed_values || []).indexOf(String(root.selectedProps()[modelData.name] || modelData.default || "")))
                                    onActivated: root.canvasController.editComponentProperty(root.selectedComponentId(), modelData.name, currentText)
                                }

                                PaperTextField {
                                    Layout.fillWidth: true
                                    visible: (modelData.allowed_values || []).length === 0
                                    text: String(root.selectedProps()[modelData.name] === undefined || root.selectedProps()[modelData.name] === null ? (modelData.default || "") : root.selectedProps()[modelData.name])
                                    onEditingFinished: root.canvasController.editComponentProperty(root.selectedComponentId(), modelData.name, text)
                                }
                            }
                        }

                        Text {
                            text: "Behavior binding"
                            color: root.token("muted", "#91a2b8")
                            font.pixelSize: 13
                            font.bold: true
                            visible: root.selectedComponentId().length > 0
                        }

                        PaperComboBox {
                            id: bindingKind
                            Layout.fillWidth: true
                            visible: root.selectedComponentId().length > 0
                            model: root.selectedSupportedBindings()
                            currentIndex: Math.max(0, root.selectedSupportedBindings().indexOf(root.selectedBinding().kind || "static"))
                        }

                        PaperTextField {
                            id: bindingReference
                            Layout.fillWidth: true
                            visible: root.selectedComponentId().length > 0
                            placeholderText: "Binding reference"
                            text: root.selectedBinding().recipe_id || root.selectedBinding().target || root.selectedBinding().intent_id || root.selectedBinding().id || ""
                        }

                        PaperButton {
                            text: "Apply Binding"
                            role: "primary"
                            visible: root.selectedComponentId().length > 0
                            Layout.fillWidth: true
                            onClicked: root.canvasController.editComponentBinding(root.selectedComponentId(), bindingKind.currentText || "static", bindingReference.text)
                        }

                        Text {
                            text: root.editPayload && root.editPayload.validation && root.editPayload.validation.errors.length ? root.editPayload.validation.errors.join("; ") : ""
                            color: root.token("danger", "#ff6b7a")
                            visible: text.length > 0
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                    }
                }
            }
        }
    }

    Component {
        id: cardDelegate

        ColumnLayout {
            property var componentData: ({})

            spacing: root.token("spacing_sm", 6)

            Text {
                text: componentData.title || componentData.id
                color: root.token("foreground", "#f4f7fb")
                font.family: root.token("font_family", "Segoe UI")
                font.pixelSize: 16
                font.weight: Font.DemiBold
                elide: Text.ElideRight
                Layout.fillWidth: true
            }

            Text {
                text: root.detailText(componentData)
                color: root.token("muted", "#91a2b8")
                font.family: root.token("font_family", "Segoe UI")
                font.pixelSize: root.token("font_size_body", 13)
                wrapMode: Text.WordWrap
                maximumLineCount: 4
                elide: Text.ElideRight
                Layout.fillWidth: true
            }

            Text {
                text: componentData.warnings && componentData.warnings.length ? componentData.warnings.join("; ") : ""
                color: root.token("warning", "#f5c45b")
                font.pixelSize: 11
                wrapMode: Text.WordWrap
                maximumLineCount: 3
                elide: Text.ElideRight
                visible: text.length > 0
                Layout.fillWidth: true
            }

            Text {
                text: root.editMode ? (componentData.id + " | " + componentData.type) : ""
                color: root.token("accent", "#3dd6a5")
                font.pixelSize: 11
                visible: root.editMode
                elide: Text.ElideRight
                Layout.fillWidth: true
            }

            Item {
                Layout.fillHeight: true
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: root.spaceSm
                visible: !root.editMode && componentData.enabled_actions && componentData.enabled_actions.length > 0

                Repeater {
                    model: componentData.enabled_actions || []

                    PaperButton {
                        text: modelData
                        role: root.actionRole(modelData)
                        compact: true
                        enabled: !root.actionBusy && !root.mockMode
                        Layout.preferredWidth: 104
                        onClicked: root.dispatch(componentData.id, modelData)
                    }
                }
            }
        }
    }

    Component {
        id: statusDelegate

        ColumnLayout {
            property var componentData: ({})

            spacing: root.spaceSm

            RowLayout {
                Layout.fillWidth: true

                Rectangle {
                    width: 10
                    height: 10
                    radius: 5
                    color: root.borderColor(componentData.status)
                }

                Text {
                    text: componentData.title || componentData.id
                    color: root.token("foreground", "#f4f7fb")
                    font.family: root.token("font_family", "Segoe UI")
                    font.pixelSize: 14
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
            }

            Text {
                text: componentData.state || componentData.status || "ready"
                color: root.borderColor(componentData.status)
                font.pixelSize: 13
                font.weight: Font.DemiBold
                elide: Text.ElideRight
                Layout.fillWidth: true
            }

            Text {
                text: root.detailText(componentData)
                color: root.token("muted", "#91a2b8")
                font.pixelSize: root.token("font_size_body", 13)
                wrapMode: Text.WordWrap
                maximumLineCount: 3
                elide: Text.ElideRight
                Layout.fillWidth: true
            }

            Text {
                text: componentData.warnings && componentData.warnings.length ? componentData.warnings.join("; ") : ""
                color: root.token("warning", "#f5c45b")
                font.pixelSize: 11
                wrapMode: Text.WordWrap
                maximumLineCount: 3
                visible: text.length > 0
                Layout.fillWidth: true
            }

            Item {
                Layout.fillHeight: true
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: root.spaceSm
                visible: !root.editMode && componentData.enabled_actions && componentData.enabled_actions.length > 0

                Repeater {
                    model: componentData.enabled_actions || []

                    PaperButton {
                        text: modelData
                        role: root.actionRole(modelData)
                        compact: true
                        enabled: !root.actionBusy && !root.mockMode
                        Layout.preferredWidth: 104
                        onClicked: root.dispatch(componentData.id, modelData)
                    }
                }
            }
        }
    }

    Component {
        id: activityDelegate

        ColumnLayout {
            property var componentData: ({})

            spacing: root.spaceSm

            Text {
                text: componentData.title || "Recent Activity"
                color: root.token("foreground", "#f4f7fb")
                font.pixelSize: 15
                font.weight: Font.DemiBold
                Layout.fillWidth: true
            }

            Repeater {
                model: componentData.data && componentData.data.items ? componentData.data.items.slice(0, 5) : []

                RowLayout {
                    Layout.fillWidth: true
                    spacing: root.spaceSm

                    Rectangle {
                        width: 8
                        height: 8
                        radius: 4
                        color: root.borderColor(modelData.status)
                    }

                    Text {
                        text: (modelData.recipe_id || "recipe") + ": " + (modelData.message || modelData.status || "")
                        color: root.token("muted", "#91a2b8")
                        font.pixelSize: 12
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                }
            }

            Item {
                Layout.fillHeight: true
            }
        }
    }

    Component {
        id: dockDelegate

        ColumnLayout {
            property var componentData: ({})

            spacing: root.spaceSm

            Text {
                text: componentData.title || "Categories"
                color: root.token("foreground", "#f4f7fb")
                font.pixelSize: 15
                font.weight: Font.DemiBold
                Layout.fillWidth: true
            }

            Repeater {
                model: componentData.data && componentData.data.categories ? componentData.data.categories : []

                Rectangle {
                    Layout.fillWidth: true
                    height: 28
                    radius: root.radiusMd
                    color: modelData === (componentData.data.selected || "") ? root.token("focus_panel", "#132235") : "transparent"
                    border.color: root.token("border", "#203044")
                    border.width: 1

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.left: parent.left
                        anchors.leftMargin: 8
                        anchors.right: parent.right
                        anchors.rightMargin: 8
                        text: modelData
                        color: root.token("muted", "#91a2b8")
                        font.pixelSize: 12
                        elide: Text.ElideRight
                    }
                }
            }

            Item {
                Layout.fillHeight: true
            }
        }
    }

    Component {
        id: textDelegate

        Text {
            property var componentData: ({})

            text: root.componentDataValue(componentData, "text", componentData.title || "")
            color: root.componentDataValue(componentData, "color", root.token("foreground", "#f4f7fb"))
            font.family: root.token("font_family", "Segoe UI")
            font.pixelSize: Number(root.componentDataValue(componentData, "size", root.componentDataValue(componentData, "font_size", 22)))
            font.bold: root.componentDataValue(componentData, "bold", false)
            horizontalAlignment: root.textHorizontalAlignment(componentData)
            wrapMode: Text.WordWrap
            elide: Text.ElideRight
            maximumLineCount: 4
        }
    }

    Component {
        id: clockDelegate

        ColumnLayout {
            id: clockRoot
            property var componentData: ({})
            property string nowText: componentData.data && componentData.data.text ? componentData.data.text : Qt.formatTime(new Date(), "hh:mm")

            Timer {
                interval: 1000
                repeat: true
                running: !root.editMode
                onTriggered: clockRoot.nowText = Qt.formatTime(new Date(), "hh:mm")
            }

            Text {
                text: clockRoot.nowText
                color: root.token("foreground", "#f4f7fb")
                font.family: root.token("font_family", "Segoe UI")
                font.pixelSize: 34
                font.bold: true
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                Layout.fillWidth: true
                Layout.fillHeight: true
            }
        }
    }

    Component {
        id: imageDelegate

        Image {
            property var componentData: ({})

            source: root.componentDataValue(componentData, "path", root.componentDataValue(componentData, "source", ""))
            fillMode: root.imageFillMode(componentData)
            asynchronous: true
            cache: true
            sourceSize.width: root.imageResolutionCap
            sourceSize.height: root.imageResolutionCap

            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                height: titleText.visible ? 34 : 0
                color: root.token("panel", "#101720")
                opacity: 0.88
                visible: titleText.visible

                Text {
                    id: titleText
                    anchors.fill: parent
                    anchors.margins: 8
                    text: componentData.title || ""
                    visible: text.length > 0
                    color: root.token("foreground", "#f4f7fb")
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }
            }
        }
    }

    Component {
        id: shapeDelegate

        Rectangle {
            property var componentData: ({})

            color: root.componentDataValue(componentData, "fill", root.componentDataValue(componentData, "color", root.token("panel_alt", "#182233")))
            radius: Number(root.componentDataValue(componentData, "radius", root.radiusLg))
            border.color: root.componentDataValue(componentData, "stroke", root.componentDataValue(componentData, "border_color", root.token("border", "#203044")))
            border.width: Number(root.componentDataValue(componentData, "border_width", 0))
        }
    }

    Rectangle {
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: 18
        width: 260
        height: 124
        radius: root.radiusLg
        color: root.token("panel", "#151d2b")
        opacity: 0.96
        border.color: root.token("border", "#203044")
        visible: root.showPerformanceOverlay

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 10
            spacing: 3

            Text {
                text: "Canvas performance"
                color: root.token("foreground", "#f4f7fb")
                font.pixelSize: 12
                font.bold: true
            }

            Text {
                text: "mode " + (root.performanceSettings.mode || "balanced") +
                      " | components " + (root.performanceCounters().component_count || root.components().length)
                color: root.token("muted", "#91a2b8")
                font.pixelSize: 11
            }

            Text {
                text: "update " + (root.performanceSettings.live_update_rate_hz || 30) +
                      "Hz | build " + Math.round(root.performanceCounters().runtime_state_build_ms || 0) + "ms"
                color: root.token("muted", "#91a2b8")
                font.pixelSize: 11
            }

            Text {
                text: "measured " + root.measuredPayloadUpdates + "/s | fps " + root.measuredFps +
                      " | payload " + Math.round(root.lastPayloadUpdateMs) + "ms"
                color: root.token("muted", "#91a2b8")
                font.pixelSize: 11
            }

            Text {
                text: "warnings " + (root.performanceCounters().warnings_count || 0) +
                      " | shadow " + root.shadowMode
                color: root.token("muted", "#91a2b8")
                font.pixelSize: 11
            }
        }
    }
}
