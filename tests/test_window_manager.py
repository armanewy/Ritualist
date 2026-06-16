from __future__ import annotations

import sys
from types import ModuleType
from types import SimpleNamespace

from ritualist.adapters.window_manager import WindowsWindowManager


class FakeWindow:
    def __init__(self, title: str, *, rect=None) -> None:
        self.title = title
        self.rect = rect
        self.focused = False
        self.minimized = False
        self.maximized = False

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


class FakeDesktop:
    def __init__(self, windows) -> None:
        self._windows = windows

    def windows(self):
        return self._windows


def test_window_exists_zero_timeout_performs_immediate_scan(monkeypatch):
    pywinauto = ModuleType("pywinauto")
    pywinauto.Desktop = lambda backend: FakeDesktop([FakeWindow("Battle.net")])
    monkeypatch.setattr("ritualist.adapters.window_manager._ensure_windows", lambda: None)
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
    monkeypatch.setattr("ritualist.adapters.window_manager._ensure_windows", lambda: None)
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
