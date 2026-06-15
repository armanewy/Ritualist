from __future__ import annotations

from textwrap import dedent

import pytest

from ritualist.errors import RecipeValidationError
from ritualist.recipe_loader import load_recipe, load_recipe_for_diagnostics, load_recipe_reference


def test_load_recipe_renders_variables(tmp_path):
    path = tmp_path / "recipe.yaml"
    path.write_text(
        dedent(
            """
            version: "0.1"
            id: test_recipe
            name: Test
            variables:
              url: https://example.test
            steps:
              - action: browser.open
                name: Open page
                url: "{{ url }}"
            """
        ),
        encoding="utf-8",
    )

    recipe = load_recipe(path)

    assert recipe.name == "Test"
    assert recipe.steps[0].url == "https://example.test"


def test_load_recipe_supports_preflight_and_verify_assertions(tmp_path):
    marker = tmp_path / "marker.txt"
    marker.write_text("ok", encoding="utf-8")
    path = tmp_path / "recipe.yaml"
    path.write_text(
        dedent(
            f"""
            version: "0.1"
            id: test_recipe
            name: Test
            variables:
              marker: {marker}
            preflight:
              - action: assert.file_exists
                path: "${{marker}}"
            steps:
              - action: app.launch
                command: demo.exe
            verify:
              - action: assert.window_text_visible
                window_title_contains: Vendor App
                text: Connected
            """
        ),
        encoding="utf-8",
    )

    recipe = load_recipe(path)

    assert recipe.preflight[0].path == str(marker)
    assert recipe.steps[0].action == "app.launch"
    assert recipe.verify[0].text == "Connected"
    assert [step.action for step in recipe.execution_steps] == [
        "assert.file_exists",
        "app.launch",
        "assert.window_text_visible",
    ]


def test_load_recipe_supports_environment_contract(tmp_path):
    path = tmp_path / "recipe.yaml"
    path.write_text(
        dedent(
            """
            version: "0.1"
            id: test_recipe
            name: Test
            variables:
              app_window: Vendor App
            environment:
              os:
                - windows
              required_capabilities:
                - windows_uia
              expected_windows:
                - title_contains: "{{ app_window }}"
              expected_labels:
                - window_title_contains: "{{ app_window }}"
                  text: Connected
              variable_hints:
                app_window: Use the visible app title.
            steps:
              - action: window.wait
                title_contains: "{{ app_window }}"
            """
        ),
        encoding="utf-8",
    )

    recipe = load_recipe(path)

    assert recipe.environment.os == ["windows"]
    assert recipe.environment.required_capabilities == ["windows_uia"]
    assert recipe.environment.expected_windows[0].title_contains == "Vendor App"
    assert recipe.environment.expected_labels[0].text == "Connected"
    assert recipe.environment.variable_hints["app_window"] == "Use the visible app title."


def test_load_recipe_without_environment_uses_empty_contract(tmp_path):
    path = tmp_path / "recipe.yaml"
    path.write_text(
        dedent(
            """
            version: "0.1"
            id: test_recipe
            name: Test
            steps:
              - action: app.launch
                command: demo.exe
            """
        ),
        encoding="utf-8",
    )

    recipe = load_recipe(path)

    assert recipe.environment.os == []
    assert recipe.environment.required_capabilities == []
    assert recipe.environment.expected_windows == []
    assert recipe.environment.expected_labels == []


def test_load_recipe_for_diagnostics_reports_missing_variables(tmp_path):
    path = tmp_path / "recipe.yaml"
    path.write_text(
        dedent(
            """
            version: "0.1"
            id: test_recipe
            name: Test
            environment:
              variable_hints:
                app_path: Set this to the local executable path.
            steps:
              - action: app.launch
                command: "${app_path}"
            """
        ),
        encoding="utf-8",
    )

    recipe, _raw, missing = load_recipe_for_diagnostics(path)

    assert missing == ["app_path"]
    assert recipe.steps[0].command == "__MISSING_app_path__"
    assert recipe.environment.variable_hints["app_path"] == "Set this to the local executable path."


def test_preflight_rejects_mutating_actions(tmp_path):
    path = tmp_path / "recipe.yaml"
    path.write_text(
        dedent(
            """
            version: "0.1"
            id: test_recipe
            name: Test
            preflight:
              - action: app.launch
                command: demo.exe
            steps:
              - action: app.launch
                command: demo.exe
            """
        ),
        encoding="utf-8",
    )

    with pytest.raises(RecipeValidationError):
        load_recipe(path)


def test_load_recipe_accepts_overrides(tmp_path):
    path = tmp_path / "recipe.yaml"
    path.write_text(
        dedent(
            """
            version: "0.1"
            id: test_recipe
            name: Test
            variables:
              url: https://example.test
            steps:
              - action: browser.open
                url: "{{ url }}"
            """
        ),
        encoding="utf-8",
    )

    recipe = load_recipe(path, {"url": "https://override.test"})

    assert recipe.variables["url"] == "https://override.test"
    assert recipe.steps[0].url == "https://override.test"


def test_load_recipe_reference_resolves_recipe_id(tmp_path, monkeypatch):
    path = tmp_path / "gaming_mode.yaml"
    path.write_text(
        dedent(
            """
            version: "0.1"
            id: gaming_mode
            name: Gaming Mode
            steps:
              - action: app.launch
                command: demo.exe
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("ritualist.recipe_loader.recipes_dir", lambda: tmp_path)

    recipe = load_recipe_reference("gaming_mode")

    assert recipe.id == "gaming_mode"


def test_unknown_action_is_validation_error(tmp_path):
    path = tmp_path / "recipe.yaml"
    path.write_text(
        dedent(
            """
            version: "0.1"
            id: test_recipe
            name: Test
            steps:
              - action: desktop.click_coordinates
                x: 1
                y: 2
            """
        ),
        encoding="utf-8",
    )

    with pytest.raises(RecipeValidationError):
        load_recipe(path)
