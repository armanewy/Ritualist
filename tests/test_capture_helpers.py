from __future__ import annotations

import sys
from types import ModuleType

import pytest

from ritualist.adapters.fake import FakeAdapters
from ritualist.adapters.windows_uia import WindowInspection
from ritualist.adapters.window_manager import WindowsWindowManager
from ritualist.capture_helpers import CaptureHelperController
from ritualist.errors import RitualistError
from ritualist.models import Recipe


class FakePathPicker:
    def __init__(
        self,
        *,
        app_path: str | None = None,
        file_path: str | None = None,
        folder_path: str | None = None,
    ) -> None:
        self.app_path = app_path
        self.file_path = file_path
        self.folder_path = folder_path

    def browse_app_path(self) -> str | None:
        return self.app_path

    def browse_file_path(self) -> str | None:
        return self.file_path

    def browse_folder_path(self) -> str | None:
        return self.folder_path


def test_capture_foreground_window_title_reuses_selected_recipe_variable() -> None:
    fakes = FakeAdapters()
    fakes.window.responses["foreground_window_title"] = "Battle.net"
    recipe = _recipe({"app_window": "Old Window"})

    capture = CaptureHelperController(fakes.bundle()).pick_foreground_window_title(
        recipe=recipe,
        variable_name="app_window",
    )

    assert capture.value == "Battle.net"
    assert capture.recipe_value == "{{ app_window }}"
    assert capture.variable_update == {"app_window": "Battle.net"}
    assert fakes.window.calls == [("foreground_window_title", (), {})]


def test_capture_browse_paths_are_explicit_and_side_effect_minimal() -> None:
    fakes = FakeAdapters()
    recipe = _recipe({"app_path": "old.exe", "file_path": "old.txt", "folder_path": "C:\\Old"})
    controller = CaptureHelperController(
        fakes.bundle(),
        path_picker=FakePathPicker(
            app_path="C:\\Games\\Launcher.exe",
            file_path="C:\\Users\\aoztu\\notes.txt",
            folder_path="C:\\Users\\aoztu\\Documents",
        ),
    )

    app_capture = controller.browse_app_path(recipe=recipe)
    file_capture = controller.browse_file_path(recipe=recipe)
    folder_capture = controller.browse_folder_path(recipe=recipe)

    assert app_capture is not None
    assert app_capture.recipe_value == "{{ app_path }}"
    assert app_capture.variable_update == {"app_path": "C:\\Games\\Launcher.exe"}
    assert file_capture is not None
    assert file_capture.recipe_value == "{{ file_path }}"
    assert folder_capture is not None
    assert folder_capture.recipe_value == "{{ folder_path }}"
    assert fakes.window.calls == []
    assert fakes.desktop.calls == []


def test_cancelled_path_browse_returns_none() -> None:
    controller = CaptureHelperController(
        FakeAdapters().bundle(),
        path_picker=FakePathPicker(app_path=None),
    )

    assert controller.browse_app_path(recipe=_recipe({"app_path": "demo.exe"})) is None


def test_capture_inspects_window_from_recipe_variable_and_chooses_visible_text() -> None:
    fakes = FakeAdapters()
    fakes.desktop.responses["inspect_windows"] = [
        WindowInspection(title="Battle.net", labels=["Diablo IV", "Play", "Settings"])
    ]
    recipe = _recipe({"app_window": "Battle", "button_text": "Old"})
    controller = CaptureHelperController(fakes.bundle())

    inspection = controller.inspect_window_text(
        recipe=recipe,
        variable_name="app_window",
        control_type="Button",
    )
    choice = controller.choose_visible_text(
        inspection,
        text="Play",
        recipe=recipe,
        variable_name="button_text",
    )

    assert inspection.query == "Battle"
    assert inspection.labels == ("Diablo IV", "Play", "Settings")
    assert choice.window_title_contains == "Battle.net"
    assert choice.recipe_text == "{{ button_text }}"
    assert choice.variable_update == {"button_text": "Play"}
    assert choice.click_text_step() == {
        "action": "desktop.click_text",
        "window_title_contains": "Battle.net",
        "text": "{{ button_text }}",
        "exact": True,
        "control_type": "Button",
        "requires_confirmation": True,
    }
    assert fakes.desktop.calls == [
        (
            "inspect_windows",
            (),
            {"title_contains": "Battle", "limit": 30, "control_type": "Button"},
        )
    ]


def test_visible_text_choice_requires_explicit_label_selection() -> None:
    fakes = FakeAdapters()
    fakes.desktop.responses["inspect_windows"] = [
        WindowInspection(title="Vendor App", labels=["Connect", "Cancel"])
    ]
    inspection = CaptureHelperController(fakes.bundle()).inspect_window_text(
        window_title_contains="Vendor",
    )

    with pytest.raises(RitualistError, match="exactly one"):
        CaptureHelperController(fakes.bundle()).choose_visible_text(inspection)

    choice = CaptureHelperController(fakes.bundle()).choose_visible_text(
        inspection,
        label_index=0,
    )

    assert choice.click_text_step() == {
        "action": "desktop.click_text",
        "window_title_contains": "Vendor App",
        "text": "Connect",
        "exact": True,
    }


def test_windows_foreground_window_title_uses_lazy_win32gui_import(monkeypatch) -> None:
    win32gui = ModuleType("win32gui")
    win32gui.GetForegroundWindow = lambda: 123
    win32gui.GetWindowText = lambda handle: "Active Title" if handle == 123 else ""
    monkeypatch.setattr("ritualist.adapters.window_manager._ensure_windows", lambda: None)
    monkeypatch.setitem(sys.modules, "win32gui", win32gui)

    assert WindowsWindowManager().foreground_window_title() == "Active Title"


def _recipe(variables: dict[str, object]) -> Recipe:
    return Recipe.model_validate(
        {
            "id": "capture_test",
            "name": "Capture Test",
            "variables": variables,
            "steps": [{"action": "wait.seconds", "seconds": 1}],
        }
    )
