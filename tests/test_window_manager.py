from __future__ import annotations

import sys
from types import ModuleType
from types import SimpleNamespace

import pytest

from setpiece.adapters.fake import FakeWindowAdapter
from setpiece.adapters.window_manager import WindowsWindowManager
from setpiece.errors import PlatformUnsupportedError
from setpiece.overlay import ScreenRect


class FakeWindow:
    def __init__(self, title: str, *, rect=None) -> None:
        self.title = title
        self.rect = rect
        self.focused = False
        self.minimized = False
        self.maximized = False
        self.restored = False
        self.moves = []

    def window_text(self) -> str:
        return self.title

    def rectangle(self):
        if self.rect is None:
            raise RuntimeError("no rectangle")
        return self.rect

    def set_focus(self) -> None:
        self.focused = True

    def minimize(self) -> None:
        self.minimized = True

    def maximize(self) -> None:
        self.maximized = True

    def restore(self) -> None:
        self.restored = True

    def move_window(self, x, y, width, height, *, repaint=True) -> None:
        self.moves.append((x, y, width, height, repaint))
        self.rect = SimpleNamespace(left=x, top=y, right=x + width, bottom=y + height)


class FakeDesktop:
    def __init__(self, windows) -> None:
        self._windows = windows

    def windows(self):
        return self._windows


def test_window_exists_zero_timeout_performs_immediate_scan(monkeypatch):
    pywinauto = ModuleType("pywinauto")
    pywinauto.Desktop = lambda backend: FakeDesktop([FakeWindow("Battle.net")])
    monkeypatch.setattr("setpiece.adapters.window_manager._ensure_windows", lambda: None)
    monkeypatch.setitem(sys.modules, "pywinauto", pywinauto)

    exists = WindowsWindowManager().window_exists(
        title_contains="Battle.net",
        process_name=None,
        timeout_seconds=0,
    )

    assert exists is True


def test_window_actions_return_window_bounds(monkeypatch):
    window = FakeWindow(
        "Battle.net",
        rect=SimpleNamespace(left=100, top=200, right=500, bottom=460),
    )
    pywinauto = ModuleType("pywinauto")
    pywinauto.Desktop = lambda backend: FakeDesktop([window])
    monkeypatch.setattr("setpiece.adapters.window_manager._ensure_windows", lambda: None)
    monkeypatch.setitem(sys.modules, "pywinauto", pywinauto)

    region = WindowsWindowManager().focus(
        title_contains="Battle.net",
        process_name=None,
        timeout_seconds=0,
    )

    assert window.focused is True
    assert region.window_title == "Battle.net"
    assert region.rect is not None
    assert region.rect.x == 100
    assert region.rect.y == 200
    assert region.rect.width == 400
    assert region.rect.height == 260


def test_window_layout_methods_move_resize_and_restore(monkeypatch):
    window = FakeWindow(
        "Battle.net",
        rect=SimpleNamespace(left=100, top=200, right=500, bottom=460),
    )
    pywinauto = ModuleType("pywinauto")
    pywinauto.Desktop = lambda backend: FakeDesktop([window])
    monkeypatch.setattr("setpiece.adapters.window_manager._ensure_windows", lambda: None)
    monkeypatch.setitem(sys.modules, "pywinauto", pywinauto)

    manager = WindowsWindowManager()
    moved = manager.move_window(
        title_contains="Battle.net",
        process_name=None,
        timeout_seconds=0,
        x=40,
        y=50,
        width=300,
        height=200,
    )
    resized = manager.resize_window(
        title_contains="Battle.net",
        process_name=None,
        timeout_seconds=0,
        width=640,
        height=360,
    )
    restored = manager.restore_window(
        title_contains="Battle.net",
        process_name=None,
        timeout_seconds=0,
    )
    maximized = manager.maximize_window(
        title_contains="Battle.net",
        process_name=None,
        timeout_seconds=0,
    )

    assert window.moves == [
        (40, 50, 300, 200, True),
        (40, 50, 640, 360, True),
    ]
    assert window.restored is True
    assert window.maximized is True
    assert moved.rect == ScreenRect(40, 50, 300, 200)
    assert resized.rect == ScreenRect(40, 50, 640, 360)
    assert restored.window_title == "Battle.net"
    assert maximized.window_title == "Battle.net"


