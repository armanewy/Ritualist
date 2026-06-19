from __future__ import annotations

import pytest

import setpiece.agent.window_activation as window_activation
from setpiece.agent.window_activation import (
    _activate_win32_window,
    _apply_transient_tool_window_style,
    place_qml_window,
)
from setpiece.agent.windows.hotkey import (
    ERROR_HOTKEY_ALREADY_REGISTERED,
    DEFAULT_HOTKEY,
    FakeGlobalHotkeyAdapter,
    HotkeySpec,
    WindowsGlobalHotkeyAdapter,
)
from setpiece.agent.windows.monitor_geometry import (
    FakeMonitorGeometryAdapter,
    MonitorGeometry,
    Point,
    WindowsMonitorGeometryAdapter,
    taskbar_edge,
)
from setpiece.agent.windows.shell_events import WindowsShellEventAdapter
from setpiece.agent.windows.tray_geometry import (
    TrayIconIdentity,
    WindowsTrayGeometryAdapter,
)
from setpiece.errors import PlatformUnsupportedError
from setpiece.overlay import ScreenRect


class FakeHotkeyWinApi:
    def __init__(self, *, register_ok: bool = True, error_code: int = 0) -> None:
        self.register_ok = register_ok
        self.error_code = error_code
        self.register_calls = []
        self.unregister_calls = []
        self.messages = []

    def register_hotkey(self, hwnd, hotkey_id, modifiers, virtual_key):
        self.register_calls.append((hwnd, hotkey_id, modifiers, virtual_key))
        return self.register_ok

    def unregister_hotkey(self, hwnd, hotkey_id):
        self.unregister_calls.append((hwnd, hotkey_id))
        return True

    def get_last_error(self):
        return self.error_code

    def peek_hotkey_message(self):
        if not self.messages:
            return None
        return self.messages.pop(0)


class FakeWindowHotkeyWinApi(FakeHotkeyWinApi):
    def __init__(self) -> None:
        super().__init__()
        self.created: list[int] = []
        self.destroyed: list[int] = []

    def create_hotkey_window(self, hotkey_id):
        self.created.append(hotkey_id)
        return 1234

    def destroy_hotkey_window(self, hwnd):
        self.destroyed.append(hwnd)


class FakeWindowStyleApi:
    def __init__(self, style: int) -> None:
        self.style = style
        self.set_style_calls: list[tuple[int, int, int]] = []
        self.set_window_pos_calls: list[tuple[int, int, int]] = []

    def GetWindowLongPtrW(self, hwnd, index):
        return self.style

    def SetWindowLongPtrW(self, hwnd, index, style):
        self.set_style_calls.append((int(hwnd), int(index), int(style)))
        self.style = int(style)
        return 1

    def SetWindowPos(self, hwnd, _insert_after, _x, _y, _cx, _cy, flags):
        self.set_window_pos_calls.append((int(hwnd), 0, int(flags)))
        return True


class FakeActivationUser32:
    def __init__(self, *, foreground_after_set: bool = False, switch_succeeds: bool = True) -> None:
        self.foreground_after_set = foreground_after_set
        self.switch_succeeds = switch_succeeds
        self.foreground = 999
        self.calls: list[tuple[str, int]] = []

    def ShowWindow(self, hwnd, _show):
        self.calls.append(("ShowWindow", int(hwnd)))
        return True

    def SetWindowPos(self, hwnd, _insert_after, _x, _y, _cx, _cy, _flags):
        self.calls.append(("SetWindowPos", int(hwnd)))
        return True

    def GetWindowThreadProcessId(self, hwnd, _pid):
        return 20 if int(hwnd) == self.foreground else 10

    def GetForegroundWindow(self):
        return self.foreground

    def AttachThreadInput(self, _source, _target, _attach):
        return True

    def BringWindowToTop(self, hwnd):
        self.calls.append(("BringWindowToTop", int(hwnd)))
        return True

    def SetForegroundWindow(self, hwnd):
        self.calls.append(("SetForegroundWindow", int(hwnd)))
        if self.foreground_after_set:
            self.foreground = int(hwnd)
        return True

    def SetActiveWindow(self, hwnd):
        self.calls.append(("SetActiveWindow", int(hwnd)))
        return hwnd

    def SetFocus(self, hwnd):
        self.calls.append(("SetFocus", int(hwnd)))
        return hwnd

    def SwitchToThisWindow(self, hwnd, _alt_tab):
        self.calls.append(("SwitchToThisWindow", int(hwnd)))
        if self.switch_succeeds:
            self.foreground = int(hwnd)


