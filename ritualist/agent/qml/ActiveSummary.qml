import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Rectangle {
    id: root

    property var activeRitual: null
    property bool hasActiveRitual: activeRitual !== null && activeRitual !== undefined
    property bool pendingConfirmation: hasActiveRitual && (
        activeRitual.pending_confirmation === true ||
        activeRitual.state === "confirmation" ||
        activeRitual.status === "confirmation"
    )
    property string ritualName: hasActiveRitual ? (activeRitual.title || activeRitual.name || "Active ritual") : ""
    property string stateLabel: hasActiveRitual ? (activeRitual.state || activeRitual.status || "running") : ""
    property string detailText: hasActiveRitual ? (activeRitual.current_step || activeRitual.message || activeRitual.description || "") : ""

    signal requestOpenActive()

    height: hasActiveRitual ? 78 : 0
    radius: 6
    color: pendingConfirmation ? "#251f14" : "#12241d"
    border.color: pendingConfirmation ? "#f5c96b" : "#58d2a3"
    border.width: 1
    Accessible.role: Accessible.Pane
    Accessible.name: "Active ritual summary"
    Accessible.description: ritualName + " " + stateLabel

    RowLayout {
        anchors.fill: parent
        anchors.margins: 10
        spacing: 10

        Rectangle {
            Layout.preferredWidth: 10
            Layout.preferredHeight: 10
            radius: 5
            color: root.pendingConfirmation ? "#f5c96b" : "#58d2a3"
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 3

            Text {
                Layout.fillWidth: true
                text: "Active ritual"
                color: root.pendingConfirmation ? "#f6d37a" : "#bbf5d1"
                font.pixelSize: 11
                font.weight: Font.DemiBold
                elide: Text.ElideRight
            }

            Text {
                Layout.fillWidth: true
                text: root.ritualName
                color: "#f2f6fb"
                font.pixelSize: 13
                font.weight: Font.DemiBold
                elide: Text.ElideRight
            }

            Text {
                Layout.fillWidth: true
                text: root.stateLabel + (root.detailText ? " - " + root.detailText : "")
                color: "#aebbd0"
                font.pixelSize: 11
                elide: Text.ElideRight
            }
        }

        ToolButton {
            text: "Show"
            Accessible.name: "Show active ritual"
            onClicked: root.requestOpenActive()
        }
    }
}
