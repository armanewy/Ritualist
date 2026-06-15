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
            id: unsafe
            name: Unsafe
            steps:
              - action: desktop.click_text
                text: Play
                window_title_contains: Battle.net
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
            id: safe
            name: Safe
            steps:
              - action: desktop.click_text
                text: Play
                window_title_contains: Battle.net
                requires_confirmation: true
            """
        ),
        encoding="utf-8",
    )

    recipe = load_recipe(path)

    assert recipe.steps[0].requires_confirmation is True


def test_click_text_requires_window_scope(tmp_path):
    path = tmp_path / "unsafe.yaml"
    path.write_text(
        dedent(
            """
            version: "0.1"
            id: unsafe
            name: Unsafe
            steps:
              - action: desktop.click_text
                text: Diablo IV
            """
        ),
        encoding="utf-8",
    )

    with pytest.raises(RecipeValidationError, match="window_title_contains"):
        load_recipe(path)


def test_recipe_id_must_be_safe(tmp_path):
    path = tmp_path / "unsafe.yaml"
    path.write_text(
        dedent(
            """
            version: "0.1"
            id: ../unsafe
            name: Unsafe
            steps:
              - action: app.launch
                command: demo.exe
            """
        ),
        encoding="utf-8",
    )

    with pytest.raises(RecipeValidationError, match="safe filename-like"):
        load_recipe(path)