class FakeKernel32:
    def GetCurrentThreadId(self):
        return 30


class FakeWinTypes:
    HWND = int


class FakeCtypes:
    c_int = int
    c_ssize_t = int


class FakeQtRect:
    def __init__(self, x: int, y: int, width: int, height: int) -> None:
        self._x = x
        self._y = y
        self._width = width
        self._height = height

    def x(self) -> int:
        return self._x

    def y(self) -> int:
        return self._y

    def width(self) -> int:
        return self._width

    def height(self) -> int:
        return self._height


class FakeQtScreen:
    def __init__(self, rect: FakeQtRect) -> None:
        self.rect = rect

    def availableGeometry(self) -> FakeQtRect:
        return self.rect


class FakePositionedRoot:
    def __init__(self, rect: FakeQtRect, width: int, height: int) -> None:
        self._screen = FakeQtScreen(rect)
        self._width = width
        self._height = height
        self.positions: list[tuple[int, int]] = []

    def screen(self) -> FakeQtScreen:
        return self._screen

    def width(self) -> int:
        return self._width

    def height(self) -> int:
        return self._height

    def setX(self, value: int) -> None:
        y = self.positions[-1][1] if self.positions else 0
        self.positions.append((value, y))

    def setY(self, value: int) -> None:
        x = self.positions[-1][0] if self.positions else 0
        self.positions[-1:] = [(x, value)]


class FakeShellNotifyApi:
    def __init__(self, rect: ScreenRect | None) -> None:
        self.rect = rect
        self.requests = []

    def notify_icon_rect(self, identity: TrayIconIdentity) -> ScreenRect | None:
        self.requests.append(identity)
        return self.rect


def test_default_hotkey_is_win_ctrl_r_and_registers_with_register_hotkey() -> None:
    winapi = FakeHotkeyWinApi()
    adapter = WindowsGlobalHotkeyAdapter(winapi=winapi, platform="win32")

    result = adapter.register()
    adapter.unregister()

    assert result.registered is True
    assert result.status == "registered"
    assert result.hotkey == DEFAULT_HOTKEY
    assert winapi.register_calls == [(None, 0x5254, 0x0008 | 0x0002, ord("R"))]
    assert winapi.unregister_calls == [(None, 0x5254)]


def test_transient_tool_windows_are_removed_from_taskbar_style() -> None:
    api = FakeWindowStyleApi(style=0x00040000)

    _apply_transient_tool_window_style(api, FakeWinTypes, FakeCtypes, 123)

    assert api.set_style_calls == [(123, -20, 0x00000080)]
    assert api.set_window_pos_calls
    assert api.set_window_pos_calls[0][2] & 0x0020


def test_activate_win32_window_falls_back_when_foreground_lock_blocks_focus() -> None:
    api = FakeActivationUser32(foreground_after_set=False)

    _activate_win32_window(api, FakeKernel32(), FakeWinTypes, 123, api.SwitchToThisWindow)

    assert ("SetForegroundWindow", 123) in api.calls
    assert ("SwitchToThisWindow", 123) in api.calls
    assert api.foreground == 123


def test_activate_win32_window_skips_fallback_when_foreground_succeeds() -> None:
    api = FakeActivationUser32(foreground_after_set=True)

    _activate_win32_window(api, FakeKernel32(), FakeWinTypes, 123, api.SwitchToThisWindow)

    assert ("SetForegroundWindow", 123) in api.calls
    assert ("SwitchToThisWindow", 123) not in api.calls


def test_picker_window_is_placed_near_bottom_right_work_area(monkeypatch) -> None:
    monkeypatch.setattr(window_activation, "_screen_at_cursor", lambda: None)
    root = FakePositionedRoot(FakeQtRect(100, 50, 1200, 800), width=400, height=520)

    place_qml_window(root, anchor="bottom-right", margin=16)

    assert root.positions[-1] == (884, 314)


def test_instrument_window_is_placed_on_right_edge_work_area(monkeypatch) -> None:
    monkeypatch.setattr(window_activation, "_screen_at_cursor", lambda: None)
    root = FakePositionedRoot(FakeQtRect(-1920, 0, 1920, 1040), width=420, height=520)

    place_qml_window(root, anchor="right-center", margin=16)

    assert root.positions[-1] == (-436, 260)


