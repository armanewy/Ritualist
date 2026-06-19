from __future__ import annotations

import json
import subprocess
import sys
from types import SimpleNamespace
from dataclasses import fields, is_dataclass
from pathlib import Path

import pytest

from setpiece.home import (
    HOME_CATEGORIES,
    HomeCard,
    HomeActivityLog,
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
from setpiece.models import Recipe


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
        "last_run_message",
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


def test_mock_home_cards_accept_requested_count():
    cards = generate_mock_home_cards(count=300)
    model = create_mock_home_model(count=300)

    assert len(cards) == 300
    assert len(model.cards) == 300
    assert len(model.to_qml()["cards"]) == 300


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
    monkeypatch.setattr("setpiece.recipe_loader.recipes_dir", lambda: recipe_dir)

    model = create_installed_home_model(
        run_history_cache=HomeRunHistoryCache(base_dir=tmp_path / "runs")
    )
    card = model.get_card("launcher")

    assert [card.id for card in model.cards] == ["launcher"]
    assert card.title == "Local Launcher"
    assert card.category == "Recipes"
    assert card.subtitle == "Ready to run locally"
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


def test_installed_recipe_description_is_not_reused_as_missing_home_subtitle(tmp_path):
    recipe = Recipe.model_validate(
        {
            "id": "gaming_mode",
            "name": "Gaming Mode",
            "description": "Open a looping video, minimize Chrome, launch Battle.net.",
            "home": {
                "category": "Gaming",
                "card": {
                    "title": "Gaming Mode",
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

    assert card.subtitle == "Ready to run locally"
    assert card.description == "Open a looping video, minimize Chrome, launch Battle.net."


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
                "final_message": "Battle.net path is missing.",
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
    assert card.last_run_message == "Battle.net path is missing."
    assert card.status is HomeCardStatus.FAILED


def test_home_run_history_maps_active_run_substates_to_running(tmp_path):
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
                    "status": "running",
                    "process_id": 123,
                    "process_start_time": 1.0,
                    "current_run_state": "waiting",
                }
            ),
        encoding="utf-8",
    )

    cards = load_installed_home_cards(
        recipe_rows=[(tmp_path / "history_recipe.yaml", recipe, None)],
        run_history_cache=HomeRunHistoryCache(
            base_dir=tmp_path / "runs",
            process_checker=lambda _pid: (True, 1.0),
        ),
    )

    assert cards[0].last_run_status is HomeLastRunStatus.RUNNING
    assert cards[0].status is HomeCardStatus.RUNNING


def test_home_run_history_reconciles_stale_running_runs_before_cards(tmp_path):
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
                "status": "running",
                "process_id": 999999,
                "last_heartbeat_at": "2026-06-15T12:00:00+00:00",
                "last_step_name": "Ask before clicking Play",
            }
        ),
        encoding="utf-8",
    )

    cards = load_installed_home_cards(
        recipe_rows=[(tmp_path / "history_recipe.yaml", recipe, None)],
        run_history_cache=HomeRunHistoryCache(
            base_dir=tmp_path / "runs",
            process_checker=lambda _pid: (False, None),
        ),
    )

    assert cards[0].last_run_status is HomeLastRunStatus.INTERRUPTED
    assert cards[0].status is HomeCardStatus.WARNING


def test_home_run_history_keeps_active_running_runs_running(tmp_path):
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
                "status": "running",
                "process_id": 123,
                "process_start_time": 1.0,
                "current_run_state": "waiting",
                "last_heartbeat_at": "2026-06-15T12:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    cards = load_installed_home_cards(
        recipe_rows=[(tmp_path / "history_recipe.yaml", recipe, None)],
        run_history_cache=HomeRunHistoryCache(
            base_dir=tmp_path / "runs",
            process_checker=lambda _pid: (True, 1.0),
        ),
    )

    assert cards[0].last_run_status is HomeLastRunStatus.RUNNING
    assert cards[0].status is HomeCardStatus.RUNNING


