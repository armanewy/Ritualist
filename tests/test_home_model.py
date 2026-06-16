from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import fields, is_dataclass
from pathlib import Path

import pytest

from ritualist.home import (
    HOME_CATEGORIES,
    HomeCard,
    HomeCardStatus,
    HomeDoctorStatus,
    HomeLastRunStatus,
    HomeModel,
    HomeRuntimeEvent,
    HomeRunHistoryCache,
    create_installed_home_model,
    create_mock_home_model,
    generate_mock_home_cards,
    load_installed_home_cards,
)
from ritualist.models import Recipe


def _card_field_names() -> tuple[str, ...]:
    if hasattr(HomeCard, "model_fields"):
        return tuple(HomeCard.model_fields)
    if is_dataclass(HomeCard):
        return tuple(field.name for field in fields(HomeCard))
    raise TypeError("HomeCard must expose dataclass fields or Pydantic model_fields")


def _category_labels() -> tuple[str, ...]:
    return tuple(getattr(category, "label", str(category)) for category in HOME_CATEGORIES)


def _cards_payload(payload):
    if isinstance(payload, dict):
        return payload["cards"]
    return payload


def test_home_card_fields_are_stable_for_qml_bridge():
    assert _card_field_names() == (
        "id",
        "title",
        "category",
        "subtitle",
        "description",
        "status",
        "last_run_status",
        "doctor_status",
        "accent",
        "image",
        "wait_action",
        "wait_target",
        "wait_started_at",
        "wait_elapsed_seconds",
        "wait_timeout_seconds",
        "keep_open_active",
    )


def test_mock_home_cards_generate_at_least_100_cards():
    cards = generate_mock_home_cards()

    assert len(cards) >= 100
    assert len({card.id for card in cards}) == len(cards)


def test_mock_home_cards_assign_all_required_categories():
    cards = generate_mock_home_cards()
    categories = {card.category for card in cards}

    assert _category_labels() == (
        "Gaming",
        "Media",
        "Coding",
        "News",
        "Helpdesk",
        "Settings",
    )
    assert categories == set(_category_labels())
    assert all(card.category in _category_labels() for card in cards)


def test_home_model_uses_custom_categories():
    model = create_mock_home_model(("Launchers", "Media"))

    payload = model.to_qml()

    assert [category["label"] for category in payload["categories"]] == ["Launchers", "Media"]
    assert {card.category for card in model.cards} == {"Launchers", "Media"}


def test_home_model_appends_unknown_card_category():
    model = HomeModel(
        categories=("Gaming", "Media"),
        cards=[
            HomeCard(
                id="local-admin",
                title="Local Admin",
                category="Local Admin",
            )
        ],
    )

    payload = model.to_qml()

    assert [category["label"] for category in payload["categories"]] == [
        "Gaming",
        "Media",
        "Local Admin",
    ]
    assert payload["cards"][0]["category"] == "Local Admin"


def test_home_model_routes_blank_card_category_to_other():
    model = HomeModel(
        categories=("Gaming",),
        cards=[
            HomeCard(
                id="uncategorized",
                title="Uncategorized",
                category=" ",
            )
        ],
    )

    payload = model.to_qml()

    assert [category["label"] for category in payload["categories"]] == ["Gaming", "Other"]
    assert payload["cards"][0]["category"] == "Other"