def test_hotkey_registers_against_message_window_when_available() -> None:
    winapi = FakeWindowHotkeyWinApi()
    adapter = WindowsGlobalHotkeyAdapter(winapi=winapi, platform="win32")

    result = adapter.register()
    winapi.messages.append(0x5254)
    event = adapter.poll()
    adapter.unregister()

    assert result.registered is True
    assert event is not None
    assert event.hotkey == DEFAULT_HOTKEY
    assert winapi.created == [0x5254]
    assert winapi.register_calls == [(1234, 0x5254, 0x0008 | 0x0002, ord("R"))]
    assert winapi.unregister_calls == [(1234, 0x5254)]
    assert winapi.destroyed == [1234]


def test_hotkey_poll_debounces_duplicate_messages_from_one_chord() -> None:
    winapi = FakeHotkeyWinApi()
    adapter = WindowsGlobalHotkeyAdapter(winapi=winapi, platform="win32")
    adapter.register()
    winapi.messages.extend([0x5254, 0x5254])

    first = adapter.poll()
    duplicate = adapter.poll()
    adapter.unregister()

    assert first is not None
    assert duplicate is None


def test_hotkey_conflict_reports_failure_without_marking_registered() -> None:
    winapi = FakeHotkeyWinApi(
        register_ok=False,
        error_code=ERROR_HOTKEY_ALREADY_REGISTERED,
    )
    adapter = WindowsGlobalHotkeyAdapter(winapi=winapi, platform="win32")

    result = adapter.register()
    unregister = adapter.unregister()

    assert result.registered is False
    assert result.status == "conflict"
    assert result.error_code == ERROR_HOTKEY_ALREADY_REGISTERED
    assert "already registered" in result.message
    assert unregister.status == "not_registered"
    assert winapi.unregister_calls == []


def test_hotkey_is_configurable_and_poll_does_not_record_keys() -> None:
    winapi = FakeHotkeyWinApi()
    adapter = WindowsGlobalHotkeyAdapter(
        hotkey="ctrl+alt+f9",
        hotkey_id=77,
        winapi=winapi,
        platform="win32",
    )

    adapter.register()
    winapi.messages.append(77)
    event = adapter.poll()

    assert event is not None
    assert event.hotkey_id == 77
    assert event.hotkey == HotkeySpec(("ctrl", "alt", "f9"))
    assert winapi.register_calls == [(None, 77, 0x0002 | 0x0001, 0x78)]


def test_non_windows_hotkey_reports_unsupported() -> None:
    result = WindowsGlobalHotkeyAdapter(platform="linux").register()

    assert result.registered is False
    assert result.status == "unsupported"


def test_fake_hotkey_adapter_supports_cross_platform_events() -> None:
    adapter = FakeGlobalHotkeyAdapter(hotkey=["win", "ctrl", "r"])

    result = adapter.register()
    adapter.emit()

    assert result.status == "registered"
    assert adapter.poll() is not None
    assert adapter.poll() is None


def test_monitor_geometry_selects_target_monitor_work_area_and_taskbar_edge() -> None:
    primary = MonitorGeometry(
        handle="primary",
        monitor_rect=ScreenRect(0, 0, 1920, 1080),
        work_area=ScreenRect(0, 0, 1920, 1040),
        primary=True,
    )
    secondary = MonitorGeometry(
        handle="secondary",
        monitor_rect=ScreenRect(1920, 0, 1600, 900),
        work_area=ScreenRect(1960, 0, 1560, 900),
    )
    adapter = FakeMonitorGeometryAdapter([primary, secondary], cursor=Point(2000, 50))

    selection = adapter.target_monitor()

    assert selection.monitor == secondary
    assert selection.monitor.work_area == ScreenRect(1960, 0, 1560, 900)
    assert selection.monitor.taskbar_edge == "left"


@pytest.mark.parametrize(
    ("monitor_rect", "work_area", "expected"),
    [
        (ScreenRect(0, 0, 100, 100), ScreenRect(10, 0, 90, 100), "left"),
        (ScreenRect(0, 0, 100, 100), ScreenRect(0, 10, 100, 90), "top"),
        (ScreenRect(0, 0, 100, 100), ScreenRect(0, 0, 90, 100), "right"),
        (ScreenRect(0, 0, 100, 100), ScreenRect(0, 0, 100, 90), "bottom"),
        (ScreenRect(0, 0, 100, 100), ScreenRect(0, 0, 100, 100), None),
    ],
)
def test_taskbar_edge_detects_any_edge(monitor_rect, work_area, expected) -> None:
    assert taskbar_edge(monitor_rect, work_area) == expected


