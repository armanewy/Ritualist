import QtQuick
import QtQuick.Controls.Basic

ComboBox {
    id: combo

    property var themeRoot

    implicitHeight: 34
    font.family: themeRoot.token("font_family", "Segoe UI")
    font.pixelSize: themeRoot.token("font_size_body", 13)
    Accessible.name: currentText || "Option selector"
    Accessible.role: Accessible.ComboBox

    contentItem: Text {
        text: combo.displayText
        color: combo.enabled ? combo.themeRoot.token("foreground", "#f4f7fb") : combo.themeRoot.token("muted", "#91a2b8")
        font: combo.font
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
        leftPadding: combo.themeRoot.spaceSm
        rightPadding: combo.themeRoot.spaceLg
    }

    background: Rectangle {
        radius: combo.themeRoot.radiusSm
        color: combo.themeRoot.token("panel_alt", "#101720")
        border.color: combo.activeFocus ? combo.themeRoot.token("focus_ring", "#7fb8ff") : combo.themeRoot.token("border", "#203044")
        border.width: combo.activeFocus ? 2 : 1
    }
}
