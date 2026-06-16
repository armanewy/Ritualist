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
    HomeLastRunStatus,
    HomeRuntimeEvent,
    create_mock_home_model,
    generate_mock_home_cards,
)


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
        "accent",
        "image",
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