def test_monitor_removal_falls_back_to_point_monitor_then_primary() -> None:
    primary = MonitorGeometry(
        handle="primary",
        monitor_rect=ScreenRect(0, 0, 100, 100),
        work_area=ScreenRect(0, 0, 100, 90),
        primary=True,
    )
    secondary = MonitorGeometry(
        handle="secondary",
        monitor_rect=ScreenRect(100, 0, 100, 100),
        work_area=ScreenRect(100, 0, 100, 100),
    )
    adapter = FakeMonitorGeometryAdapter([primary, secondary])

    point_fallback = adapter.target_monitor(point=(120, 10), preferred_handle="removed")
    primary_fallback = adapter.target_monitor(point=(999, 999), preferred_handle="removed")

    assert point_fallback.monitor == secondary
    assert point_fallback.fallback_used is True
    assert primary_fallback.monitor == primary
    assert primary_fallback.reason == "point was outside current monitors"


def test_windows_monitor_adapter_rejects_non_windows_platform() -> None:
    with pytest.raises(PlatformUnsupportedError, match="Windows monitor geometry"):
        WindowsMonitorGeometryAdapter(platform="linux").list_monitors()


def test_tray_icon_uses_shell_notify_icon_rect_when_available() -> None:
    monitor = MonitorGeometry(
        handle="primary",
        monitor_rect=ScreenRect(0, 0, 1920, 1080),
        work_area=ScreenRect(0, 0, 1920, 1040),
        primary=True,
    )
    monitor_adapter = FakeMonitorGeometryAdapter([monitor], cursor=(20, 20))
    shellapi = FakeShellNotifyApi(ScreenRect(1800, 1000, 24, 24))
    adapter = WindowsTrayGeometryAdapter(
        shellapi=shellapi,
        monitor_adapter=monitor_adapter,
        platform="win32",
    )

    result = adapter.icon_geometry(TrayIconIdentity(hwnd=100, uid=2))

    assert result.source == "shell_notify_icon"
    assert result.rect == ScreenRect(1800, 1000, 24, 24)
    assert result.monitor == monitor
    assert shellapi.requests == [TrayIconIdentity(hwnd=100, uid=2)]


def test_tray_icon_falls_back_to_cursor_and_target_monitor() -> None:
    monitor = MonitorGeometry(
        handle="secondary",
        monitor_rect=ScreenRect(1920, 0, 1600, 900),
        work_area=ScreenRect(1920, 0, 1600, 860),
    )
    monitor_adapter = FakeMonitorGeometryAdapter([monitor], cursor=(2100, 850))
    adapter = WindowsTrayGeometryAdapter(
        shellapi=FakeShellNotifyApi(None),
        monitor_adapter=monitor_adapter,
        platform="win32",
    )

    result = adapter.icon_geometry(TrayIconIdentity(hwnd=100, uid=2))

    assert result.source == "cursor"
    assert result.rect == ScreenRect(2100, 850, 1, 1)
    assert result.monitor == monitor


def test_tray_icon_non_windows_reports_unsupported() -> None:
    result = WindowsTrayGeometryAdapter(platform="linux").icon_geometry()

    assert result.source == "unsupported"
    assert result.rect is None


def test_taskbar_created_registers_explorer_restart_message() -> None:
    class FakeShellEventApi:
        def __init__(self) -> None:
            self.names = []

        def register_window_message(self, name: str) -> int:
            self.names.append(name)
            return 0xC001

    api = FakeShellEventApi()
    adapter = WindowsShellEventAdapter(winapi=api, platform="win32")

    registration = adapter.register_taskbar_created()

    assert registration.supported is True
    assert registration.taskbar_created_message == 0xC001
    assert adapter.is_taskbar_created(0xC001) is True
    assert adapter.is_taskbar_created(0xC002) is False
    assert api.names == ["TaskbarCreated"]


def test_taskbar_created_non_windows_reports_unsupported() -> None:
    registration = WindowsShellEventAdapter(platform="linux").register_taskbar_created()

    assert registration.supported is False
    assert registration.taskbar_created_message is None
