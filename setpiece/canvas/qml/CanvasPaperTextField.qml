import QtQuick
import QtQuick.Controls.Basic

TextField {
    id: field

    property var themeRoot

    implicitHeight: 34
    color: themeRoot.token("foreground", "#f4f7fb")
    placeholderTextColor: themeRoot.token("muted", "#91a2b8")
    selectedTextColor: themeRoot.token("background", "#070c13")
    selectionColor: themeRoot.token("accent", "#3dd6a5")
    font.family: themeRoot.token("font_family", "Segoe UI")
    font.pixelSize: themeRoot.token("font_size_body", 13)
    Accessible.name: placeholderText || text || "Text field"
    Accessible.role: Accessible.EditableText
    leftPadding: themeRoot.spaceSm
    rightPadding: themeRoot.spaceSm

    background: Rectangle {
        radius: field.themeRoot.radiusSm
        color: field.themeRoot.token("panel_alt", "#101720")
        border.color: field.activeFocus ? field.themeRoot.token("focus_ring", "#7fb8ff") : field.themeRoot.token("border", "#203044")
        border.width: field.activeFocus ? 2 : 1
    }
}
