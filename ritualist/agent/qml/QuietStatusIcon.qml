import QtQuick

Item {
    id: icon

    property var tokens: RitualistTokens {}
    property string status: "waiting"
    property bool reducedMotion: false

    implicitWidth: tokens.spaceLg
    implicitHeight: tokens.spaceLg
    Accessible.name: status
    Accessible.role: Accessible.Indicator

    Rectangle {
        id: dot

        width: 12
        height: 12
        radius: 6
        anchors.centerIn: parent
        color: icon.tokens.semanticColor(icon.status)
        border.color: icon.tokens.panel
        border.width: 2

        Behavior on color {
            ColorAnimation { duration: icon.tokens.duration("state", icon.reducedMotion) }
        }
    }
}
