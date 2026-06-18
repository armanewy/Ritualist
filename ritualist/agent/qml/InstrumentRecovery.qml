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

    function recoverySteps() {
        return root.payload.recovery_steps || root.futureSteps
    }

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
            color: root.tokens.semanticPanel("recovery")
            border.color: root.tokens.recovery
            border.width: 1

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: root.tokens.spaceMd
                spacing: 5

                Text {
                    Layout.fillWidth: true
                    text: "Recovery"
                    color: root.tokens.recovery
                    font.family: root.tokens.fontFamily
                    font.pixelSize: root.tokens.bodyFontEpx
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }

                Text {
                    Layout.fillWidth: true
                    text: root.titleFor(root.currentStep, root.payload.recovery_title || "Choose the recovery path")
                    color: root.tokens.text
                    font.family: root.tokens.fontFamily
                    font.pixelSize: root.tokens.titleFontEpx
                    font.weight: Font.DemiBold
                    wrapMode: Text.WordWrap
                }

                Text {
                    Layout.fillWidth: true
                    text: root.detailFor(root.currentStep, root.payload.recovery_summary || "The ritual can resume after the selected recovery step.")
                    color: root.tokens.textMuted
                    font.family: root.tokens.fontFamily
                    font.pixelSize: root.tokens.captionFontEpx
                    wrapMode: Text.WordWrap
                }
            }
        }

        Repeater {
            model: root.recoverySteps()

            delegate: RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 28
                spacing: root.tokens.spaceSm

                Rectangle {
                    Layout.preferredWidth: 6
                    Layout.preferredHeight: 6
                    radius: 3
                    color: root.tokens.recovery
                }

                Text {
                    Layout.fillWidth: true
                    text: root.titleFor(modelData, "Recovery step")
                    color: root.tokens.text
                    font.family: root.tokens.fontFamily
                    font.pixelSize: root.tokens.captionFontEpx
                    elide: Text.ElideRight
                }
            }
        }

        Item {
            Layout.fillHeight: true
        }
    }
}
