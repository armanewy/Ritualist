import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Window

Window {
    id: root

    SetpieceTokens {
        id: tokens
    }

    width: 400
    height: 520
    minimumWidth: 336
    maximumHeight: 520
    visible: false
    flags: Qt.Window | Qt.FramelessWindowHint
    color: "transparent"
    title: "Setpiece Picker"

    property var pickerController: typeof setpiecePickerController === "undefined" ? null : setpiecePickerController
    property var pickerPayload: pickerController && pickerController.payload ? pickerController.payload : ({
        "current_room": { "room_id": "", "name": "Current Room" },
        "recent_rituals": [],
        "matching_rituals": [],
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
        var room = pickerPayload && pickerPayload.current_room ? pickerPayload.current_room : (pickerPayload && pickerPayload.room ? pickerPayload.room : {})
        return room.name || room.label || "Current Room"
    }

    function activeRitual() {
        if (!pickerPayload || !pickerPayload.active_ritual) {
            return null
        }
        return pickerPayload.active_ritual
    }

    function recentRituals() {
        if (!pickerPayload) {
            return []
        }
        var source = pickerPayload.recent_rituals && pickerPayload.recent_rituals.length > 0
                ? pickerPayload.recent_rituals
                : (pickerPayload.matching_rituals || [])
        var needle = query.trim().toLowerCase()
        if (needle === "") {
            return source
        }
        var filtered = []
        for (var i = 0; i < source.length; i += 1) {
            var item = source[i]
            var haystack = String((item.title || item.name || "") + " " + (item.room_name || item.room || "") + " " + (item.description || "") + " " + (item.intent_summary || "")).toLowerCase()
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
        if (pickerController && pickerController.openPreflight) {
            pickerController.openPreflight(ritualId)
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
    onVisibleChanged: {
        if (visible) {
            searchField.forceActiveFocus()
        }
    }

    Component.onCompleted: searchField.forceActiveFocus()

    Rectangle {
        id: surface

        anchors.fill: parent
        radius: 8
        color: tokens.panel
        border.color: tokens.border
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
                color: tokens.panelAlt
                border.color: tokens.border

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 10
                    spacing: 8

                    Text {
                        text: "Current Room"
                        color: tokens.textMuted
                        font.family: tokens.fontFamily
                        font.pixelSize: tokens.captionFontEpx
                        font.weight: Font.DemiBold
                    }

                    Text {
                        Layout.fillWidth: true
                        text: root.roomName()
                        color: tokens.text
                        font.family: tokens.fontFamily
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
                    color: tokens.text
                    font.family: tokens.fontFamily
                    font.pixelSize: tokens.bodyFontEpx
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }

                ToolButton {
                    text: "Browse all rituals"
                    Accessible.name: "Browse all rituals"
                    onClicked: {
                        if (root.pickerController && root.pickerController.browseAll) {
                            root.pickerController.browseAll()
                        }
                        root.requestBrowseAllRituals()
                    }
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
                    onClicked: {
                        if (root.pickerController && root.pickerController.openBuilder) {
                            root.pickerController.openBuilder()
                        }
                        root.requestOpenBuilder()
                    }
                }

                ToolButton {
                    Layout.fillWidth: true
                    text: "Open Builder"
                    visible: !root.compactActions
                    Accessible.name: "Open Builder"
                    onClicked: {
                        if (root.pickerController && root.pickerController.openBuilder) {
                            root.pickerController.openBuilder()
                        }
                        root.requestOpenBuilder()
                    }
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
                            onTriggered: {
                                if (root.pickerController && root.pickerController.openBuilder) {
                                    root.pickerController.openBuilder()
                                }
                                root.requestOpenBuilder()
                            }
                        }

                        MenuItem {
                            text: "Open Builder"
                            onTriggered: {
                                if (root.pickerController && root.pickerController.openBuilder) {
                                    root.pickerController.openBuilder()
                                }
                                root.requestOpenBuilder()
                            }
                        }
                    }
                }
            }
        }
    }
}
