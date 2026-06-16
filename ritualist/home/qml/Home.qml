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
    property int waitTick: 0
    property bool actionBusy: homeController ? homeController.actionBusy : false
    property bool runtimeActive: homeController ? homeController.runtimeActive : false
    property bool runtimePaused: homeController ? homeController.runtimePaused : false
    property bool confirmationPending: homeController ? homeController.confirmationPending : false
    property string confirmationPrompt: homeController ? homeController.confirmationPrompt : ""
    property bool detailOpen: false
    property var detailCard: ({})

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
        openCardDetails(card)
    }

    function openCardDetails(card) {
        detailCard = card
        detailOpen = true
        footerText = card.title + " details"
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

    function durationText(rawSeconds) {
        var seconds = Math.max(0, Math.floor(Number(rawSeconds || 0)))
        if (seconds < 60) {
            return seconds + "s"
        }
        var minutes = Math.floor(seconds / 60)
        var remainder = seconds % 60
        if (minutes < 60) {
            return minutes + "m " + remainder + "s"
        }
        var hours = Math.floor(minutes / 60)
        return hours + "h " + (minutes % 60) + "m"
    }

    function elapsedWaitText(startedAt, baselineSeconds) {
        var tick = waitTick
        var baseline = Number(baselineSeconds || 0)
        var parsed = Date.parse(startedAt || "")
        if (!isNaN(parsed)) {
            return durationText(Math.max(baseline, (Date.now() - parsed) / 1000))
        }
        return durationText(baseline)
    }

    function waitSummary(target, startedAt, elapsedSeconds, timeoutSeconds) {
        var parts = []
        if (target) {
            parts.push("Target: " + target)
        }
        parts.push("Elapsed: " + elapsedWaitText(startedAt, elapsedSeconds))
        if (timeoutSeconds) {
            parts.push("Timeout: " + durationText(timeoutSeconds))
        }
        return parts.join(" | ")
    }

    function hasActiveWait() {
        var cards = allCards()
        for (var i = 0; i < cards.length; i += 1) {
            if (cards[i].wait_action) {
                return true
            }
        }
        return false
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

    function actionEnabled(cardStatus) {
        return homeController && !mockMode && !actionBusy && cardStatus !== "disabled"
    }

    function invokeCardAction(action, cardId) {
        if (!homeController || !cardId || mockMode || actionBusy) {
            return
        }
        if (action === "run") {
            homeController.runCard(cardId)
        } else if (action === "dry_run") {
            homeController.dryRunCard(cardId)
        } else if (action === "doctor") {
            homeController.doctorCard(cardId)
        } else if (action === "edit_recipe") {
            homeController.editRecipe(cardId)
        } else if (action === "open_logs") {
            homeController.openLogs(cardId)
        }
    }

    function selectedCardId() {
        if (cardModel.count === 0 || selectedCard < 0 || selectedCard >= cardModel.count) {
            return ""
        }
        return cardModel.get(selectedCard).id || ""
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

        function onActionStateChanged() {
            if (root.homeController && root.homeController.actionBusy) {
                root.footerText = "Action running"
            }
        }

        function onConfirmationChanged() {
            if (root.homeController && root.homeController.confirmationPending) {
                root.footerText = "Confirmation required"
            }
        }
    }

    Timer {
        interval: 1000
        repeat: true
        running: root.mockMode
        onTriggered: root.devTick += 1
    }

    Timer {
        interval: 1000
        repeat: true
        running: root.hasActiveWait()
        onTriggered: root.waitTick += 1
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
            if (root.confirmationPending) {
                if (event.key === Qt.Key_Escape) {
                    root.homeController.answerConfirmation(false)
                } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                    root.homeController.answerConfirmation(true)
                }
                event.accepted = true
            } else if (event.key === Qt.Key_Escape) {
                if (root.detailOpen) {
                    root.detailOpen = false
                } else {
                    root.close()
                }
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

                        Rectangle {
                            id: closeBrowserControl

                            Layout.preferredWidth: 132
                            Layout.preferredHeight: 40
                            radius: 8
                            color: closeBrowserControl.closeEnabled ? (closeBrowserPointer.containsMouse ? "#263648" : "#1c2734") : "#151b24"
                            border.color: closeBrowserControl.closeEnabled ? "#40546a" : "#263648"
                            opacity: closeBrowserControl.closeEnabled ? 1.0 : 0.52

                            property bool closeEnabled: homeController && !mockMode && !actionBusy

                            MouseArea {
                                id: closeBrowserPointer

                                anchors.fill: parent
                                hoverEnabled: true
                                enabled: closeBrowserControl.closeEnabled
                                onClicked: root.homeController.closeKeepOpenBrowser(root.selectedCardId())
                            }

                            Text {
                                anchors.centerIn: parent
                                width: parent.width - 12
                                text: "Close Browser"
                                color: closeBrowserControl.closeEnabled ? "#d8e2ee" : "#7f8da1"
                                font.pixelSize: 13
                                font.weight: Font.DemiBold
                                horizontalAlignment: Text.AlignHCenter
                                elide: Text.ElideRight
                            }
                        }

                        Rectangle {
                            id: pauseControl

                            Layout.preferredWidth: 104
                            Layout.preferredHeight: 40
                            radius: 8
                            color: pauseControl.pauseEnabled ? (pausePointer.containsMouse ? "#263648" : "#1c2734") : "#151b24"
                            border.color: pauseControl.pauseEnabled ? "#40546a" : "#263648"
                            opacity: pauseControl.pauseEnabled ? 1.0 : 0.52

                            MouseArea {
                                id: pausePointer

                                anchors.fill: parent
                                hoverEnabled: true
                                enabled: pauseControl.pauseEnabled
                                onClicked: root.homeController.pauseCurrentRun()
                            }

                            property bool pauseEnabled: root.runtimeActive && !root.runtimePaused && root.homeController

                            Text {
                                anchors.centerIn: parent
                                width: parent.width - 12
                                text: "Pause"
                                color: pauseControl.pauseEnabled ? "#d8e2ee" : "#7f8da1"
                                font.pixelSize: 13
                                font.weight: Font.DemiBold
                                horizontalAlignment: Text.AlignHCenter
                                elide: Text.ElideRight
                            }
                        }

                        Rectangle {
                            id: resumeControl

                            Layout.preferredWidth: 104
                            Layout.preferredHeight: 40
                            radius: 8
                            color: resumeControl.resumeEnabled ? (resumePointer.containsMouse ? "#263648" : "#1c2734") : "#151b24"
                            border.color: resumeControl.resumeEnabled ? "#40546a" : "#263648"
                            opacity: resumeControl.resumeEnabled ? 1.0 : 0.52

                            MouseArea {
                                id: resumePointer

                                anchors.fill: parent
                                hoverEnabled: true
                                enabled: resumeControl.resumeEnabled
                                onClicked: root.homeController.resumeCurrentRun()
                            }

                            property bool resumeEnabled: root.runtimeActive && root.runtimePaused && root.homeController

                            Text {
                                anchors.centerIn: parent
                                width: parent.width - 12
                                text: "Resume"
                                color: resumeControl.resumeEnabled ? "#d8e2ee" : "#7f8da1"
                                font.pixelSize: 13
                                font.weight: Font.DemiBold
                                horizontalAlignment: Text.AlignHCenter
                                elide: Text.ElideRight
                            }
                        }

                        Rectangle {
                            Layout.preferredWidth: 104
                            Layout.preferredHeight: 40
                            radius: 8
                            color: root.runtimeActive ? (stopPointer.containsMouse ? "#4a2a34" : "#351f27") : "#151b24"
                            border.color: root.runtimeActive ? "#d96d7e" : "#263648"
                            opacity: root.runtimeActive ? 1.0 : 0.52

                            MouseArea {
                                id: stopPointer

                                anchors.fill: parent
                                hoverEnabled: true
                                enabled: root.runtimeActive && root.homeController
                                onClicked: root.homeController.stopCurrentRun()
                            }

                            Text {
                                anchors.centerIn: parent
                                width: parent.width - 12
                                text: "Stop"
                                color: root.runtimeActive ? "#ffeef1" : "#7f8da1"
                                font.pixelSize: 13
                                font.weight: Font.DemiBold
                                horizontalAlignment: Text.AlignHCenter
                                elide: Text.ElideRight
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
                        cellHeight: 382

                        property int columns: width >= 1260 ? 4 : (width >= 900 ? 3 : 2)

                        delegate: Item {
                            id: cardSlot

                            width: grid.cellWidth
                            height: grid.cellHeight

                            property int cardIndex: index
                            property string cardId: model.id || ""
                            property string cardStatus: model.status || status
                            property bool waitActive: (model.wait_action || "") !== ""
                            property bool keepOpenActive: (model.keep_open_active || "") === "true"

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
                                        root.setSelectedCard(cardSlot.cardIndex)
                                        root.openCardDetails(cardModel.get(cardSlot.cardIndex))
                                    }
                                }

                                Rectangle {
                                    id: art

                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.top: parent.top
                                    height: 94
                                    radius: 8
                                    clip: true
                                    color: accent

                                    gradient: Gradient {
                                        GradientStop { position: 0.0; color: accent }
                                        GradientStop { position: 1.0; color: "#1a2230" }
                                    }

                                    Image {
                                        anchors.fill: parent
                                        source: image || ""
                                        visible: source !== ""
                                        fillMode: Image.PreserveAspectCrop
                                        asynchronous: true
                                        cache: true
                                        smooth: true
                                        sourceSize.width: 512
                                        sourceSize.height: 288
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

                                    Rectangle {
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: cardSlot.waitActive ? 48 : 0
                                        visible: cardSlot.waitActive
                                        radius: 6
                                        color: "#1b2530"
                                        border.color: "#f5c96b"
                                        border.width: 1

                                        Column {
                                            anchors.fill: parent
                                            anchors.margins: 8
                                            spacing: 3

                                            Text {
                                                width: parent.width
                                                text: "Waiting: " + (model.wait_action || "")
                                                color: "#f6d37a"
                                                font.pixelSize: 12
                                                font.weight: Font.DemiBold
                                                elide: Text.ElideRight
                                            }

                                            Text {
                                                width: parent.width
                                                text: root.waitSummary(model.wait_target || "", model.wait_started_at || "", model.wait_elapsed_seconds || "", model.wait_timeout_seconds || "")
                                                color: "#d7e0eb"
                                                font.pixelSize: 11
                                                elide: Text.ElideRight
                                            }
                                        }
                                    }

                                    Rectangle {
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: cardSlot.keepOpenActive ? 24 : 0
                                        visible: cardSlot.keepOpenActive
                                        radius: 6
                                        color: "#18281f"
                                        border.color: "#65d59b"
                                        border.width: 1

                                        Text {
                                            anchors.centerIn: parent
                                            width: parent.width - 12
                                            text: "Keep-open active"
                                            color: "#bbf5d1"
                                            font.pixelSize: 11
                                            font.weight: Font.DemiBold
                                            horizontalAlignment: Text.AlignHCenter
                                            elide: Text.ElideRight
                                        }
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

                                    GridLayout {
                                        Layout.fillWidth: true
                                        columns: 3
                                        rowSpacing: 6
                                        columnSpacing: 6

                                        property var actionItems: [
                                            { "label": "Run", "action": "run" },
                                            { "label": "Dry Run", "action": "dry_run" },
                                            { "label": "Doctor", "action": "doctor" },
                                            { "label": "Edit", "action": "edit_recipe" },
                                            { "label": "Logs", "action": "open_logs" }
                                        ]

                                        Repeater {
                                            model: parent.actionItems

                                            delegate: Rectangle {
                                                Layout.fillWidth: true
                                                Layout.preferredHeight: 28
                                                radius: 6
                                                color: enabledAction ? (buttonPointer.containsMouse ? "#263648" : "#1c2734") : "#151b24"
                                                border.width: 1
                                                border.color: enabledAction ? "#40546a" : "#24303d"
                                                opacity: enabledAction ? 1.0 : 0.5

                                                property bool enabledAction: root.actionEnabled(cardSlot.cardStatus)

                                                MouseArea {
                                                    id: buttonPointer

                                                    anchors.fill: parent
                                                    hoverEnabled: true
                                                    enabled: parent.enabledAction
                                                    onClicked: {
                                                        root.railActive = false
                                                        root.setSelectedCard(cardSlot.cardIndex)
                                                        root.invokeCardAction(modelData.action, cardSlot.cardId)
                                                    }
                                                }

                                                Text {
                                                    anchors.centerIn: parent
                                                    width: parent.width - 8
                                                    text: modelData.label
                                                    color: "#d8e2ee"
                                                    font.pixelSize: 11
                                                    font.weight: Font.DemiBold
                                                    horizontalAlignment: Text.AlignHCenter
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
        }
    }

    Rectangle {
        id: confirmationPanel

        visible: root.confirmationPending
        z: 100
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 28
        width: Math.min(parent.width - 56, 720)
        height: 176
        radius: 8
        color: "#10151e"
        border.color: "#f5c96b"
        border.width: 1
        opacity: 0.96

        RowLayout {
            anchors.fill: parent
            anchors.margins: 16
            spacing: 14

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 6

                Text {
                    Layout.fillWidth: true
                    text: "Confirmation required"
                    color: "#f6d37a"
                    font.pixelSize: 14
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }

                Text {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    text: root.confirmationPrompt
                    color: "#d7e0eb"
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                    maximumLineCount: 7
                    elide: Text.ElideRight
                }
            }

            Rectangle {
                Layout.preferredWidth: 112
                Layout.preferredHeight: 42
                radius: 6
                color: confirmPointer.containsMouse ? "#305842" : "#244735"
                border.color: "#65d59b"

                MouseArea {
                    id: confirmPointer

                    anchors.fill: parent
                    hoverEnabled: true
                    onClicked: root.homeController.answerConfirmation(true)
                }

                Text {
                    anchors.centerIn: parent
                    text: "Confirm"
                    color: "#ecfff5"
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                }
            }

            Rectangle {
                Layout.preferredWidth: 96
                Layout.preferredHeight: 42
                radius: 6
                color: cancelPointer.containsMouse ? "#4a2a34" : "#351f27"
                border.color: "#d96d7e"

                MouseArea {
                    id: cancelPointer

                    anchors.fill: parent
                    hoverEnabled: true
                    onClicked: root.homeController.answerConfirmation(false)
                }

                Text {
                    anchors.centerIn: parent
                    text: "Cancel"
                    color: "#ffeef1"
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                }
            }
        }
    }

    Rectangle {
        id: detailPanel

        visible: root.detailOpen && !root.confirmationPending
        z: 80
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 28
        width: Math.min(parent.width - 56, 760)
        height: 168
        radius: 8
        color: "#10151e"
        border.color: "#35506a"
        border.width: 1
        opacity: 0.96

        RowLayout {
            anchors.fill: parent
            anchors.margins: 16
            spacing: 16

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 6

                Text {
                    Layout.fillWidth: true
                    text: root.detailCard.title || "Recipe"
                    color: "#f2f5f8"
                    font.pixelSize: 16
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }

                Text {
                    Layout.fillWidth: true
                    text: root.detailCard.subtitle || ""
                    color: "#aebbd0"
                    font.pixelSize: 12
                    elide: Text.ElideRight
                }

                Text {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    text: root.detailCard.description || ""
                    color: "#d7e0eb"
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                    maximumLineCount: 5
                    elide: Text.ElideRight
                }
            }

            Rectangle {
                Layout.preferredWidth: 88
                Layout.preferredHeight: 38
                radius: 6
                color: closeDetailPointer.containsMouse ? "#253244" : "#1b2532"
                border.color: "#50667e"

                MouseArea {
                    id: closeDetailPointer

                    anchors.fill: parent
                    hoverEnabled: true
                    onClicked: root.detailOpen = false
                }

                Text {
                    anchors.centerIn: parent
                    text: "Close"
                    color: "#e6edf7"
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                }
            }
        }
    }

    Rectangle {
        id: confirmationModalBlocker

        visible: root.confirmationPending
        anchors.fill: parent
        z: 90
        color: "#000000"
        opacity: 0.22

        MouseArea {
            anchors.fill: parent
            hoverEnabled: true
            acceptedButtons: Qt.AllButtons
            onClicked: {
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
