import QtQuick

Rectangle {
    id: divider

    property var tokens: RitualistTokens {}
    property bool vertical: false

    implicitWidth: vertical ? 1 : tokens.primaryHitTargetEpx
    implicitHeight: vertical ? tokens.primaryHitTargetEpx : 1
    color: tokens.border
}
