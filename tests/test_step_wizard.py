from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from setpiece.capture_helpers import (
    CapturedValue,
    CapturedWindowInspection,
    VisibleTextChoice,
    WindowTextInspection,
)
from setpiece.errors import RecipeValidationError
from setpiece.models import Recipe
from setpiece.recipe_step_builder import RecipeStepAppendController, RecipeStepBuilder
from setpiece.recipe_loader import load_recipe
from setpiece.ui.step_wizard import AddStepDialog


def test_step_builder_builds_basic_wait_step():
    step = RecipeStepBuilder().build_step("wait.seconds", {"seconds": "1.5"})

    assert step == {"action": "wait.seconds", "seconds": 1.5}


def test_step_builder_preserves_play_confirmation_gate():
    step = RecipeStepBuilder().build_step(
        "desktop.click_text",
        {"text": "Play", "window_title_contains": "Battle.net"},
    )

    assert step["requires_confirmation"] is True


def test_step_builder_preserves_risky_browser_confirmation_gate():
    step = RecipeStepBuilder().build_step("browser.click_text", {"text": "Buy now"})

    assert step == {
        "action": "browser.click_text",
        "text": "Buy now",
        "requires_confirmation": True,
    }


def test_step_builder_rejects_unscoped_desktop_click():
    with pytest.raises(RecipeValidationError, match="window_title_contains"):
        RecipeStepBuilder().build_step(
            "desktop.click_text",
            {"text": "Launch", "window_title_contains": ""},
        )


def test_append_controller_creates_and_appends_local_recipe(tmp_path):
    controller = RecipeStepAppendController()
    path = tmp_path / "demo_recipe.yaml"

    recipe = controller.create_recipe_with_step(
        path,
        {"action": "wait.seconds", "seconds": 1.0},
    )
    recipe = controller.append_step(
        path,
        {"action": "wait.for_user", "prompt": "Ready?"},
    )
    loaded = load_recipe(path)

    assert recipe.id == "demo_recipe"
    assert loaded.name == "Demo Recipe"
    assert [step.action for step in loaded.steps] == ["wait.seconds", "wait.for_user"]


def test_append_controller_applies_variable_updates(tmp_path):
    controller = RecipeStepAppendController()
    path = tmp_path / "demo_recipe.yaml"

    controller.create_recipe_with_step(
        path,
        {"action": "app.launch", "command": "{{ app_path }}"},
        variable_updates={"app_path": "old.exe"},
    )
    controller.append_step(
        path,
        {"action": "app.launch", "command": "{{ app_path }}"},
        variable_updates={"app_path": "new.exe"},
    )
    loaded = load_recipe(path)

    assert loaded.variables["app_path"] == "new.exe"
    assert loaded.steps[0].command == "new.exe"
    assert loaded.steps[1].command == "new.exe"


def test_append_controller_ignores_variable_updates_not_used_by_step(tmp_path):
    controller = RecipeStepAppendController()
    path = tmp_path / "demo_recipe.yaml"

    controller.create_recipe_with_step(
        path,
        {"action": "app.launch", "command": "{{ app_path }}"},
        variable_updates={"app_path": "old.exe"},
    )
    controller.append_step(
        path,
        {"action": "wait.seconds", "seconds": 1.0},
        variable_updates={"app_path": "new.exe"},
    )
    loaded = load_recipe(path)

    assert loaded.variables["app_path"] == "old.exe"
    assert loaded.steps[0].command == "old.exe"


def test_add_step_dialog_builds_step_and_collapses_optional_fields():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    dialog = AddStepDialog()
    dialog.category_combo.setCurrentText("Waits")
    dialog.action_combo.setCurrentText("wait.seconds")

    assert app is not None
    assert dialog.optional_fields_container.isHidden() is True

    dialog.optional_toggle.setChecked(True)
    assert dialog.optional_fields_container.isHidden() is False

    seconds_widget = dialog._field_widgets["seconds"]
    assert isinstance(seconds_widget, QtWidgets.QLineEdit)
    seconds_widget.setText("2")

    dialog.accept()

    assert dialog.step_data == {"action": "wait.seconds", "seconds": 2.0}
    dialog.close()


def test_add_step_dialog_capture_helper_fills_window_variable():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    recipe = Recipe.model_validate(
        {
            "id": "demo",
            "name": "Demo",
            "variables": {"app_window": "Old"},
            "steps": [{"action": "wait.seconds", "seconds": 1}],
        }
    )

    class FakeCaptureController:
        def pick_foreground_window_title(self, *, recipe=None):
            return CapturedValue(
                value="Battle.net",
                source="foreground_window",
                variable_name="app_window",
            )

    dialog = AddStepDialog(capture_controller=FakeCaptureController(), recipe=recipe)
    dialog.category_combo.setCurrentText("Desktop UI")
    dialog.action_combo.setCurrentText("desktop.click_text")
    window_widget = dialog._field_widgets["window_title_contains"]

    assert app is not None
    assert isinstance(window_widget, QtWidgets.QLineEdit)

    dialog._capture_foreground_title(window_widget)

    assert window_widget.text() == "{{ app_window }}"
    assert dialog.variable_updates == {"app_window": "Battle.net"}
    dialog.close()