def test_home_card_relative_image_resolves_next_to_recipe(tmp_path, monkeypatch):
    recipe_path = tmp_path / "recipes" / "card_recipe.yaml"
    image_path = recipe_path.parent / "assets" / "card.png"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"not decoded in this test")
    recipe = Recipe.model_validate(
        {
            "id": "card_recipe",
            "name": "Card Recipe",
            "home": {"card": {"image": "assets/card.png"}},
            "steps": [{"action": "app.launch", "command": "demo.exe"}],
        }
    )
    seen: list[Path] = []

    class FakeThumbnailCache:
        def ensure_thumbnail(self, source):
            seen.append(Path(source))
            return SimpleNamespace(thumbnail_url="file:///thumb.png")

    monkeypatch.setattr("setpiece.home.assets.HomeThumbnailCache", FakeThumbnailCache)

    cards = load_installed_home_cards(
        recipe_rows=[(recipe_path, recipe, None)],
        run_history_cache=HomeRunHistoryCache(base_dir=tmp_path / "runs"),
    )

    assert seen == [image_path]
    assert cards[0].image == "file:///thumb.png"


def test_home_card_absolute_image_path_still_resolves(tmp_path, monkeypatch):
    recipe_path = tmp_path / "recipes" / "card_recipe.yaml"
    image_path = tmp_path / "shared" / "card.png"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"not decoded in this test")
    recipe = Recipe.model_validate(
        {
            "id": "card_recipe",
            "name": "Card Recipe",
            "home": {"card": {"image": str(image_path)}},
            "steps": [{"action": "app.launch", "command": "demo.exe"}],
        }
    )
    seen: list[Path] = []

    class FakeThumbnailCache:
        def ensure_thumbnail(self, source):
            seen.append(Path(source))
            return SimpleNamespace(thumbnail_url="file:///absolute-thumb.png")

    monkeypatch.setattr("setpiece.home.assets.HomeThumbnailCache", FakeThumbnailCache)

    cards = load_installed_home_cards(
        recipe_rows=[(recipe_path, recipe, None)],
        run_history_cache=HomeRunHistoryCache(base_dir=tmp_path / "runs"),
    )

    assert seen == [image_path]
    assert cards[0].image == "file:///absolute-thumb.png"


def test_home_card_missing_image_falls_back(tmp_path):
    recipe_path = tmp_path / "recipes" / "card_recipe.yaml"
    recipe_path.parent.mkdir(parents=True)
    recipe = Recipe.model_validate(
        {
            "id": "card_recipe",
            "name": "Card Recipe",
            "home": {"card": {"image": "assets/missing.png"}},
            "steps": [{"action": "app.launch", "command": "demo.exe"}],
        }
    )

    cards = load_installed_home_cards(
        recipe_rows=[(recipe_path, recipe, None)],
        run_history_cache=HomeRunHistoryCache(base_dir=tmp_path / "runs"),
    )

    assert cards[0].image == ""


def test_home_card_imported_pack_asset_path_resolves_safely(tmp_path, monkeypatch):
    pack_root = tmp_path / "imported-packs" / "demo_pack"
    recipe_path = pack_root / "recipe.yaml"
    image_path = pack_root / "assets" / "card.png"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"not decoded in this test")
    recipe = Recipe.model_validate(
        {
            "id": "pack_recipe",
            "name": "Pack Recipe",
            "home": {"card": {"image": "assets/card.png"}},
            "steps": [{"action": "wait.seconds", "seconds": 0.1}],
        }
    )
    seen: list[Path] = []

    class FakeThumbnailCache:
        def ensure_thumbnail(self, source):
            seen.append(Path(source))
            return SimpleNamespace(thumbnail_url="file:///pack-thumb.png")

    monkeypatch.setattr("setpiece.home.assets.HomeThumbnailCache", FakeThumbnailCache)

    cards = load_installed_home_cards(
        recipe_rows=[(recipe_path, recipe, None)],
        run_history_cache=HomeRunHistoryCache(base_dir=tmp_path / "runs"),
    )

    assert seen == [image_path]
    assert cards[0].image == "file:///pack-thumb.png"


