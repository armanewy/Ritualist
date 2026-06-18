import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Rectangle {
    id: root

    RitualistTokens {
        id: tokens
    }

    property var ritual: ({})
    property bool selected: false
    property string ritualId: ritual.id || ritual.recipe_id || ""
    property string title: ritual.title || ritual.name || "Untitled ritual"
    property string subtitle: ritual.room_name || ritual.room || ritual.readiness_summary || ritual.description || "Recent ritual"
    property string status: ritual.status || ritual.last_run_status || (ritual.active_summary ? "running" : "ready")

    signal rowSelected()
    signal preflightRequested(string ritualId)

    height: 62
    radius: 6
    color: selected ? tokens.runningPanel : (pointer.containsMouse ? tokens.panelAlt : tokens.panel)
    border.color: selected ? tokens.focusRing : tokens.border
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
            color: status === "failed" ? tokens.failure : (status === "running" ? tokens.running : tokens.accent)
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 3

            Text {
                Layout.fillWidth: true
                text: root.title
                color: tokens.text
                font.family: tokens.fontFamily
                font.pixelSize: tokens.bodyFontEpx
                font.weight: Font.DemiBold
                elide: Text.ElideRight
            }

            Text {
                Layout.fillWidth: true
                text: root.subtitle
                color: tokens.textMuted
                font.family: tokens.fontFamily
                font.pixelSize: tokens.captionFontEpx
                elide: Text.ElideRight
            }
        }

        Text {
            text: "Preflight"
            color: tokens.accent
            font.family: tokens.fontFamily
            font.pixelSize: tokens.captionFontEpx
            font.weight: Font.DemiBold
            visible: root.selected
        }
    }
}
