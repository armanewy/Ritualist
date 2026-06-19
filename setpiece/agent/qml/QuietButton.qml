import QtQuick
import QtQuick.Controls.Basic

Button {
    id: control

    property var tokens: SetpieceTokens {}
    property string role: "neutral"
    property bool reducedMotion: false

    implicitHeight: tokens.primaryHitTargetEpx
    leftPadding: tokens.spaceMd
    rightPadding: tokens.spaceMd
    topPadding: tokens.spaceSm
    bottomPadding: tokens.spaceSm
    font.family: tokens.fontFamily
    font.pixelSize: Math.max(tokens.bodyFontEpx, tokens.minFontEpx)
    focusPolicy: Qt.StrongFocus
    Accessible.name: text
    Accessible.role: Accessible.Button

    contentItem: Text {
        text: control.text
        color: control.tokens.buttonText(control.role, control.enabled)
        font: control.font
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight

        Behavior on color {
            ColorAnimation { duration: control.tokens.duration("state", control.reducedMotion) }
        }
    }

    background: Rectangle {
        radius: control.tokens.controlRadiusEpx
        color: control.tokens.buttonBackground(
            control.role,
            control.enabled,
            control.hovered,
            control.down
        )
        border.color: control.tokens.buttonBorder(control.role, control.enabled, control.activeFocus)
        border.width: control.activeFocus ? 2 : 1
        opacity: control.enabled ? 1.0 : control.tokens.disabledOpacity

        Behavior on color {
            ColorAnimation { duration: control.tokens.duration("state", control.reducedMotion) }
        }
        Behavior on border.color {
            ColorAnimation { duration: control.tokens.duration("state", control.reducedMotion) }
        }
        Behavior on opacity {
            NumberAnimation { duration: control.tokens.duration("fade", control.reducedMotion) }
        }
    }
}
