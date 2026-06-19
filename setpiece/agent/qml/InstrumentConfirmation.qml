import QtQuick
import QtQuick.Layouts

Item {
    id: root

    property var tokens: SetpieceTokens {}
    property var payload: ({})
    property var currentStep: ({})
    property var completedSteps: []
    property var futureSteps: []
    property bool reducedMotion: false

    function confirmation() {
        return root.payload.confirmation || ({})
    }

    function textOr(value, fallback) {
        var text = String(value || "").trim()
        return text.length > 0 ? text : fallback
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: root.tokens.spaceMd

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 150
            radius: root.tokens.controlRadiusEpx
            color: root.tokens.semanticPanel("confirmation")
            border.color: root.tokens.confirmation
            border.width: 1

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: root.tokens.spaceMd
                spacing: 6

                Text {
                    Layout.fillWidth: true
                    text: "Confirmation required"
                    color: root.tokens.confirmation
                    font.family: root.tokens.fontFamily
                    font.pixelSize: root.tokens.bodyFontEpx
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }

                Text {
                    Layout.fillWidth: true
                    text: root.textOr(root.confirmation().consequence, root.payload.summary || "Setpiece needs your decision before it continues.")
                    color: root.tokens.text
                    font.family: root.tokens.fontFamily
                    font.pixelSize: root.tokens.titleFontEpx
                    font.weight: Font.DemiBold
                    wrapMode: Text.WordWrap
                }

                Text {
                    Layout.fillWidth: true
                    text: "Target: " + root.textOr(root.confirmation().target, "current app")
                    color: root.tokens.textMuted
                    font.family: root.tokens.fontFamily
                    font.pixelSize: root.tokens.captionFontEpx
                    elide: Text.ElideRight
                }
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: root.tokens.spaceSm

            Text {
                Layout.fillWidth: true
                text: root.textOr(root.confirmation().safe_negative_path, "Cancel stops safely before this action.")
                color: root.tokens.text
                font.family: root.tokens.fontFamily
                font.pixelSize: root.tokens.bodyFontEpx
                wrapMode: Text.WordWrap
            }

            Text {
                Layout.fillWidth: true
                text: root.textOr(root.confirmation().preserved_work, "Completed work remains recorded.")
                color: root.tokens.textMuted
                font.family: root.tokens.fontFamily
                font.pixelSize: root.tokens.captionFontEpx
                wrapMode: Text.WordWrap
            }

            Text {
                Layout.fillWidth: true
                visible: root.confirmation().remembered_approval_summary
                text: root.confirmation().remembered_approval_summary || ""
                color: root.tokens.confirmation
                font.family: root.tokens.fontFamily
                font.pixelSize: root.tokens.captionFontEpx
                wrapMode: Text.WordWrap
            }
        }

        Item {
            Layout.fillHeight: true
        }
    }
}
