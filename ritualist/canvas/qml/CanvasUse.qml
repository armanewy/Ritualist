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
    property bool mockMode: typeof ritualistMockMode === "undefined" ? false : ritualistMockMode
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
        return "#101720"
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
        return "#2c3c53"
    }

    function dispatch(componentId, actionId) {
        if (!canvasController || actionBusy || mockMode) {
            return
        }
        canvasController.dispatchAction(componentId, actionId)
    }

    Connections {
        target: root.canvasController

        function onPayloadChanged() {
            root.canvasPayload = root.canvasController.payload
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
        color: "#070c13"
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
                    color: "#f4f7fb"
                    font.pixelSize: 26
                    font.bold: true
                }

                Text {
                    text: root.footerText
                    color: "#91a2b8"
                    font.pixelSize: 13
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
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
                color: "#0b1018"
                border.color: "#1d2a3a"
                border.width: 1

                Repeater {
                    model: root.components()

                    Rectangle {
                        id: componentFrame
                        property string componentId: modelData.id

                        x: modelData.x
                        y: modelData.y
                        z: modelData.z
                        width: modelData.width
                        height: modelData.height
                        visible: modelData.visible
                        radius: 8
                        color: root.componentColor(modelData.status, modelData.type)
                        border.color: root.borderColor(modelData.status)
                        border.width: 1

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 12
                            spacing: 8

                            Text {
                                text: modelData.title || modelData.id
                                color: "#f4f7fb"
                                font.pixelSize: modelData.type === "text.label" ? 18 : 15
                                font.bold: true
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }

                            Text {
                                text: modelData.subtitle || modelData.message || modelData.type
                                color: "#91a2b8"
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

                            Item {
                                Layout.fillHeight: true
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 6
                                visible: modelData.enabled_actions && modelData.enabled_actions.length > 0

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
                    }
                }
            }
        }
    }
}
