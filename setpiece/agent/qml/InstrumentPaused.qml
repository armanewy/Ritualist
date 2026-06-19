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

    function titleFor(step, fallback) {
        if (!step) {
            return fallback
        }
        return step.title || step.name || step.label || fallback
    }

    function detailFor(step, fallback) {
        if (!step) {
            return fallback
        }
        return step.detail || step.summary || step.description || fallback
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: root.tokens.spaceMd

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 118
            radius: root.tokens.controlRadiusEpx
            color: root.tokens.semanticPanel("paused")
            border.color: root.tokens.paused
            border.width: 1

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: root.tokens.spaceMd
                spacing: 5

                Text {
                    Layout.fillWidth: true
                    text: "Paused"
                    color: root.tokens.paused
                    font.family: root.tokens.fontFamily
                    font.pixelSize: root.tokens.bodyFontEpx
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }

                Text {
                    Layout.fillWidth: true
                    text: root.titleFor(root.currentStep, root.payload.title || "Ritual is paused")
                    color: root.tokens.text
                    font.family: root.tokens.fontFamily
                    font.pixelSize: root.tokens.titleFontEpx
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }

                Text {
                    Layout.fillWidth: true
                    text: root.detailFor(root.currentStep, root.payload.summary || "Resume when the desktop is ready.")
                    color: root.tokens.textMuted
                    font.family: root.tokens.fontFamily
                    font.pixelSize: root.tokens.captionFontEpx
                    elide: Text.ElideRight
                }
            }
        }

        Text {
            Layout.fillWidth: true
            text: root.completedSteps.length + " completed - " + root.futureSteps.length + " upcoming"
            color: root.tokens.textMuted
            font.family: root.tokens.fontFamily
            font.pixelSize: root.tokens.captionFontEpx
            elide: Text.ElideRight
        }

        Item {
            Layout.fillHeight: true
        }
    }
}
