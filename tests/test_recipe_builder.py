from __future__ import annotations

from textwrap import dedent

import pytest
import yaml

from setpiece.errors import RecipeValidationError
from setpiece.recipe_builder import RecipeBuilder
from setpiece.recipe_loader import load_recipe


def test_builder_creates_edits_and_saves_recipe(tmp_path):
    path = tmp_path / "focus.yaml"
    builder = RecipeBuilder.create("focus_mode", "Focus Mode")

    builder.update_metadata(
        name="Deep Focus",
        description="Open the focus workspace.",
        variables={"notes_path": "notes.exe"},
        home={
            "category": "Work",
            "card": {
                "title": "Deep Focus",
                "subtitle": "Notes and timer",
                "image": "",
                "accent": "#6aa9ff",
            },
        },
    )
    builder.add_step({"name": "Open notes", "action": "app.launch", "command": "{{ notes_path }}"})

    recipe = builder.save(path)
    loaded = load_recipe(path)

    assert recipe.id == "focus_mode"
    assert loaded.name == "Deep Focus"
    assert loaded.description == "Open the focus workspace."
    assert loaded.home.category == "Work"
    assert loaded.steps[0].command == "notes.exe"


def test_builder_reorders_and_deletes_steps():
    builder = RecipeBuilder.create("demo", "Demo")
    builder.add_step({"name": "First", "action": "wait.seconds", "seconds": 1})
    builder.add_step({"name": "Second", "action": "wait.seconds", "seconds": 2})
    builder.add_step({"name": "Third", "action": "wait.seconds", "seconds": 3})

    builder.reorder_step(0, 2)
    removed = builder.delete_step(1)

    assert removed["name"] == "Third"
    assert [step["name"] for step in builder.steps] == ["Second", "First"]
    assert [step.seconds for step in builder.validate().steps] == [2, 1]


def test_builder_can_insert_step_at_index():
    builder = RecipeBuilder.create("demo", "Demo")
    builder.add_step({"name": "First", "action": "wait.seconds", "seconds": 1})
    inserted = builder.add_step({"name": "Before first", "action": "wait.seconds", "seconds": 0.5}, 0)

    assert inserted == 0
    assert [step["name"] for step in builder.steps] == ["Before first", "First"]


def test_builder_save_validates_before_writing(tmp_path):
    path = tmp_path / "unsafe.yaml"
    builder = RecipeBuilder.create("unsafe", "Unsafe")
    builder.add_step(
        {
            "action": "desktop.click_text",
            "text": "Play",
            "window_title_contains": "Battle.net",
        }
    )

    with pytest.raises(RecipeValidationError, match="requires_confirmation"):
        builder.save(path)

    assert not path.exists()


def test_builder_from_path_preserves_power_user_yaml_shape(tmp_path):
    path = tmp_path / "recipe.yaml"
    path.write_text(
        dedent(
            """
            version: "0.1"
            id: demo
            name: Demo
            variables:
              app_path: demo.exe
            steps:
              - action: app.launch
                command: "{{ app_path }}"
            """
        ),
        encoding="utf-8",
    )
    builder = RecipeBuilder.from_path(path)

    builder.update_metadata(name="Edited Demo")
    builder.add_step({"action": "wait.seconds", "seconds": 1})
    builder.save(path)
    saved = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert saved["variables"]["app_path"] == "demo.exe"
    assert saved["steps"][0]["command"] == "{{ app_path }}"
    assert load_recipe(path).name == "Edited Demo"