def test_add_step_dialog_discards_captured_variable_after_manual_edit():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    recipe = Recipe.model_validate(
        {
            "id": "demo",
            "name": "Demo",
            "variables": {"app_window": "Old"},
            "steps": [{"action": "wait.seconds", "seconds": 1}],
        }
    )

    class FakeCaptureController:
        def pick_foreground_window_title(self, *, recipe=None):
            return CapturedValue(
                value="Battle.net",
                source="foreground_window",
                variable_name="app_window",
            )

    dialog = AddStepDialog(capture_controller=FakeCaptureController(), recipe=recipe)
    dialog.category_combo.setCurrentText("Desktop UI")
    dialog.action_combo.setCurrentText("desktop.click_text")
    window_widget = dialog._field_widgets["window_title_contains"]
    text_widget = dialog._field_widgets["text"]

    assert app is not None
    assert isinstance(window_widget, QtWidgets.QLineEdit)
    assert isinstance(text_widget, QtWidgets.QLineEdit)

    dialog._capture_foreground_title(window_widget)
    window_widget.setText("Battle.net")
    text_widget.setText("Shop")
    dialog.accept()

    assert dialog.step_data == {
        "action": "desktop.click_text",
        "window_title_contains": "Battle.net",
        "text": "Shop",
    }
    assert dialog.variable_updates == {}
    dialog.close()


def test_add_step_dialog_discards_captured_variable_after_action_change():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    recipe = Recipe.model_validate(
        {
            "id": "demo",
            "name": "Demo",
            "variables": {"app_window": "Old"},
            "steps": [{"action": "wait.seconds", "seconds": 1}],
        }
    )

    class FakeCaptureController:
        def pick_foreground_window_title(self, *, recipe=None):
            return CapturedValue(
                value="Battle.net",
                source="foreground_window",
                variable_name="app_window",
            )

    dialog = AddStepDialog(capture_controller=FakeCaptureController(), recipe=recipe)
    dialog.category_combo.setCurrentText("Desktop UI")
    dialog.action_combo.setCurrentText("desktop.click_text")
    window_widget = dialog._field_widgets["window_title_contains"]

    assert app is not None
    assert isinstance(window_widget, QtWidgets.QLineEdit)

    dialog._capture_foreground_title(window_widget)
    dialog.category_combo.setCurrentText("Waits")
    dialog.action_combo.setCurrentText("wait.seconds")
    seconds_widget = dialog._field_widgets["seconds"]
    assert isinstance(seconds_widget, QtWidgets.QLineEdit)
    seconds_widget.setText("1")
    dialog.accept()

    assert dialog.step_data == {"action": "wait.seconds", "seconds": 1.0}
    assert dialog.variable_updates == {}
    dialog.close()


def test_add_step_dialog_inspect_text_marks_play_confirmation(monkeypatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    class FakeCaptureController:
        def inspect_window_text(self, **_kwargs):
            return WindowTextInspection(
                query="Battle.net",
                control_type="Button",
                windows=(CapturedWindowInspection(title="Battle.net", labels=("Play",)),),
            )

        def choose_visible_text(self, inspection, *, text, recipe=None):
            return VisibleTextChoice(
                window_title_contains="Battle.net",
                text=text,
                control_type=inspection.control_type,
                variable_name="button_text",
            )

    monkeypatch.setattr(
        "setpiece.ui.step_wizard.QInputDialog.getItem",
        lambda *_args, **_kwargs: ("Play", True),
    )
    dialog = AddStepDialog(capture_controller=FakeCaptureController())
    dialog.category_combo.setCurrentText("Desktop UI")
    dialog.action_combo.setCurrentText("desktop.click_text")
    text_widget = dialog._field_widgets["text"]
    confirmation_widget = dialog._field_widgets["requires_confirmation"]

    assert app is not None
    assert isinstance(text_widget, QtWidgets.QLineEdit)
    assert isinstance(confirmation_widget, QtWidgets.QCheckBox)

    dialog._inspect_text(text_widget)

    assert text_widget.text() == "{{ button_text }}"
    assert confirmation_widget.isChecked() is True
    assert dialog.variable_updates == {"button_text": "Play"}
    dialog.close()
