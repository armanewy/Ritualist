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
    property var canvasPayload: canvasController ? canvasController.payload : ritualistCanvasPayload
    property var editPayload: canvasController ? canvasController.editPayload : ritualistCanvasEditPayload
    property var performanceSettings: typeof ritualistCanvasPerformance === "undefined" ? ({}) : ritualistCanvasPerformance
    property bool editMode: canvasController ? canvasController.editMode : false
    property bool mockMode: typeof ritualistMockMode === "undefined" ? false : ritualistMockMode
    property bool animationsEnabled: performanceSettings.animations === undefined ? true : performanceSettings.animations
    property bool showPerformanceOverlay: performanceSettings.show_performance_overlay === true
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

    function componentColor(status, typeName) {
        if (status === "failed" || status === "incompatible") {
            return "#28151c"
        }
        if (status === "warning" || status === "warnings" || status === "stopped") {
            return "#252014"
        }
        if (status === "running" || status === "waiting" || status === "paused") {
            return "#132235"
        }
        if (status === "success" || status === "compatible") {
            return "#12251f"
        }
        if (typeName === "shape") {
            return "#182233"
        }
        return root.token("panel", "#101720")
    }

    function borderColor(status) {
        if (status === "failed" || status === "incompatible") {
            return "#ff6b7a"
        }
        if (status === "warning" || status === "warnings" || status === "stopped") {
            return "#f5c45b"
        }
        if (status === "running" || status === "waiting" || status === "paused") {
            return "#7fb8ff"
        }
        if (status === "success" || status === "compatible") {
            return "#3dd6a5"
        }
        return root.token("border", "#2c3c53")
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
            root.canvasPayload = root.canvasController.payload
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
        }
    }

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

                        Rectangle {
                            id: componentFrame
                            property string componentId: modelData.id
                            property bool selected: root.editMode && root.selectedComponentId() === componentId

                            x: modelData.x
                            y: modelData.y
                            z: modelData.z
                            width: modelData.width
                            height: modelData.height
                            visible: modelData.visible
                            radius: root.token("radius_md", 8)
                            color: root.componentColor(modelData.status, modelData.type)
                            border.color: selected ? root.token("accent", "#3dd6a5") : root.borderColor(modelData.status)
                            border.width: selected ? 3 : 1
                            opacity: root.actionBusy && !selected ? 0.92 : 1.0

                            Behavior on opacity {
                                enabled: root.animationsEnabled
                                NumberAnimation { duration: root.motionFastMs }
                            }

                            MouseArea {
                                id: moveArea
                                anchors.fill: parent
                                enabled: root.editMode
                                drag.target: componentFrame
                                drag.axis: Drag.XAndYAxis
                                onClicked: root.canvasController.selectComponent(componentFrame.componentId)
                                onReleased: root.canvasController.moveComponent(componentFrame.componentId, componentFrame.x, componentFrame.y)
                            }

                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: root.token("spacing_md", 12)
                                spacing: root.token("spacing_sm", 6)

                                Text {
                                    text: modelData.title || modelData.id
                                    color: root.token("foreground", "#f4f7fb")
                                    font.family: root.token("font_family", "Segoe UI")
                                    font.pixelSize: modelData.type === "text.label" ? 18 : 15
                                    font.bold: true
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }

                                Text {
                                    text: modelData.subtitle || modelData.message || modelData.type
                                    color: root.token("muted", "#91a2b8")
                                    font.family: root.token("font_family", "Segoe UI")
                                    font.pixelSize: 12
                                    wrapMode: Text.WordWrap
                                    maximumLineCount: 3
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }

                                Text {
                                    text: modelData.warnings && modelData.warnings.length ? modelData.warnings.join("; ") : ""
                                    color: "#f5c45b"
                                    font.pixelSize: 11
                                    wrapMode: Text.WordWrap
                                    maximumLineCount: 3
                                    elide: Text.ElideRight
                                    visible: text.length > 0
                                    Layout.fillWidth: true
                                }

                                Text {
                                    text: root.editMode ? (modelData.id + " | " + modelData.type) : ""
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
                                    visible: !root.editMode && modelData.enabled_actions && modelData.enabled_actions.length > 0

                                    Repeater {
                                        model: modelData.enabled_actions || []

                                        Button {
                                            text: modelData
                                            enabled: !root.actionBusy && !root.mockMode
                                            Layout.preferredWidth: 96
                                            onClicked: root.dispatch(componentFrame.componentId, modelData)
                                        }
                                    }
                                }
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
                                        componentFrame.width = Math.max(32, startWidth + mouse.x - startX)
                                        componentFrame.height = Math.max(24, startHeight + mouse.y - startY)
                                    }
                                    onReleased: root.canvasController.resizeComponent(componentFrame.componentId, componentFrame.width, componentFrame.height)
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

    Rectangle {
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: 18
        width: 260
        height: 104
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
                text: "warnings " + (root.performanceCounters().warnings_count || 0)
                color: root.token("muted", "#91a2b8")
                font.pixelSize: 11
            }
        }
    }
}
