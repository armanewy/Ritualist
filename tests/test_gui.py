from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from ritualist.models import Recipe
from ritualist.doctor import DoctorCheck
from ritualist.ui import main_window
from ritualist.ui.diagnostics_dialog import DiagnosticsDialog


def test_main_window_has_personal_app_controls_and_loads_selected_recipe(tmp_path, monkeypatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    recipe_path = tmp_path / "gaming_mode.yaml"
    recipe = Recipe.model_validate(
        {
            "id": "gaming_mode",
            "name": "Gaming Mode",
            "steps": [{"action": "app.launch", "command": "demo.exe"}],
        }
    )
    monkeypatch.setattr(main_window, "discover_recipes", lambda: [(recipe_path, recipe, None)])
    monkeypatch.setattr(main_window, "load_recipe", lambda path: recipe)

    window = main_window.MainWindow()

    assert app is not None
    assert window.init_button.text() == "Initialize App"
    assert window.refresh_button.text() == "Refresh Recipes"
    assert window.run_button.text() == "Run"
    assert window.dry_run_button.text() == "Dry Run"
    assert window.doctor_button.text() == "Doctor"
    assert window.stop_button.text() == "Stop"
    assert window.recipe is recipe
    assert window.path_edit.text() == str(recipe_path)
    assert window.status_label.text() == "Loaded gaming_mode"

    window.close()


def test_main_window_doctor_prints_checks_without_running_recipe(tmp_path, monkeypatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    recipe_path = tmp_path / "gaming_mode.yaml"
    recipe = Recipe.model_validate(
        {
            "id": "gaming_mode",
            "name": "Gaming Mode",
            "steps": [{"action": "app.launch", "command": "demo.exe"}],
        }
    )
    monkeypatch.setattr(main_window, "discover_recipes", lambda: [(recipe_path, recipe, None)])
    monkeypatch.setattr(main_window, "load_recipe", lambda path: recipe)
    monkeypatch.setattr(
        main_window,
        "diagnose_recipe",
        lambda loaded: [DoctorCheck("ok", "recipe", f"loaded {loaded.id}")],
    )

    window = main_window.MainWindow()
    window.doctor_recipe()

    assert app is not None
    assert "Doctor: Gaming Mode (gaming_mode)" in window.log.toPlainText()
    assert "ok: recipe - loaded gaming_mode" in window.log.toPlainText()

    window.close()


def test_diagnostics_dialog_copies_text_to_clipboard():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    dialog = DiagnosticsDialog()

    dialog.copy_diagnostics()

    assert app is not None
    assert "App version:" in dialog.text.toPlainText()
    assert QtWidgets.QApplication.clipboard().text() == dialog.text.toPlainText()

    dialog.close()
