from __future__ import annotations

from textwrap import dedent

import pytest

from ritualist.errors import RecipeValidationError
from ritualist.recipe_loader import load_recipe


def test_load_recipe_renders_variables(tmp_path):
    path = tmp_path / "recipe.yaml"
    path.write_text(
        dedent(
            """
            version: "0.1"
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


def test_load_recipe_accepts_overrides(tmp_path):
    path = tmp_path / "recipe.yaml"
    path.write_text(
        dedent(
            """
            version: "0.1"
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


def test_unknown_action_is_validation_error(tmp_path):
    path = tmp_path / "recipe.yaml"
    path.write_text(
        dedent(
            """
            version: "0.1"
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
