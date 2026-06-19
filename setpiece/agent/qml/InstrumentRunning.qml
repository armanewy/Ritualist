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

    function limitedFutureSteps() {
        return root.futureSteps.slice(0, 4)
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: root.tokens.spaceMd

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 112
            radius: root.tokens.controlRadiusEpx
            color: root.tokens.semanticPanel("running")
            border.color: root.tokens.running
            border.width: 1

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: root.tokens.spaceMd
                spacing: 5

                Text {
                    Layout.fillWidth: true
                    text: "Now running"
                    color: root.tokens.running
                    font.family: root.tokens.fontFamily
                    font.pixelSize: root.tokens.captionFontEpx
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }

                Text {
                    Layout.fillWidth: true
                    text: root.titleFor(root.currentStep, "Current step")
                    color: root.tokens.text
                    font.family: root.tokens.fontFamily
                    font.pixelSize: root.tokens.titleFontEpx
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }

                Text {
                    Layout.fillWidth: true
                    text: root.detailFor(root.currentStep, "Ritual is making progress.")
                    color: root.tokens.textMuted
                    font.family: root.tokens.fontFamily
                    font.pixelSize: root.tokens.captionFontEpx
                    elide: Text.ElideRight
                }
            }
        }

        Text {
            Layout.fillWidth: true
            text: root.completedSteps.length > 0 ? "Completed" : ""
            visible: root.completedSteps.length > 0
            color: root.tokens.textMuted
            font.family: root.tokens.fontFamily
            font.pixelSize: root.tokens.captionFontEpx
            font.weight: Font.DemiBold
        }

        Repeater {
            model: root.completedSteps

            delegate: RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 22
                spacing: root.tokens.spaceSm
                opacity: 0.72

                Rectangle {
                    Layout.preferredWidth: 6
                    Layout.preferredHeight: 6
                    radius: 3
                    color: root.tokens.running
                }

                Text {
                    Layout.fillWidth: true
                    text: root.titleFor(modelData, "Completed step")
                    color: root.tokens.textMuted
                    font.family: root.tokens.fontFamily
                    font.pixelSize: root.tokens.captionFontEpx
                    elide: Text.ElideRight
                }
            }
        }

        Text {
            Layout.fillWidth: true
            text: root.futureSteps.length > 0 ? "Upcoming" : ""
            visible: root.futureSteps.length > 0
            color: root.tokens.textMuted
            font.family: root.tokens.fontFamily
            font.pixelSize: root.tokens.captionFontEpx
            font.weight: Font.DemiBold
        }

        Repeater {
            model: root.limitedFutureSteps()

            delegate: RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 22
                spacing: root.tokens.spaceSm
                opacity: 0.62

                Rectangle {
                    Layout.preferredWidth: 6
                    Layout.preferredHeight: 6
                    radius: 3
                    color: root.tokens.borderStrong
                }

                Text {
                    Layout.fillWidth: true
                    text: root.titleFor(modelData, "Upcoming step")
                    color: root.tokens.textMuted
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
