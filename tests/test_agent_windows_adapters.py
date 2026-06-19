from __future__ import annotations

import pytest

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
