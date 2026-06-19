import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Rectangle {
    id: root

    SetpieceTokens {
        id: tokens
    }

    property var activeRitual: null
    property bool hasActiveRitual: activeRitual !== null && activeRitual !== undefined
    property bool pendingConfirmation: hasActiveRitual && (
        activeRitual.pending_confirmation === true ||
        activeRitual.state === "confirmation" ||
        activeRitual.status === "confirmation"
    )
    property string ritualName: hasActiveRitual ? (activeRitual.title || activeRitual.name || "Active ritual") : ""
    property string stateLabel: hasActiveRitual ? (activeRitual.state || activeRitual.status || "running") : ""
    property string detailText: hasActiveRitual ? (activeRitual.summary || activeRitual.current_step || activeRitual.message || activeRitual.description || "") : ""

    signal requestOpenActive()

    height: hasActiveRitual ? 78 : 0
    radius: 6
    color: pendingConfirmation ? tokens.confirmationPanel : tokens.runningPanel
    border.color: pendingConfirmation ? tokens.confirmation : tokens.running
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
            color: root.pendingConfirmation ? tokens.confirmation : tokens.running
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 3

            Text {
                Layout.fillWidth: true
                text: "Active ritual"
                color: root.pendingConfirmation ? tokens.confirmation : tokens.running
                font.family: tokens.fontFamily
                font.pixelSize: tokens.captionFontEpx
                font.weight: Font.DemiBold
                elide: Text.ElideRight
            }

            Text {
                Layout.fillWidth: true
                text: root.ritualName
                color: tokens.text
                font.family: tokens.fontFamily
                font.pixelSize: tokens.bodyFontEpx
                font.weight: Font.DemiBold
                elide: Text.ElideRight
            }

            Text {
                Layout.fillWidth: true
                text: root.stateLabel + (root.detailText ? " - " + root.detailText : "")
                color: tokens.textMuted
                font.family: tokens.fontFamily
                font.pixelSize: tokens.captionFontEpx
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
