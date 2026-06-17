import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: root
    width: 1280
    height: 760
    visible: true
    title: "Ritualist Canvas"

    property var canvasController: typeof ritualistCanvasUseController === "undefined" ? null : ritualistCanvasUseController
    property var canvasPayload: typeof ritualistCanvasPayload === "undefined" ? ({}) : ritualistCanvasPayload
    property var editPayload: canvasController ? canvasController.editPayload : ritualistCanvasEditPayload
    property var performanceSettings: typeof ritualistCanvasPerformance === "undefined" ? ({}) : ritualistCanvasPerformance
    property bool editMode: canvasController ? canvasController.editMode : false
    property bool mockMode: typeof ritualistMockMode === "undefined" ? false : ritualistMockMode
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
        return tokens[name] || fallback
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

    function componentColor(status, typeName) {
        if (status === "failed" || status === "incompatible") {
            return root.token("danger_panel", "#28151c")
        }
        if (status === "warning" || status === "warnings" || status === "stopped") {
            return root.token("warning_panel", "#252014")
        }
        if (status === "running" || status === "waiting" || status === "paused") {
            return root.token("focus_panel", "#132235")
        }
        if (status === "success" || status === "compatible") {
            return root.token("success_panel", "#12251f")
        }
        if (typeName === "shape") {
            return root.token("panel_alt", "#182233")
        }
        return root.token("panel", "#101720")
    }

    function borderColor(status) {
        if (status === "failed" || status === "incompatible") {
            return root.token("danger", "#ff6b7a")
        }
        if (status === "warning" || status === "warnings" || status === "stopped") {
            return root.token("warning", "#f5c45b")
        }
        if (status === "running" || status === "waiting" || status === "paused") {
            return root.token("focus_ring", "#7fb8ff")
        }
        if (status === "success" || status === "compatible") {
            return root.token("success", root.token("accent", "#3dd6a5"))
        }
        return root.token("border", "#2c3c53")
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
        id: frameApproximationTimer
        interval: 16
        repeat: true
        running: root.showPerformanceOverlay
        onTriggered: root.frameTicksThisSecond += 1
    }

    Component.onCompleted: root.requestPayloadUpdate(true)

    Rectangle {
        anchors.fill: parent
        color: root.token("background", "#070c13")
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 18
        spacing: 12

        RowLayout {
            Layout.fillWidth: true
            spacing: 12

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2

                Text {
                    text: root.canvasName()
                    color: root.token("foreground", "#f4f7fb")
                    font.family: root.token("font_family", "Segoe UI")
                    font.pixelSize: root.token("font_size_title", 26)
                    font.bold: true
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

            Button {
                text: root.editMode ? "Use Mode" : "Edit Mode"
                enabled: root.canvasController && !root.runtimeActive
                onClicked: root.canvasController.setEditMode(!root.editMode)
            }

            Button {
                text: "Pause"
                enabled: root.runtimeActive && !root.runtimePaused && root.canvasController
                onClicked: root.canvasController.pauseCurrentRun()
            }

            Button {
                text: "Resume"
                enabled: root.runtimeActive && root.runtimePaused && root.canvasController
                onClicked: root.canvasController.resumeCurrentRun()
            }

            Button {
                text: "Stop"
                enabled: root.runtimeActive && root.canvasController
                onClicked: root.canvasController.stopCurrentRun()
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 12

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
                    color: root.token("panel_alt", "#0b1018")
                    border.color: root.editMode ? root.token("accent", "#3dd6a5") : root.token("border", "#1d2a3a")
                    border.width: root.editMode ? 2 : 1

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
                                radius: root.token("radius_md", 8)
                                color: "#000000"
                                opacity: root.shadowMode === "rich" ? 0.32 : 0.16
                                visible: root.shadowMode !== "none" && index < root.maxAnimatedComponents
                            }

                            Rectangle {
                            id: componentFrame
                            property string componentId: componentShell.componentId
                            property bool selected: componentShell.selected

                            anchors.fill: parent
                            radius: root.token("radius_md", 8)
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
                                anchors.margins: root.token("spacing_md", 12)
                                property var componentData: modelData
                                sourceComponent: root.delegateFor(modelData.type)
                                onLoaded: item.componentData = componentData
                            }

                            Rectangle {
                                width: 18
                                height: 18
                                radius: 3
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
                color: "#0e151f"
                border.color: root.token("border", "#203044")
                border.width: 1
                radius: root.token("radius_md", 8)

                ScrollView {
                    anchors.fill: parent
                    anchors.margins: 12

                    ColumnLayout {
                        width: parent.width
                        spacing: 10

                        Text {
                            text: "Edit Mode"
                            color: root.token("foreground", "#f4f7fb")
                            font.pixelSize: 20
                            font.bold: true
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            Button { text: "Save"; enabled: root.canvasController && root.editPayload && root.editPayload.dirty; onClicked: root.canvasController.saveCanvas() }
                            Button { text: "Discard"; enabled: root.canvasController && root.editPayload && root.editPayload.dirty; onClicked: root.canvasController.discardEdit() }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            Button { text: "Undo"; enabled: root.canvasController && root.editPayload && root.editPayload.history && root.editPayload.history.can_undo; onClicked: root.canvasController.undoEdit() }
                            Button { text: "Redo"; enabled: root.canvasController && root.editPayload && root.editPayload.history && root.editPayload.history.can_redo; onClicked: root.canvasController.redoEdit() }
                        }

                        Text {
                            text: "Palette"
                            color: "#91a2b8"
                            font.pixelSize: 13
                            font.bold: true
                        }

                        Repeater {
                            model: root.paletteEntries()

                            Button {
                                text: modelData.display_name
                                Layout.fillWidth: true
                                onClicked: root.canvasController.addComponent(modelData.type_id)
                            }
                        }

                        Rectangle {
                            height: 1
                            color: "#203044"
                            Layout.fillWidth: true
                        }

                        Text {
                            text: root.selectedComponentId() ? (root.selectedComponent().id + " | " + root.selectedComponent().type) : "Select a component"
                            color: "#f4f7fb"
                            font.pixelSize: 15
                            font.bold: true
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            visible: root.selectedComponentId().length > 0
                            Button { text: "Duplicate"; onClicked: root.canvasController.duplicateSelectedComponent() }
                            Button { text: "Delete"; onClicked: root.canvasController.deleteSelectedComponent() }
                        }

                        Text {
                            text: "Properties"
                            color: "#91a2b8"
                            font.pixelSize: 13
                            font.bold: true
                            visible: root.selectedComponentId().length > 0
                        }

                        Repeater {
                            model: root.selectedPropertySchema()

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 4

                                Text {
                                    text: modelData.label
                                    color: "#91a2b8"
                                    font.pixelSize: 11
                                }

                                ComboBox {
                                    Layout.fillWidth: true
                                    visible: modelData.allowed_values && modelData.allowed_values.length > 0
                                    model: modelData.allowed_values || []
                                    currentIndex: Math.max(0, (modelData.allowed_values || []).indexOf(String(root.selectedProps()[modelData.name] || modelData.default || "")))
                                    onActivated: root.canvasController.editComponentProperty(root.selectedComponentId(), modelData.name, currentText)
                                }

                                TextField {
                                    Layout.fillWidth: true
                                    visible: !(modelData.allowed_values && modelData.allowed_values.length > 0)
                                    text: String(root.selectedProps()[modelData.name] === undefined || root.selectedProps()[modelData.name] === null ? (modelData.default || "") : root.selectedProps()[modelData.name])
                                    onEditingFinished: root.canvasController.editComponentProperty(root.selectedComponentId(), modelData.name, text)
                                }
                            }
                        }

                        Text {
                            text: "Binding"
                            color: "#91a2b8"
                            font.pixelSize: 13
                            font.bold: true
                            visible: root.selectedComponentId().length > 0
                        }

                        ComboBox {
                            id: bindingKind
                            Layout.fillWidth: true
                            visible: root.selectedComponentId().length > 0
                            model: root.selectedSupportedBindings()
                            currentIndex: Math.max(0, root.selectedSupportedBindings().indexOf(root.selectedBinding().kind || "static"))
                        }

                        TextField {
                            id: bindingReference
                            Layout.fillWidth: true
                            visible: root.selectedComponentId().length > 0
                            placeholderText: "Binding reference"
                            text: root.selectedBinding().recipe_id || root.selectedBinding().target || root.selectedBinding().intent_id || root.selectedBinding().id || ""
                        }

                        Button {
                            text: "Apply Binding"
                            visible: root.selectedComponentId().length > 0
                            Layout.fillWidth: true
                            onClicked: root.canvasController.editComponentBinding(root.selectedComponentId(), bindingKind.currentText || "static", bindingReference.text)
                        }

                        Text {
                            text: root.editPayload && root.editPayload.validation && root.editPayload.validation.errors.length ? root.editPayload.validation.errors.join("; ") : ""
                            color: "#ff6b7a"
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
                font.pixelSize: 15
                font.bold: true
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
                spacing: 6
                visible: !root.editMode && componentData.enabled_actions && componentData.enabled_actions.length > 0

                Repeater {
                    model: componentData.enabled_actions || []

                    Button {
                        text: modelData
                        enabled: !root.actionBusy && !root.mockMode
                        Layout.preferredWidth: 96
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

            spacing: root.token("spacing_sm", 6)

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
                    font.bold: true
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
            }

            Text {
                text: componentData.state || componentData.status || "ready"
                color: root.token("focus_ring", "#7fb8ff")
                font.pixelSize: 12
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
                spacing: 6
                visible: !root.editMode && componentData.enabled_actions && componentData.enabled_actions.length > 0

                Repeater {
                    model: componentData.enabled_actions || []

                    Button {
                        text: modelData
                        enabled: !root.actionBusy && !root.mockMode
                        Layout.preferredWidth: 92
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

            spacing: root.token("spacing_sm", 6)

            Text {
                text: componentData.title || "Recent Activity"
                color: root.token("foreground", "#f4f7fb")
                font.pixelSize: 15
                font.bold: true
                Layout.fillWidth: true
            }

            Repeater {
                model: componentData.data && componentData.data.items ? componentData.data.items.slice(0, 5) : []

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 6

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

            spacing: root.token("spacing_sm", 6)

            Text {
                text: componentData.title || "Categories"
                color: root.token("foreground", "#f4f7fb")
                font.pixelSize: 15
                font.bold: true
                Layout.fillWidth: true
            }

            Repeater {
                model: componentData.data && componentData.data.categories ? componentData.data.categories : []

                Rectangle {
                    Layout.fillWidth: true
                    height: 28
                    radius: root.token("radius_sm", 4)
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
                color: "#99000000"
                visible: titleText.visible

                Text {
                    id: titleText
                    anchors.fill: parent
                    anchors.margins: 8
                    text: componentData.title || ""
                    visible: text.length > 0
                    color: "#ffffff"
                    font.pixelSize: 13
                    font.bold: true
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
            radius: Number(root.componentDataValue(componentData, "radius", root.token("radius_md", 8)))
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
        radius: root.token("radius_md", 8)
        color: "#151d2b"
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
