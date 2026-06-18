import QtQuick
import QtQuick.Controls.Basic

Button {
    id: control

    property var themeRoot
    property string role: "neutral"
    property bool compact: false

    implicitHeight: compact ? 30 : 36
    leftPadding: themeRoot.spaceMd
    rightPadding: themeRoot.spaceMd
    topPadding: themeRoot.spaceSm
    bottomPadding: themeRoot.spaceSm
    font.family: themeRoot.token("font_family", "Segoe UI")
    font.pixelSize: themeRoot.token("font_size_body", 13)
    focusPolicy: Qt.StrongFocus
    Accessible.name: text
    Accessible.role: Accessible.Button

    contentItem: Text {
        text: control.text
        color: control.enabled ? control.themeRoot.token("foreground", "#f4f7fb") : control.themeRoot.token("muted", "#91a2b8")
        font: control.font
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    background: Rectangle {
        radius: control.themeRoot.radiusMd
        color: control.themeRoot.buttonBackground(control.role, control.enabled, control.hovered, control.down)
        border.color: control.themeRoot.buttonBorder(control.role, control.enabled, control.activeFocus)
        border.width: control.activeFocus ? 2 : 1
        opacity: control.enabled ? 1.0 : 0.56
    }
}
