from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from ritualist.agent.picker_controller import PickerController, PickerIntent, PickerIntentKind
from ritualist.agent.picker_model import (
    PICKER_MODEL_SCHEMA_VERSION,
    PickerAction,
    PickerActiveRitual,
    PickerModel,
    PickerRitual,
    PickerRoom,
)


def test_picker_intent_values_are_stable() -> None:
    assert [kind.value for kind in PickerIntentKind] == [
        "select_ritual",
        "open_preflight",
        "browse_all",
        "open_builder",
        "change_room",
        "return_to_active",
    ]


def test_controller_emits_bounded_ritual_and_navigation_intents() -> None:
    model = _model(selected=True, active=True)
    controller = PickerController(model)

    assert controller.select_ritual("gaming_mode").to_dict() == {
        "kind": "select_ritual",
        "recipe_id": "gaming_mode",
        "room_id": "",
    }
    assert controller.open_preflight().kind is PickerIntentKind.OPEN_PREFLIGHT
    assert controller.browse_all().to_dict() == {
        "kind": "browse_all",
        "recipe_id": "",
        "room_id": "",
    }
    assert controller.open_builder().kind is PickerIntentKind.OPEN_BUILDER
    assert controller.change_room("support_desk").room_id == "support_desk"
    assert controller.return_to_active().recipe_id == "gaming_mode"

    assert [event.kind for event in controller.events] == [
        PickerIntentKind.SELECT_RITUAL,
        PickerIntentKind.OPEN_PREFLIGHT,
        PickerIntentKind.BROWSE_ALL,
        PickerIntentKind.OPEN_BUILDER,
        PickerIntentKind.CHANGE_ROOM,
        PickerIntentKind.RETURN_TO_ACTIVE,
    ]


def test_selecting_ritual_never_emits_run_or_execute_intent() -> None:
    event = PickerController(_model(selected=False)).select_ritual("gaming_mode")

    serialized = event.to_dict()
    assert serialized == {
        "kind": "select_ritual",
        "recipe_id": "gaming_mode",
        "room_id": "",
    }
    assert "run" not in serialized["kind"]
    assert "execute" not in serialized["kind"]
    assert set(serialized) == {"kind", "recipe_id", "room_id"}


def test_controller_rejects_unknown_or_unbounded_payloads() -> None:
    controller = PickerController(_model(selected=True, active=False))

    with pytest.raises(ValueError, match="unknown picker ritual"):
        controller.select_ritual("other_recipe")
    with pytest.raises(ValueError, match="safe catalog token"):
        controller.select_ritual("gaming_mode; bad")
    with pytest.raises(ValueError, match="unknown picker room"):
        controller.change_room("home")
    with pytest.raises(ValueError, match="cannot carry a recipe id"):
        PickerIntent(PickerIntentKind.OPEN_BUILDER, recipe_id="gaming_mode")


def test_return_to_active_requires_active_ritual() -> None:
    controller = PickerController(_model(selected=True, active=False))

    with pytest.raises(ValueError, match="no active ritual"):
        controller.return_to_active()


def test_picker_controller_imports_without_gui_windows_or_executor_dependencies() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    code = """
import sys
import ritualist.agent.picker_controller
blocked = ["PySide6", "pywinauto", "win32api", "win32gui", "ritualist.executor"]
loaded = [name for name in blocked if name in sys.modules]
if loaded:
    raise SystemExit(f"picker controller loaded forbidden modules: {loaded}")
"""

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def _model(*, selected: bool, active: bool = False) -> PickerModel:
    room = PickerRoom("gaming", "Gaming Room", current=True, ritual_count=1)
    support = PickerRoom("support_desk", "Support Desk")
    ritual = PickerRitual(
        recipe_id="gaming_mode",
        title="Diablo IV Night",
        subtitle="Review before run",
        description="Prepare a safe gaming setup.",
        room_name="Gaming Room",
        step_count=3,
        affected_apps_count=2,
        intent_summary="Prepare a safe gaming setup.",
        readiness_summary="Compatible",
        setup_summary="2 setup fields",
    )
    active_ritual = (
        PickerActiveRitual(
            recipe_id="gaming_mode",
            title="Diablo IV Night",
            state="running",
            summary="Diablo IV Night is running",
            step_count=3,
        )
        if active
        else None
    )
    return PickerModel(
        schema_version=PICKER_MODEL_SCHEMA_VERSION,
        search_query="",
        current_room=room,
        last_room=None,
        rooms=(room, support),
        recent_rituals=(),
        matching_rituals=(ritual,),
        selected_ritual=ritual if selected else None,
        active_ritual=active_ritual,
        intent_summary="1 ritual available in Gaming Room",
        available_actions=(
            PickerAction("select_ritual", "Select ritual"),
            PickerAction("open_preflight", "Open preflight", enabled=selected),
        ),
    )
