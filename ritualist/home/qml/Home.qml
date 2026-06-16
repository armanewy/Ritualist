import QtQuick
import QtQuick.Layouts
import QtQuick.Window

Window {
    id: root

    width: 1280
    height: 720
    visible: true
    visibility: Window.FullScreen
    flags: Qt.Window | Qt.FramelessWindowHint
    color: "#090b10"
    title: "Ritualist Home"

    property bool mockMode: ritualistMockMode
    property var homeController: typeof ritualistHomeController === "undefined" ? null : ritualistHomeController
    property var homePayload: homeController ? homeController.payload : (typeof ritualistHomePayload === "undefined" ? ({ "categories": [], "cards": [] }) : ritualistHomePayload)
    property int selectedCategory: 0
    property int selectedCard: 0
    property bool railActive: false
    property string footerText: "Home ready"
    property int devTick: 0

    function allCards() {
        if (!homePayload || !homePayload.cards) {
            return []
        }
        return homePayload.cards
    }

    function allCategories() {
        if (!homePayload || !homePayload.categories) {
            return []
        }
        return homePayload.categories
    }

    function clamp(value, minimum, maximum) {
        return Math.max(minimum, Math.min(maximum, value))
    }

    function currentCategoryName() {
        if (categoryModel.count === 0) {
            return "Home"
        }
        return categoryModel.get(selectedCategory).name
    }

    function categoryCount(categoryName) {
        var count = 0
        var cards = allCards()
        for (var i = 0; i < cards.length; i += 1) {
            if (cards[i].category === categoryName) {
                count += 1
            }
        }
        return count
    }

    function loadCategories() {
        categoryModel.clear()
        var categories = allCategories()
        for (var i = 0; i < categories.length; i += 1) {
            var name = categories[i].label
            categoryModel.append({ "name": name, "count": String(categoryCount(name)) })
        }
        selectedCategory = categoryModel.count === 0 ? 0 : clamp(selectedCategory, 0, categoryModel.count - 1)
    }

    function setSelectedCard(index) {
        if (cardModel.count === 0) {
            selectedCard = 0
            return
        }
        selectedCard = clamp(index, 0, cardModel.count - 1)
        grid.positionViewAtIndex(selectedCard, GridView.Contain)
    }

    function setSelectedCategory(index) {
        if (categoryModel.count === 0) {
            return
        }
        selectedCategory = clamp(index, 0, categoryModel.count - 1)
        railActive = true
    }

    function activateSelection() {
        if (railActive) {
            footerText = currentCategoryName() + " selected"
            return
        }
        if (cardModel.count === 0) {
            return
        }
        var card = cardModel.get(selectedCard)
        footerText = card.title + " opened"
    }

    function refreshHomePayload() {
        var previousCardId = ""
        if (cardModel.count > 0 && selectedCard >= 0 && selectedCard < cardModel.count) {
            previousCardId = cardModel.get(selectedCard).id
        }
        if (homeController) {
            homePayload = homeController.payload
        }
        loadCategories()
        loadCards(previousCardId)
    }

    function metricText() {
        if (!homeController) {
            return "mock updates 0 | tick " + devTick
        }
        return "mock updates " + homeController.updatesApplied + " | tick " + devTick
    }

    function statusColor(status) {
        if (status === "running") {
            return "#58d2a3"
        }
        if (status === "success") {
            return "#6de2b2"
        }
        if (status === "warning") {
            return "#f5c96b"
        }
        if (status === "failed") {
            return "#d96d7e"
        }
        if (status === "disabled") {
            return "#7f8da1"
        }
        return "#bec8d9"
    }

    function statusLabel(status) {
        if (!status) {
            return "ready"
        }
        return status.charAt(0).toUpperCase() + status.slice(1)
    }

    function loadCards(preferredCardId) {
        cardModel.clear()
        var categoryName = currentCategoryName()
        var cards = allCards()
        var preferredIndex = 0
        for (var i = 0; i < cards.length; i += 1) {
            if (cards[i].category === categoryName) {
                cardModel.append(cards[i])
                if (preferredCardId && cards[i].id === preferredCardId) {
                    preferredIndex = cardModel.count - 1
                }
            }
        }
        setSelectedCard(preferredIndex)
        footerText = categoryName + " ready"
    }

    onSelectedCategoryChanged: {
        if (categoryModel.count > 0) {
            loadCards()
        }
    }

    ListModel {
        id: categoryModel
    }

    ListModel {
        id: cardModel
    }

    Connections {
        target: root.homeController
        ignoreUnknownSignals: true

        function onPayloadChanged() {
            root.refreshHomePayload()
        }

        function onMetricsChanged() {
            if (root.homeController) {
                root.footerText = root.homeController.lastEventLabel
            }
        }
    }

    Timer {
        interval: 1000
        repeat: true
        running: root.mockMode
        onTriggered: root.devTick += 1
    }

    Rectangle {
        anchors.fill: parent
        color: "#090b10"

        gradient: Gradient {
            GradientStop { position: 0.0; color: "#151823" }
            GradientStop { position: 0.5; color: "#0c1118" }
            GradientStop { position: 1.0; color: "#090b10" }
        }
    }

    Item {
        id: surface

        anchors.fill: parent
        focus: true

        Component.onCompleted: {
            root.loadCategories()
            root.loadCards()
            forceActiveFocus()
        }

        Keys.onPressed: function(event) {
            if (event.key === Qt.Key_Escape) {
                root.close()
                event.accepted = true
            } else if (event.key === Qt.Key_Left) {
                if (!root.railActive && root.selectedCard % grid.columns === 0) {
                    root.railActive = true
                } else if (!root.railActive) {
                    root.setSelectedCard(root.selectedCard - 1)
                }
                event.accepted = true
            } else if (event.key === Qt.Key_Right) {
                if (root.railActive) {
                    root.railActive = false
                } else {
                    root.setSelectedCard(root.selectedCard + 1)
                }
                event.accepted = true
            } else if (event.key === Qt.Key_Up) {
                if (root.railActive) {
                    root.setSelectedCategory(root.selectedCategory - 1)
                } else {
                    root.setSelectedCard(root.selectedCard - grid.columns)
                }
                event.accepted = true
            } else if (event.key === Qt.Key_Down) {
                if (root.railActive) {
                    root.setSelectedCategory(root.selectedCategory + 1)
                } else {
                    root.setSelectedCard(root.selectedCard + grid.columns)
                }
                event.accepted = true
            } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
                root.activateSelection()
                event.accepted = true
            }
        }

        RowLayout {
            anchors.fill: parent
            anchors.margins: 28
            spacing: 28

            Rectangle {
                id: rail

                Layout.fillHeight: true
                Layout.preferredWidth: 230
                radius: 8
                color: "#10151e"
                border.color: root.railActive ? "#6de2b2" : "#273241"
                border.width: 1

                Column {
                    anchors.fill: parent
                    anchors.margins: 18
                    spacing: 14

                    Text {
                        text: "Home"
                        color: "#f2f5f8"
                        font.pixelSize: 30
                        font.weight: Font.DemiBold
                    }

                    Text {
                        text: "Local rituals"
                        color: "#8f9aad"
                        font.pixelSize: 14
                    }

                    Repeater {
                        model: categoryModel

                        delegate: Rectangle {
                            id: categoryItem

                            width: parent.width
                            height: 54
                            radius: 8
                            scale: hovered || focused ? 1.025 : 1.0
                            color: selected ? "#1d3340" : (hovered ? "#18212c" : "transparent")
                            border.width: focused ? 2 : 1
                            border.color: focused ? "#6de2b2" : (selected ? "#3c5364" : "transparent")

                            property bool selected: root.selectedCategory === index
                            property bool focused: root.railActive && selected
                            property bool hovered: pointer.containsMouse

                            Behavior on scale {
                                NumberAnimation { duration: 120; easing.type: Easing.OutCubic }
                            }
                            Behavior on color {
                                ColorAnimation { duration: 120 }
                            }

                            MouseArea {
                                id: pointer

                                anchors.fill: parent
                                hoverEnabled: true
                                onClicked: {
                                    root.setSelectedCategory(index)
                                    root.footerText = name + " selected"
                                }
                            }

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 14
                                anchors.rightMargin: 12
                                spacing: 10

                                Rectangle {
                                    Layout.preferredWidth: 8
                                    Layout.preferredHeight: 8
                                    radius: 4
                                    color: categoryItem.selected ? "#6de2b2" : "#596779"
                                }

                                Text {
                                    Layout.fillWidth: true
                                    text: name
                                    color: categoryItem.selected ? "#f5fbff" : "#a7b1c2"
                                    elide: Text.ElideRight
                                    font.pixelSize: 15
                                    font.weight: categoryItem.selected ? Font.DemiBold : Font.Normal
                                }

                                Text {
                                    text: count
                                    color: "#7f8da1"
                                    font.pixelSize: 13
                                    horizontalAlignment: Text.AlignRight
                                }
                            }
                        }
                    }
                }
            }

            Item {
                Layout.fillWidth: true
                Layout.fillHeight: true

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 18

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 58
                        spacing: 14

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 4

                            Text {
                                text: root.currentCategoryName()
                                color: "#f2f5f8"
                                font.pixelSize: 28
                                font.weight: Font.DemiBold
                            }

                            Text {
                                text: root.footerText
                                color: "#8f9aad"
                                font.pixelSize: 14
                                elide: Text.ElideRight
                            }
                        }

                        Rectangle {
                            Layout.preferredWidth: 148
                            Layout.preferredHeight: 40
                            radius: 8
                            color: "#121b26"
                            border.color: "#263648"

                            Text {
                                anchors.centerIn: parent
                                text: cardModel.count + " cards"
                                color: "#b8c4d6"
                                font.pixelSize: 14
                                font.weight: Font.DemiBold
                            }
                        }
                    }

                    GridView {
                        id: grid

                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        model: cardModel
                        boundsBehavior: Flickable.StopAtBounds
                        currentIndex: root.selectedCard
                        cellWidth: Math.floor(width / columns)
                        cellHeight: 218

                        property int columns: width >= 1260 ? 4 : (width >= 900 ? 3 : 2)

                        delegate: Item {
                            id: cardSlot

                            width: grid.cellWidth
                            height: grid.cellHeight

                            Rectangle {
                                id: card

                                anchors.fill: parent
                                anchors.margins: 10
                                radius: 8
                                scale: hovered || focused ? 1.04 : 1.0
                                opacity: hovered || focused ? 1.0 : 0.88
                                color: "#141a23"
                                border.width: focused ? 2 : 1
                                border.color: focused ? "#6de2b2" : (hovered ? "#58718d" : "#263241")

                                property bool focused: !root.railActive && root.selectedCard === index
                                property bool hovered: cardPointer.containsMouse

                                Behavior on scale {
                                    NumberAnimation { duration: 130; easing.type: Easing.OutCubic }
                                }
                                Behavior on opacity {
                                    NumberAnimation { duration: 130; easing.type: Easing.OutCubic }
                                }

                                MouseArea {
                                    id: cardPointer

                                    anchors.fill: parent
                                    hoverEnabled: true
                                    onClicked: {
                                        root.railActive = false
                                        root.setSelectedCard(index)
                                        root.footerText = title + " opened"
                                    }
                                }

                                Rectangle {
                                    id: art

                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.top: parent.top
                                    height: 94
                                    radius: 8
                                    color: accent

                                    gradient: Gradient {
                                        GradientStop { position: 0.0; color: accent }
                                        GradientStop { position: 1.0; color: "#1a2230" }
                                    }

                                    Rectangle {
                                        anchors.right: parent.right
                                        anchors.top: parent.top
                                        anchors.margins: 12
                                        width: 92
                                        height: 26
                                        radius: 8
                                        color: "#141a23"
                                        opacity: 0.78

                                        Text {
                                            anchors.centerIn: parent
                                            width: parent.width - 14
                                            text: last_run_status
                                            color: "#eef4fb"
                                            font.pixelSize: 12
                                            font.weight: Font.DemiBold
                                            horizontalAlignment: Text.AlignHCenter
                                            elide: Text.ElideRight
                                        }
                                    }
                                }

                                ColumnLayout {
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.top: art.bottom
                                    anchors.bottom: parent.bottom
                                    anchors.margins: 16
                                    anchors.topMargin: 14
                                    spacing: 8

                                    Text {
                                        Layout.fillWidth: true
                                        text: title
                                        color: "#f4f7fa"
                                        font.pixelSize: 18
                                        font.weight: Font.DemiBold
                                        elide: Text.ElideRight
                                    }

                                    Text {
                                        Layout.fillWidth: true
                                        text: subtitle
                                        color: "#9ca8b8"
                                        font.pixelSize: 13
                                        elide: Text.ElideRight
                                    }

                                    Item {
                                        Layout.fillHeight: true
                                    }

                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 8

                                        Rectangle {
                                            Layout.preferredWidth: 10
                                            Layout.preferredHeight: 10
                                            radius: 5
                                            color: root.statusColor(status)
                                        }

                                        Text {
                                            Layout.fillWidth: true
                                            text: root.statusLabel(status)
                                            color: "#c8d2df"
                                            font.pixelSize: 13
                                            font.weight: Font.DemiBold
                                            elide: Text.ElideRight
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    Rectangle {
        id: devOverlay

        visible: root.mockMode
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.margins: 18
        width: 292
        height: 72
        radius: 8
        color: "#10151e"
        opacity: 0.92
        border.color: "#2d3f51"
        border.width: 1

        Column {
            anchors.fill: parent
            anchors.margins: 12
            spacing: 4

            Text {
                width: parent.width
                text: "Home mock"
                color: "#f2f5f8"
                font.pixelSize: 13
                font.weight: Font.DemiBold
                elide: Text.ElideRight
            }

            Text {
                width: parent.width
                text: root.metricText()
                color: "#a7b3c5"
                font.pixelSize: 12
                elide: Text.ElideRight
            }

            Text {
                width: parent.width
                text: root.homeController ? root.homeController.lastEventLabel : "No mock events yet"
                color: "#7f8da1"
                font.pixelSize: 11
                elide: Text.ElideRight
            }
        }
    }
}
