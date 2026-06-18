import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Rectangle {
    id: root

    property var ritual: ({})
    property bool selected: false
    property string ritualId: ritual.id || ritual.recipe_id || ""
    property string title: ritual.title || ritual.name || "Untitled ritual"
    property string subtitle: ritual.room || ritual.description || "Recent ritual"
    property string status: ritual.status || ritual.last_run_status || "ready"

    signal rowSelected()
    signal preflightRequested(string ritualId)

    height: 62
    radius: 6
    color: selected ? "#1b2a3a" : (pointer.containsMouse ? "#151f2b" : "#101720")
    border.color: selected ? "#6ea8e8" : "#223044"
    border.width: 1
    activeFocusOnTab: true

    Accessible.role: Accessible.ListItem
    Accessible.name: title
    Accessible.description: "Press Enter to open preflight. Double-click does not start a ritual."

    Keys.onPressed: function(event) {
        if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
            root.preflightRequested(root.ritualId)
            event.accepted = true
        } else if (event.key === Qt.Key_Space) {
            root.rowSelected()
            event.accepted = true
        }
    }

    MouseArea {
        id: pointer

        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton
        onClicked: {
            root.forceActiveFocus()
            root.rowSelected()
        }
        onDoubleClicked: function(mouse) {
            mouse.accepted = true
            root.rowSelected()
        }
    }

    RowLayout {
        anchors.fill: parent
        anchors.margins: 10
        spacing: 10

        Rectangle {
            Layout.preferredWidth: 10
            Layout.preferredHeight: 10
            radius: 5
            color: status === "failed" ? "#d96d7e" : (status === "running" ? "#63d6a3" : "#7fb8ff")
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 3

            Text {
                Layout.fillWidth: true
                text: root.title
                color: "#f2f6fb"
                font.pixelSize: 13
                font.weight: Font.DemiBold
                elide: Text.ElideRight
            }

            Text {
                Layout.fillWidth: true
                text: root.subtitle
                color: "#91a2b8"
                font.pixelSize: 11
                elide: Text.ElideRight
            }
        }

        Text {
            text: "Preflight"
            color: "#b8d8ff"
            font.pixelSize: 11
            font.weight: Font.DemiBold
            visible: root.selected
        }
    }
}
