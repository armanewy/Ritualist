from __future__ import annotations

import sys
from types import ModuleType

from ritualist.adapters.window_manager import WindowsWindowManager


class FakeWindow:
    def __init__(self, title: str) -> None:
        self.title = title

    def window_text(self) -> str:
        return self.title


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
