from __future__ import annotations

import sys
from types import ModuleType
from types import SimpleNamespace

import pytest

from ritualist.adapters.windows_uia import WindowsUIAutomationAdapter
from ritualist.errors import RitualistError


class FakeElement:
    def __init__(
        self,
        text: str,
        *,
        visible: bool = True,
        enabled: bool = True,
        rect=None,
    ) -> None:
        self.text = text
        self.visible = visible
        self.enabled = enabled
        self.invoked = False
        self.clicked = False
        self.element_info = SimpleNamespace(name=text)
        self.rect = rect

    def window_text(self) -> str:
        return self.text

    def is_visible(self) -> bool:
        return self.visible

    def is_enabled(self) -> bool:
        return self.enabled

    def invoke(self) -> None:
        self.invoked = True

    def click_input(self, *, button: str) -> None:
        self.clicked = True

    def rectangle(self):
        if self.rect is None:
            raise RuntimeError("no rectangle")
        return self.rect


class FakeRoot(FakeElement):
    def __init__(self, title: str, descendants: list[FakeElement]) -> None:
        super().__init__(title)
        self._descendants = descendants

    def descendants(self, **_kwargs):
        return self._descendants


class FakeDesktop:
    def __init__(self, root: FakeRoot) -> None:
        self.root = root

    def windows(self):
        return [self.root]


def test_click_text_uses_invoke_before_click(monkeypatch):
    button = FakeElement("Play", rect=SimpleNamespace(left=100, top=200, right=180, bottom=240))
    desktop = FakeDesktop(FakeRoot("Battle.net", [button]))
    pywinauto = ModuleType("pywinauto")
    pywinauto.Desktop = lambda backend: desktop
    monkeypatch.setattr("ritualist.adapters.windows_uia._ensure_windows", lambda: None)
    monkeypatch.setitem(sys.modules, "pywinauto", pywinauto)

    region = WindowsUIAutomationAdapter().click_text(
        text="Play",
        window_title_contains="Battle.net",
        control_type=None,
        exact=True,
        button="left",
        timeout_seconds=0.01,
    )

    assert button.invoked is True
    assert button.clicked is False
    assert region.window_title == "Battle.net"
    assert region.target_text == "Play"
    assert region.rect is not None
    assert region.rect.x == 100
    assert region.rect.y == 200
    assert region.rect.width == 80
    assert region.rect.height == 40


def test_click_text_failure_includes_candidate_labels(monkeypatch):
    desktop = FakeDesktop(FakeRoot("Battle.net", [FakeElement("Diablo IV"), FakeElement("Settings")]))
    pywinauto = ModuleType("pywinauto")
    pywinauto.Desktop = lambda backend: desktop
    monkeypatch.setattr("ritualist.adapters.windows_uia._ensure_windows", lambda: None)
    monkeypatch.setitem(sys.modules, "pywinauto", pywinauto)

    with pytest.raises(RitualistError) as exc:
        WindowsUIAutomationAdapter().click_text(
            text="Play",
            window_title_contains="Battle.net",
            control_type=None,
            exact=True,
            button="left",
            timeout_seconds=0.01,
        )

    assert "Candidate labels" in str(exc.value)
    assert "Diablo IV" in str(exc.value)
    assert "Settings" in str(exc.value)


def test_find_text_region_returns_element_bounds(monkeypatch):
    button = FakeElement("Play", rect=SimpleNamespace(left=100, top=200, right=180, bottom=240))
    desktop = FakeDesktop(FakeRoot("Battle.net", [button]))
    pywinauto = ModuleType("pywinauto")
    pywinauto.Desktop = lambda backend: desktop
    monkeypatch.setattr("ritualist.adapters.windows_uia._ensure_windows", lambda: None)
    monkeypatch.setitem(sys.modules, "pywinauto", pywinauto)

    region = WindowsUIAutomationAdapter().find_text_region(
        text="Play",
        window_title_contains="Battle.net",
        control_type=None,
        exact=True,
        timeout_seconds=0.01,
    )

    assert region is not None
    assert region.window_title == "Battle.net"
    assert region.target_text == "Play"
    assert region.rect is not None
    assert region.rect.x == 100
    assert region.rect.y == 200
    assert region.rect.width == 80
    assert region.rect.height == 40


def test_text_visible_is_read_only(monkeypatch):
    button = FakeElement("Connected")
    desktop = FakeDesktop(FakeRoot("Vendor App", [button]))
    pywinauto = ModuleType("pywinauto")
    pywinauto.Desktop = lambda backend: desktop
    monkeypatch.setattr("ritualist.adapters.windows_uia._ensure_windows", lambda: None)
    monkeypatch.setitem(sys.modules, "pywinauto", pywinauto)

    visible = WindowsUIAutomationAdapter().text_visible(
        text="Connected",
        window_title_contains="Vendor App",
        control_type=None,
        exact=True,
        timeout_seconds=0.01,
    )

    assert visible is True
    assert button.invoked is False
    assert button.clicked is False
