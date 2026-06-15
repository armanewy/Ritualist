from __future__ import annotations

from textwrap import dedent

import pytest

from ritualist.errors import RecipeValidationError
from ritualist.recipe_loader import load_recipe


def test_clicking_play_requires_confirmation(tmp_path):
    path = tmp_path / "unsafe.yaml"
    path.write_text(
        dedent(
            """
            version: "0.1"
            name: Unsafe
            steps:
              - action: desktop.click_text
                text: Play
            """
        ),
        encoding="utf-8",
    )

    with pytest.raises(RecipeValidationError, match="requires_confirmation"):
        load_recipe(path)


def test_clicking_play_with_confirmation_is_valid(tmp_path):
    path = tmp_path / "safe.yaml"
    path.write_text(
        dedent(
            """
            version: "0.1"
            name: Safe
            steps:
              - action: desktop.click_text
                text: Play
                requires_confirmation: true
            """
        ),
        encoding="utf-8",
    )

    recipe = load_recipe(path)

    assert recipe.steps[0].requires_confirmation is True
