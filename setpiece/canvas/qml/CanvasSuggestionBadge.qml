import QtQuick

Rectangle {
    id: badge

    property var themeRoot
    property string text: ""

    height: 24
    width: Math.max(76, badgeText.implicitWidth + 16)
    radius: themeRoot.radiusSm
    color: themeRoot.token("panel_alt", "#101720")
    border.color: themeRoot.token("border", "#203044")
    border.width: 1

    Text {
        id: badgeText

        anchors.centerIn: parent
        text: badge.text
        color: badge.themeRoot.token("muted", "#91a2b8")
        font.pixelSize: 11
        font.weight: Font.DemiBold
        elide: Text.ElideRight
    }
}
