import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Window

Window {
    id: root

    width: 400
    height: 520
    minimumWidth: 336
    maximumHeight: 520
    visible: true
    flags: Qt.Tool | Qt.FramelessWindowHint
    color: "transparent"
    title: "Ritualist Picker"

    property var pickerController: typeof ritualistPickerController === "undefined" ? null : ritualistPickerController
    property var pickerPayload: pickerController && pickerController.payload ? pickerController.payload : ({
        "room": { "id": "", "name": "Current Room" },
        "recent_rituals": [],
        "active_ritual": null
    })
    property string query: ""
    property int selectedIndex: 0
    property bool actionBusy: pickerController ? pickerController.actionBusy : false
    property bool compactActions: width < 380
    property bool idle: !actionBusy && !activeSummary.pendingConfirmation

    signal requestPreflight(string ritualId)
    signal requestBrowseAllRituals()
    signal requestOpenBuilder()
    signal requestDismiss(string reason)
    signal requestReturnFocusToPriorApp()

    function roomName() {
        var room = pickerPayload && pickerPayload.room ? pickerPayload.room : {}
        return room.name || room.label || "Current Room"
    }

    function activeRitual() {
        if (!pickerPayload || !pickerPayload.active_ritual) {
            return null
        }
        return pickerPayload.active_ritual
    }

    function recentRituals() {
        if (!pickerPayload || !pickerPayload.recent_rituals) {
            return []
        }
        var needle = query.trim().toLowerCase()
        if (needle === "") {
            return pickerPayload.recent_rituals
        }
        var filtered = []
        for (var i = 0; i < pickerPayload.recent_rituals.length; i += 1) {
            var item = pickerPayload.recent_rituals[i]
            var haystack = String((item.title || item.name || "") + " " + (item.room || "") + " " + (item.description || "")).toLowerCase()
            if (haystack.indexOf(needle) >= 0) {
                filtered.push(item)
            }
        }
        return filtered
    }

    function ritualIdAt(index) {
        var rituals = recentRituals()
        if (index < 0 || index >= rituals.length) {
            return ""
        }
        return rituals[index].id || rituals[index].recipe_id || ""
    }

    function openPreflight(ritualId) {
        if (!ritualId || actionBusy) {
            return
        }
        requestPreflight(ritualId)
        dismissIfIdle("preflight")
    }

    function dismissIfIdle(reason) {
        if (!idle) {
            return
        }
        requestDismiss(reason)
        requestReturnFocusToPriorApp()
        close()
    }

    function dismissFromHotkey() {
        dismissIfIdle("hotkey")
    }

    onActiveChanged: {
        if (!active) {
            dismissIfIdle("outside")
        }
    }

    Component.onCompleted: searchField.forceActiveFocus()

    Rectangle {
        id: surface

        anchors.fill: parent
        radius: 8
        color: "#0d1118"
        border.color: "#2a3748"
        border.width: 1
        focus: true

        Keys.onPressed: function(event) {
            if (event.key === Qt.Key_Escape) {
                root.dismissIfIdle("escape")
                event.accepted = true
                return
            }
            if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                root.openPreflight(root.ritualIdAt(root.selectedIndex))
                event.accepted = true
                return
            }
            if (event.key === Qt.Key_Down) {
                root.selectedIndex = Math.min(root.selectedIndex + 1, Math.max(0, ritualList.count - 1))
                ritualList.currentIndex = root.selectedIndex
                event.accepted = true
                return
            }
            if (event.key === Qt.Key_Up) {
                root.selectedIndex = Math.max(0, root.selectedIndex - 1)
                ritualList.currentIndex = root.selectedIndex
                event.accepted = true
            }
        }

        ColumnLayout {
            id: content

            anchors.fill: parent
            anchors.margins: 14
            spacing: 10

            TextField {
                id: searchField

                Layout.fillWidth: true
                Layout.preferredHeight: 40
                placeholderText: "Search rituals"
                text: root.query
                selectByMouse: true
                activeFocusOnTab: true
                Accessible.name: "Search rituals"
                Accessible.description: "Search recent rituals and open a ritual preflight with Enter."
                onTextChanged: {
                    root.query = text
                    root.selectedIndex = 0
                    ritualList.currentIndex = 0
                }
                Keys.onPressed: function(event) {
                    if (event.key === Qt.Key_Escape) {
                        root.dismissIfIdle("escape")
                        event.accepted = true
                    } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                        root.openPreflight(root.ritualIdAt(root.selectedIndex))
                        event.accepted = true
                    }
                }
            }

            Rectangle {
                id: roomStrip

                Layout.fillWidth: true
                Layout.preferredHeight: 48
                radius: 6
                color: "#121a24"
                border.color: "#273549"

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 10
                    spacing: 8

                    Text {
                        text: "Current Room"
                        color: "#8fa0b8"
                        font.pixelSize: 11
                        font.weight: Font.DemiBold
                    }

                    Text {
                        Layout.fillWidth: true
                        text: root.roomName()
                        color: "#f2f6fb"
                        font.pixelSize: 14
                        font.weight: Font.DemiBold
                        elide: Text.ElideRight
                    }
                }
            }

            ActiveSummary {
                id: activeSummary

                Layout.fillWidth: true
                activeRitual: root.activeRitual()
                visible: hasActiveRitual
                onRequestOpenActive: {
                    if (root.pickerController && root.pickerController.openActiveRitual) {
                        root.pickerController.openActiveRitual()
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                Text {
                    Layout.fillWidth: true
                    text: "Recent rituals"
                    color: "#dce6f2"
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }

                ToolButton {
                    text: "Browse all rituals"
                    Accessible.name: "Browse all rituals"
                    onClicked: root.requestBrowseAllRituals()
                }
            }

            ListView {
                id: ritualList

                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumHeight: 120
                clip: true
                spacing: 6
                currentIndex: root.selectedIndex
                model: root.recentRituals()

                delegate: PickerRow {
                    width: ritualList.width
                    ritual: modelData
                    selected: index === root.selectedIndex
                    onRowSelected: {
                        root.selectedIndex = index
                        ritualList.currentIndex = index
                    }
                    onPreflightRequested: function(ritualId) {
                        root.selectedIndex = index
                        root.openPreflight(ritualId)
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                ToolButton {
                    Layout.fillWidth: true
                    text: "New ritual"
                    visible: !root.compactActions
                    Accessible.name: "New ritual"
                    onClicked: root.requestOpenBuilder()
                }

                ToolButton {
                    Layout.fillWidth: true
                    text: "Open Builder"
                    visible: !root.compactActions
                    Accessible.name: "Open Builder"
                    onClicked: root.requestOpenBuilder()
                }

                ToolButton {
                    id: overflowButton

                    Layout.fillWidth: true
                    text: "More"
                    visible: root.compactActions
                    Accessible.name: "More picker actions"
                    onClicked: overflowMenu.open()

                    Menu {
                        id: overflowMenu

                        MenuItem {
                            text: "New ritual"
                            onTriggered: root.requestOpenBuilder()
                        }

                        MenuItem {
                            text: "Open Builder"
                            onTriggered: root.requestOpenBuilder()
                        }
                    }
                }
            }
        }
    }
}
