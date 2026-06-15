from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from ritualist.models import Recipe
from ritualist.ui import main_window


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
    assert window.stop_button.text() == "Stop"
    assert window.recipe is recipe
    assert window.path_edit.text() == str(recipe_path)
    assert window.status_label.text() == "Loaded gaming_mode"

    window.close()
