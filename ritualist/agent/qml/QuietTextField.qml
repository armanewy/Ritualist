import QtQuick
import QtQuick.Controls.Basic

TextField {
    id: field

    property var tokens: RitualistTokens {}
    property bool reducedMotion: false

    implicitHeight: tokens.primaryHitTargetEpx
    color: tokens.text
    placeholderTextColor: tokens.textMuted
    selectedTextColor: tokens.panel
    selectionColor: tokens.accent
    font.family: tokens.fontFamily
    font.pixelSize: Math.max(tokens.bodyFontEpx, tokens.minFontEpx)
    Accessible.name: placeholderText || text || "Text field"
    Accessible.role: Accessible.EditableText
    leftPadding: tokens.spaceMd
    rightPadding: tokens.spaceMd

    background: Rectangle {
        radius: field.tokens.controlRadiusEpx
        color: field.tokens.panel
        border.color: field.activeFocus ? field.tokens.focusRing : field.tokens.border
        border.width: field.activeFocus ? 2 : 1
        opacity: field.enabled ? 1.0 : field.tokens.disabledOpacity

        Behavior on border.color {
            ColorAnimation { duration: field.tokens.duration("state", field.reducedMotion) }
        }
        Behavior on opacity {
            NumberAnimation { duration: field.tokens.duration("fade", field.reducedMotion) }
        }
    }
}