def test_move_window_uses_hwnd_wrapper_when_uia_wrapper_has_no_move_window(monkeypatch):
    class FakeUIAWindow:
        handle = 1234

        def __init__(self) -> None:
            self.title = "Battle.net"
            self.rect = SimpleNamespace(left=100, top=200, right=500, bottom=460)

        def window_text(self) -> str:
            return self.title

        def process_id(self) -> int:
            return 42

        def rectangle(self):
            return self.rect

    handles = {}
    wrapper_calls = []

    class FakeHwndWrapper:
        def __init__(self, handle) -> None:
            self.window = handles[int(handle)]

        def move_window(self, x, y, width, height, *, repaint=True) -> None:
            wrapper_calls.append((x, y, width, height, repaint))
            self.window.rect = SimpleNamespace(left=x, top=y, right=x + width, bottom=y + height)

    window = FakeUIAWindow()
    handles[window.handle] = window
    pywinauto = ModuleType("pywinauto")
    pywinauto.Desktop = lambda backend: FakeDesktop([window])
    controls = ModuleType("pywinauto.controls")
    hwndwrapper = ModuleType("pywinauto.controls.hwndwrapper")
    hwndwrapper.HwndWrapper = FakeHwndWrapper
    monkeypatch.setattr("setpiece.adapters.window_manager._ensure_windows", lambda: None)
    monkeypatch.setitem(sys.modules, "pywinauto", pywinauto)
    monkeypatch.setitem(sys.modules, "pywinauto.controls", controls)
    monkeypatch.setitem(sys.modules, "pywinauto.controls.hwndwrapper", hwndwrapper)

    region = WindowsWindowManager().move_window(
        title_contains="Battle.net",
        process_name=None,
        timeout_seconds=0,
        x=40,
        y=50,
    )

    assert wrapper_calls == [(40, 50, 400, 260, True)]
    assert region.rect == ScreenRect(40, 50, 400, 260)


@pytest.mark.parametrize(
    ("method_name", "expected"),
    [
        ("snap_left", ScreenRect(1920, 0, 960, 1040)),
        ("snap_right", ScreenRect(2880, 0, 960, 1040)),
        ("snap_top", ScreenRect(1920, 0, 1920, 520)),
        ("snap_bottom", ScreenRect(1920, 520, 1920, 520)),
    ],
)
def test_snap_methods_use_window_monitor_work_area(monkeypatch, method_name, expected):
    window = FakeWindow(
        "Battle.net",
        rect=SimpleNamespace(left=2000, top=100, right=2400, bottom=500),
    )
    pywinauto = ModuleType("pywinauto")
    pywinauto.Desktop = lambda backend: FakeDesktop([window])
    monkeypatch.setattr("setpiece.adapters.window_manager._ensure_windows", lambda: None)
    monkeypatch.setattr(
        "setpiece.adapters.window_manager._monitor_rects",
        lambda: [ScreenRect(0, 0, 1920, 1040), ScreenRect(1920, 0, 1920, 1040)],
    )
    monkeypatch.setitem(sys.modules, "pywinauto", pywinauto)

    region = getattr(WindowsWindowManager(), method_name)(
        title_contains="Battle.net",
        process_name=None,
        timeout_seconds=0,
    )

    assert region.rect == expected
    assert window.moves == [
        (expected.x, expected.y, expected.width, expected.height, True),
    ]


def test_list_monitors_returns_work_areas(monkeypatch):
    win32api = ModuleType("win32api")
    win32api.EnumDisplayMonitors = lambda: [
        ("primary", None, None),
        ("secondary", None, None),
    ]
    win32api.GetMonitorInfo = lambda monitor: {
        "primary": {"Work": (0, 0, 1920, 1040)},
        "secondary": {"Work": (1920, 0, 3840, 1040)},
    }[monitor]
    monkeypatch.setattr("setpiece.adapters.window_manager._ensure_windows", lambda: None)
    monkeypatch.setitem(sys.modules, "win32api", win32api)

    assert WindowsWindowManager().list_monitors() == [
        ScreenRect(0, 0, 1920, 1040),
        ScreenRect(1920, 0, 1920, 1040),
    ]


def test_list_monitors_rejects_unsupported_platform(monkeypatch):
    monkeypatch.setattr("setpiece.adapters.window_manager.sys.platform", "linux")

    with pytest.raises(PlatformUnsupportedError, match="Windows UI/window automation"):
        WindowsWindowManager().list_monitors()


def test_fake_window_adapter_supports_layout_methods():
    fake = FakeWindowAdapter()

    moved = fake.move_window(
        title_contains="Demo",
        process_name=None,
        timeout_seconds=0,
        x=5,
        y=6,
        width=700,
        height=400,
    )
    resized = fake.resize_window(
        title_contains="Demo",
        process_name=None,
        timeout_seconds=0,
        width=900,
        height=500,
    )
    snapped = fake.snap_left(title_contains="Demo", process_name=None, timeout_seconds=0)
    monitors = fake.list_monitors()

    assert moved.rect == ScreenRect(5, 6, 700, 400)
    assert resized.rect == ScreenRect(10, 20, 900, 500)
    assert snapped.rect == ScreenRect(0, 0, 960, 1080)
    assert monitors == [ScreenRect(0, 0, 1920, 1080)]
    assert [call[0] for call in fake.calls] == [
        "move_window",
        "resize_window",
        "snap_left",
        "list_monitors",
    ]