def test_home_run_history_cache_keeps_latest_runbook_summary(tmp_path):
    run_dir = tmp_path / "runs" / "20260615T120000Z_history_recipe"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "recipe_id": "history_recipe",
                "recipe_name": "History Recipe",
                "status": "success",
                "final_state": "success",
                "last_step_id": 3,
                "last_step_name": "Verify marker",
                "current_step_state": "success",
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "steps.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "index": 1,
                        "step_name": "Check marker",
                        "action": "assert.file_exists",
                        "status": "success",
                    }
                ),
                json.dumps(
                    {
                        "index": 2,
                        "step_name": "Continue",
                        "action": "wait.for_user",
                        "status": "success",
                    }
                ),
                json.dumps(
                    {
                        "index": 3,
                        "step_name": "Verify marker",
                        "action": "assert.path_exists",
                        "status": "success",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    cache = HomeRunHistoryCache(base_dir=tmp_path / "runs")

    runbook = cache.get_summary("history_recipe")

    assert runbook is not None
    assert runbook.preflight_status == "passed"
    assert runbook.actions_completed == 1
    assert runbook.assertions_passed == 2
    assert runbook.human_prompts_answered == 1
    assert runbook.final_status == "success"
    assert runbook.last_step == "#3 Verify marker (success)"


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
            "last_run_message": "Run completed",
            "description": "Finished without touching the GUI thread.",
        }
    )

    assert finished.status is HomeCardStatus.SUCCESS
    assert finished.last_run_status is HomeLastRunStatus.SUCCESS
    assert finished.last_run_message == "Run completed"
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
    assert model.get_card(card.id).to_qml()["keep_open_active"] is True


def test_home_model_runtime_updates_survive_direct_card_append():
    model = HomeModel(cards=[HomeCard(id="one", title="One", category="Gaming")])
    model.cards.append(HomeCard(id="two", title="Two", category="Gaming"))

    updated = model.apply_runtime_event(
        HomeRuntimeEvent(card_id="two", status=HomeCardStatus.RUNNING, subtitle="Indexed")
    )

    assert updated.id == "two"
    assert updated.status is HomeCardStatus.RUNNING
    assert updated.subtitle == "Indexed"


def test_home_model_rejects_unknown_runtime_event_card_id():
    model = create_mock_home_model()

    with pytest.raises(KeyError):
        model.apply_runtime_event({"card_id": "missing-card", "status": "running"})


def test_home_model_rebuilds_card_index_after_external_card_replacement():
    model = create_mock_home_model()
    original = model.cards[0]
    replacement = HomeCard(id="new-card", title="New Card", category="Gaming")
    model.cards = [replacement, *model.cards[1:]]

    assert model.get_card("new-card") == replacement
    with pytest.raises(KeyError):
        model.get_card(original.id)


def test_home_cards_serialize_to_qml_safe_payloads():
    model = create_mock_home_model()

    payload = model.to_qml()
    cards_payload = _cards_payload(payload)

    assert len(cards_payload) == len(model.cards)
    assert tuple(cards_payload[0]) == _card_field_names()
    assert cards_payload[0] == model.cards[0].to_qml()
    assert isinstance(cards_payload[0]["keep_open_active"], bool)
    assert all(
        isinstance(value, str | bool | int | float)
        for value in cards_payload[0].values()
    )
    json.dumps(payload)


def test_home_activity_log_retains_fast_statuses_without_coalescing():
    activity = HomeActivityLog(max_entries=4)

    for index, status in enumerate(
        [
            HomeCardStatus.RUNNING,
            HomeCardStatus.WARNING,
            HomeCardStatus.SUCCESS,
        ],
        start=1,
    ):
        activity.record(
            HomeRuntimeEvent(
                card_id="gaming_mode",
                status=status,
                subtitle=f"status {index}",
            )
        )

    payload = activity.to_qml()

    assert [entry["subtitle"] for entry in payload] == ["status 3", "status 2", "status 1"]
    assert [entry["status"] for entry in payload] == ["success", "warning", "running"]


def test_home_model_imports_without_gui_or_windows_dependencies():
    repo_root = Path(__file__).resolve().parents[1]
    code = """
import sys
import setpiece.home

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
