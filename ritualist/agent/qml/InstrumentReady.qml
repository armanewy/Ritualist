import QtQuick
import QtQuick.Layouts

Item {
    id: root

    property var tokens: RitualistTokens {}
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

        Text {
            Layout.fillWidth: true
            text: "Ready"
            color: root.tokens.accent
            font.family: root.tokens.fontFamily
            font.pixelSize: root.tokens.bodyFontEpx
            font.weight: Font.DemiBold
        }

        Text {
            Layout.fillWidth: true
            text: root.payload.ready_summary || root.payload.summary || "Review the first step, then begin when the ritual is ready."
            color: root.tokens.text
            font.family: root.tokens.fontFamily
            font.pixelSize: root.tokens.bodyFontEpx
            wrapMode: Text.WordWrap
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 92
            radius: root.tokens.controlRadiusEpx
            color: root.tokens.semanticPanel("running")
            border.color: root.tokens.border
            border.width: 1

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: root.tokens.spaceMd
                spacing: 4

                Text {
                    Layout.fillWidth: true
                    text: "First step"
                    color: root.tokens.running
                    font.family: root.tokens.fontFamily
                    font.pixelSize: root.tokens.captionFontEpx
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }

                Text {
                    Layout.fillWidth: true
                    text: root.titleFor(root.currentStep, "Ritual setup")
                    color: root.tokens.text
                    font.family: root.tokens.fontFamily
                    font.pixelSize: root.tokens.bodyFontEpx
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }

                Text {
                    Layout.fillWidth: true
                    text: root.detailFor(root.currentStep, "No extra preparation is required.")
                    color: root.tokens.textMuted
                    font.family: root.tokens.fontFamily
                    font.pixelSize: root.tokens.captionFontEpx
                    elide: Text.ElideRight
                }
            }
        }

        Text {
            Layout.fillWidth: true
            text: root.futureSteps.length > 0 ? root.futureSteps.length + " upcoming steps" : "No upcoming steps"
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