def test_installed_recipes_become_home_cards(tmp_path, monkeypatch):
    recipe_dir = tmp_path / "recipes"
    recipe_dir.mkdir()
    (recipe_dir / "launcher.yaml").write_text(
        """
version: "0.1"
id: launcher
name: Local Launcher
description: Starts a local launcher.
steps:
  - action: app.launch
    command: demo.exe
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr("ritualist.recipe_loader.recipes_dir", lambda: recipe_dir)

    model = create_installed_home_model(
        run_history_cache=HomeRunHistoryCache(base_dir=tmp_path / "runs")
    )
    card = model.get_card("launcher")

    assert [card.id for card in model.cards] == ["launcher"]
    assert card.title == "Local Launcher"
    assert card.category == "Recipes"
    assert card.subtitle == "Starts a local launcher."
    assert card.description == "Starts a local launcher."
    assert card.doctor_status is HomeDoctorStatus.NOT_CHECKED
    assert [category["label"] for category in model.to_qml()["categories"]] == [
        "Gaming",
        "Media",
        "Coding",
        "News",
        "Helpdesk",
        "Settings",
        "Recipes",
    ]


def test_installed_recipe_home_metadata_controls_card(tmp_path):
    recipe = Recipe.model_validate(
        {
            "id": "gaming_mode",
            "name": "Gaming Mode",
            "description": "Fallback description",
            "home": {
                "category": "Gaming",
                "card": {
                    "title": "Diablo IV Night",
                    "subtitle": "YouTube ambience + Battle.net",
                    "accent": "#6aa9ff",
                    "image": "",
                },
            },
            "steps": [{"action": "app.launch", "command": "demo.exe"}],
        }
    )

    cards = load_installed_home_cards(
        recipe_rows=[(tmp_path / "gaming_mode.yaml", recipe, None)],
        run_history_cache=HomeRunHistoryCache(base_dir=tmp_path / "runs"),
    )
    card = cards[0]

    assert card.id == "gaming_mode"
    assert card.title == "Diablo IV Night"
    assert card.category == "Gaming"
    assert card.subtitle == "YouTube ambience + Battle.net"
    assert card.description == "Fallback description"
    assert card.accent == "#6aa9ff"
    assert card.image == ""


def test_installed_recipe_missing_metadata_uses_home_defaults(tmp_path):
    recipe = Recipe.model_validate(
        {
            "id": "bare_recipe",
            "name": "Bare Recipe",
            "steps": [{"action": "app.launch", "command": "demo.exe"}],
        }
    )

    cards = load_installed_home_cards(
        recipe_rows=[(tmp_path / "bare_recipe.yaml", recipe, None)],
        run_history_cache=HomeRunHistoryCache(base_dir=tmp_path / "runs"),
    )
    card = cards[0]

    assert card.id == "bare_recipe"
    assert card.title == "Bare Recipe"
    assert card.category == "Recipes"
    assert card.subtitle == "Ready to run locally"
    assert card.description == "No description provided."
    assert card.status is HomeCardStatus.READY
    assert card.last_run_status is HomeLastRunStatus.NONE
    assert card.doctor_status is HomeDoctorStatus.NOT_CHECKED


def test_installed_recipe_card_includes_cached_last_run_status(tmp_path):
    recipe = Recipe.model_validate(
        {
            "id": "history_recipe",
            "name": "History Recipe",
            "steps": [{"action": "app.launch", "command": "demo.exe"}],
        }
    )
    run_dir = tmp_path / "runs" / "20260615T120000Z_history_recipe"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "recipe_id": "history_recipe",
                "recipe_name": "History Recipe",
                "status": "stopped",
                "final_state": "failed",
            }
        ),
        encoding="utf-8",
    )

    cache = HomeRunHistoryCache(base_dir=tmp_path / "runs")
    cards = load_installed_home_cards(
        recipe_rows=[(tmp_path / "history_recipe.yaml", recipe, None)],
        run_history_cache=cache,
    )
    card = cards[0]

    assert card.last_run_status is HomeLastRunStatus.FAILED
    assert card.status is HomeCardStatus.FAILED


def test_home_model_updates_card_from_runtime_event():
    model = create_mock_home_model()
    card = model.cards[0]

    updated = model.apply_runtime_event(
        HomeRuntimeEvent(
            card_id=card.id,
            status=HomeCardStatus.RUNNING,
            subtitle="Running local workflow",
        )
    )

    assert updated.id == card.id
    assert updated.status is HomeCardStatus.RUNNING
    assert updated.subtitle == "Running local workflow"
    assert model.get_card(card.id) == updated

    finished = model.apply_runtime_event(
        {
            "card_id": card.id,
            "status": "success",
            "last_run_status": "success",
            "description": "Finished without touching the GUI thread.",
        }
    )

    assert finished.status is HomeCardStatus.SUCCESS
    assert finished.last_run_status is HomeLastRunStatus.SUCCESS
    assert finished.description == "Finished without touching the GUI thread."


def test_home_model_updates_wait_and_keep_open_state():
    model = create_mock_home_model()
    card = model.cards[0]

    waiting = model.apply_runtime_event(
        HomeRuntimeEvent(
            card_id=card.id,
            status=HomeCardStatus.RUNNING,
            wait_action="wait.for_window",
            wait_target="window Battle.net",
            wait_started_at="2026-06-15T12:00:00+00:00",
            wait_elapsed_seconds="3",
            wait_timeout_seconds="30",
        )
    )

    assert waiting.wait_action == "wait.for_window"
    assert waiting.wait_target == "window Battle.net"
    assert waiting.wait_elapsed_seconds == "3"
    assert waiting.wait_timeout_seconds == "30"

    keep_open = model.apply_runtime_event(
        {"card_id": card.id, "keep_open_active": True, "wait_action": "", "wait_target": ""}
    )

    assert keep_open.keep_open_active is True
    assert keep_open.wait_action == ""
    assert keep_open.wait_target == ""
    assert model.get_card(card.id).to_qml()["keep_open_active"] == "true"


def test_home_model_rejects_unknown_runtime_event_card_id():
    model = create_mock_home_model()

    with pytest.raises(KeyError):
        model.apply_runtime_event({"card_id": "missing-card", "status": "running"})


def test_home_cards_serialize_to_qml_safe_payloads():
    model = create_mock_home_model()

    payload = model.to_qml()
    cards_payload = _cards_payload(payload)

    assert len(cards_payload) == len(model.cards)
    assert tuple(cards_payload[0]) == _card_field_names()
    assert cards_payload[0] == model.cards[0].to_qml()
    assert all(isinstance(value, str) for value in cards_payload[0].values())
    json.dumps(payload)


def test_home_model_imports_without_gui_or_windows_dependencies():
    repo_root = Path(__file__).resolve().parents[1]
    code = """
import sys
import ritualist.home

blocked = ["PySide6", "pywinauto", "win32api", "win32gui", "win32con"]
loaded = [name for name in blocked if name in sys.modules]
if loaded:
    raise SystemExit(f"home model loaded GUI/Windows modules: {loaded}")
"""

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
