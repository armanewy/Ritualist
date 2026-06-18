from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from .menu_model import MenuAction, MenuItem, TrayMenuContext, build_tray_menu
from .tray_model import TrayContext, TrayState, build_tray_model


TrayActionHandler = Callable[[MenuAction], None]


@dataclass
class AgentTray:
    """Small Qt tray wrapper for the resident Agent skeleton."""

    app: Any
    system_tray_icon: Any
    menu: Any
    actions: Mapping[MenuAction, Any]
    on_action: TrayActionHandler
    show_count: int = 0
    received_taskbar_created: bool = False

    def show(self) -> None:
        self.system_tray_icon.show()
        self.show_count += 1

    def hide(self) -> None:
        self.system_tray_icon.hide()

    def set_ready(self) -> None:
        model = build_tray_model(TrayContext(TrayState.READY))
        self.system_tray_icon.setToolTip("Ritualist - Ready")
        if model.tooltip and model.tooltip != "Ritualist is ready":
            self.system_tray_icon.setToolTip(model.tooltip)

    def handle_taskbar_created(self) -> None:
        self.received_taskbar_created = True
        self.show()

    def close(self) -> None:
        self.hide()


@dataclass
class TrayQtTypes:
    QApplication: Any
    QMenu: Any
    QAction: Any
    QIcon: Any
    QSystemTrayIcon: Any
    QTimer: Any | None = None


@dataclass
class FakeSignal:
    callbacks: list[Callable[..., None]] = field(default_factory=list)

    def connect(self, callback: Callable[..., None]) -> None:
        self.callbacks.append(callback)

    def emit(self, *args: object) -> None:
        for callback in list(self.callbacks):
            callback(*args)


class FakeAction:
    def __init__(self, label: str, parent: object | None = None) -> None:
        self.label = label
        self.parent = parent
        self.enabled = True
        self.triggered = FakeSignal()

    def setEnabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)


class FakeMenu:
    def __init__(self) -> None:
        self.entries: list[FakeAction | FakeMenu | None] = []
        self.title = ""

    def addAction(self, action: FakeAction) -> None:
        self.entries.append(action)

    def addMenu(self, label: str) -> "FakeMenu":
        menu = FakeMenu()
        menu.title = label
        self.entries.append(menu)
        return menu

    def addSeparator(self) -> None:
        self.entries.append(None)


class FakeSystemTrayIcon:
    class ActivationReason:
        Trigger = 1

    def __init__(self, icon: object | None = None, parent: object | None = None) -> None:
        self.icon = icon
        self.parent = parent
        self.menu: object | None = None
        self.tooltip = ""
        self.visible = False
        self.activated = FakeSignal()
        self.show_calls = 0
        self.hide_calls = 0

    def setContextMenu(self, menu: object) -> None:
        self.menu = menu

    def setToolTip(self, tooltip: str) -> None:
        self.tooltip = tooltip

    def show(self) -> None:
        self.visible = True
        self.show_calls += 1

    def hide(self) -> None:
        self.visible = False
        self.hide_calls += 1


class FakeIcon:
    @classmethod
    def fromTheme(cls, _name: str) -> "FakeIcon":
        return cls()

    def isNull(self) -> bool:
        return False


class FakeApplication:
    def __init__(self) -> None:
        self.quit_on_last_window_closed: bool | None = None
        self.quit_called = False
        self.exec_called = False

    def setQuitOnLastWindowClosed(self, value: bool) -> None:
        self.quit_on_last_window_closed = bool(value)

    def quit(self) -> None:
        self.quit_called = True

    def exec(self) -> int:
        self.exec_called = True
        return 0


class FakeTimer:
    def __init__(self) -> None:
        self.timeout = FakeSignal()
        self.interval_ms: int | None = None

    def start(self, interval_ms: int) -> None:
        self.interval_ms = int(interval_ms)


def fake_qt_types() -> TrayQtTypes:
    return TrayQtTypes(
        QApplication=FakeApplication,
        QMenu=FakeMenu,
        QAction=FakeAction,
        QIcon=FakeIcon,
        QSystemTrayIcon=FakeSystemTrayIcon,
        QTimer=FakeTimer,
    )


def create_agent_tray(
    app: Any,
    on_action: TrayActionHandler,
    *,
    qt_types: TrayQtTypes | None = None,
    menu_context: TrayMenuContext | None = None,
) -> AgentTray:
    qt = qt_types or load_tray_qt_types()
    menu = qt.QMenu()
    actions: dict[MenuAction, Any] = {}
    _populate_menu(menu, build_tray_menu(menu_context), on_action, qt, actions)

    icon = qt.QIcon.fromTheme("ritualist")
    tray = qt.QSystemTrayIcon(icon, app)
    tray.setContextMenu(menu)
    agent_tray = AgentTray(
        app=app,
        system_tray_icon=tray,
        menu=menu,
        actions=actions,
        on_action=on_action,
    )
    agent_tray.set_ready()
    _connect_left_click(tray, on_action, qt)
    return agent_tray


def load_tray_qt_types() -> TrayQtTypes:
    try:
        from PySide6.QtCore import QTimer
        from PySide6.QtGui import QAction, QIcon
        from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon
    except ImportError as exc:
        from ritualist.errors import DependencyMissingError

        raise DependencyMissingError("Resident Agent tray requires PySide6") from exc
    return TrayQtTypes(
        QApplication=QApplication,
        QMenu=QMenu,
        QAction=QAction,
        QIcon=QIcon,
        QSystemTrayIcon=QSystemTrayIcon,
        QTimer=QTimer,
    )


def _populate_menu(
    menu: Any,
    items: tuple[MenuItem, ...],
    on_action: TrayActionHandler,
    qt: TrayQtTypes,
    actions: dict[MenuAction, Any],
) -> None:
    for item in items:
        if item.children:
            submenu = menu.addMenu(item.label)
            _populate_menu(submenu, item.children, on_action, qt, actions)
            continue
        if item.action is None:
            menu.addSeparator()
            continue
        action = qt.QAction(item.label, menu)
        action.setEnabled(item.enabled)
        action.triggered.connect(_action_callback(on_action, item.action))
        menu.addAction(action)
        actions[item.action] = action


def _connect_left_click(tray: Any, on_action: TrayActionHandler, qt: TrayQtTypes) -> None:
    reason_type = getattr(qt.QSystemTrayIcon, "ActivationReason", qt.QSystemTrayIcon)
    trigger = getattr(reason_type, "Trigger", None)

    def handle_activated(reason: object) -> None:
        if trigger is None or reason == trigger:
            on_action(MenuAction.OPEN_RITUALIST)

    tray.activated.connect(handle_activated)


def _action_callback(on_action: TrayActionHandler, action: MenuAction) -> Callable[[], None]:
    def handle_action(*_args: object) -> None:
        on_action(action)

    return handle_action
