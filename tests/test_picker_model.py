from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from setpiece.activity_journal import JournalEvent
from setpiece.agent.models import AgentRunState, AgentState, AgentStep
from setpiece.agent.picker_model import HERO_ROOM_NAMES, build_picker_model
from setpiece.recipe_loader import load_recipe


def test_picker_uses_exact_hero_rooms_and_current_room_filter(tmp_path: Path) -> None:
    rows = [
        _recipe_row(tmp_path, "gaming_mode", "Gaming Mode", "Gaming", "Diablo IV Night"),
        _recipe_row(tmp_path, "coding_mode", "Coding Mode", "Coding", "Coding Mode"),
        _recipe_row(tmp_path, "support_triage", "Support Triage", "Support Desk", "Support Triage"),
    ]

    model = build_picker_model(
        current_room="support_desk",
        last_room="Gaming Room",
        recipe_rows=rows,
        recent_run_records=[],
        activity_events=[],
        transparency_provider=_transparency,
        doctor_provider=_doctor,
    )

    assert [room.name for room in model.rooms] == list(HERO_ROOM_NAMES)
    assert model.current_room is not None
    assert model.current_room.name == "Support Desk"
    assert model.last_room is not None
    assert model.last_room.name == "Gaming Room"
    assert [ritual.title for ritual in model.matching_rituals] == ["Support Triage"]
    assert "Home" not in model.intent_summary


def test_picker_exposes_recent_five_distinct_rituals_from_runs_and_activity(tmp_path: Path) -> None:
    rows = [
        _recipe_row(tmp_path, f"recipe_{index}", f"Recipe {index}", "Coding", f"Recipe {index}")
        for index in range(1, 8)
    ]
    records = [
        {"metadata": {"recipe_id": "recipe_3"}},
        {"metadata": {"recipe_id": "recipe_1"}},
        {"metadata": {"recipe_id": "recipe_3"}},
        {"metadata": {"recipe_id": "recipe_2"}},
    ]
    events = [
        JournalEvent("recipe_dry_run", {"recipe_id": "recipe_4"}),
        JournalEvent("recipe_run_finished", {"recipe_id": "recipe_5"}),
        JournalEvent("recipe_run_finished", {"recipe_id": "recipe_6"}),
    ]

    model = build_picker_model(
        current_room="project",
        recipe_rows=rows,
        recent_run_records=records,
        activity_events=events,
        transparency_provider=_transparency,
        doctor_provider=_doctor,
    )

    assert [ritual.recipe_id for ritual in model.recent_rituals] == [
        "recipe_3",
        "recipe_1",
        "recipe_2",
        "recipe_4",
        "recipe_5",
    ]
    assert model.recent_rituals[0].recent_summary == "Most recent ritual"


def test_picker_summaries_use_transparency_doctor_and_display_names(tmp_path: Path) -> None:
    rows = [
        _recipe_row(
            tmp_path,
            "gaming_mode",
            "Gaming Mode",
            "Gaming",
            "Diablo IV Night",
            description="Prepare the game workspace.",
        )
    ]

    model = build_picker_model(
        current_room="gaming",
        search_query="diablo",
        selected_ritual_id="gaming_mode",
        recipe_rows=rows,
        recent_run_records=[],
        activity_events=[],
        transparency_provider=_transparency,
        doctor_provider=lambda _recipe: {
            "compatibility": {
                "status": "compatible_with_warnings",
                "errors_count": 0,
                "warnings_count": 1,
            }
        },
    )

    ritual = model.selected_ritual
    assert ritual is not None
    assert ritual.title == "Diablo IV Night"
    assert ritual.step_count == 2
    assert ritual.affected_apps_count == 1
    assert ritual.intent_summary == "Prepare the game workspace."
    assert ritual.readiness_summary == "Ready with 1 warning"
    assert ritual.setup_summary == "2 setup fields, 1 overridden"

    display_text = " ".join(
        [
            ritual.title,
            ritual.subtitle,
            ritual.description,
            ritual.intent_summary,
            ritual.readiness_summary,
            ritual.setup_summary,
            ritual.room_name,
        ]
    )
    assert "gaming_mode" not in display_text
    assert model.intent_summary == '1 ritual match "diablo" in Gaming Room'


def test_picker_active_ritual_supports_return_without_starting_anything(tmp_path: Path) -> None:
    rows = [
        _recipe_row(tmp_path, "coding_mode", "Coding Mode", "Coding", "Coding Mode"),
    ]
    active = AgentState(
        state=AgentRunState.RUNNING,
        active_ritual_id="coding_mode",
        active_ritual_name="Coding Mode",
        current_step=AgentStep(index=1, name="Open project", action="app.launch", state="running"),
        step_count=2,
    )

    model = build_picker_model(
        current_room="project",
        recipe_rows=rows,
        recent_run_records=[],
        activity_events=[],
        active_state=active,
        transparency_provider=_transparency,
        doctor_provider=_doctor,
    )

    assert model.active_ritual is not None
    assert model.active_ritual.summary == "Coding Mode is running: Open project"
    assert model.matching_rituals[0].active_summary == "Coding Mode is running: Open project"
    actions = {action.action: action.enabled for action in model.available_actions}
    assert actions["return_to_active"] is True
    assert actions["open_preflight"] is False


def _recipe_row(
    tmp_path: Path,
    recipe_id: str,
    name: str,
    category: str,
    title: str,
    *,
    description: str | None = None,
):
    path = tmp_path / f"{recipe_id}.yaml"
    path.write_text(
        dedent(
            f"""
            version: "0.1"
            id: {recipe_id}
            name: {name}
            description: {description or f"Open {name} safely."}
            home:
              category: {category}
              card:
                title: {title}
                subtitle: Review before run
            steps:
              - name: Confirm
                action: confirm.ask
                prompt: Review this ritual?
              - name: Open app
                action: app.launch
                command: demo.exe
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    return (path, load_recipe(path), None)


def _transparency(_path, recipe):
    return {
        "plain_language_plan": [f"Purpose: {recipe.description}"],
        "setup_fields": [
            {"name": "safe_path", "label": "Safe path", "editable": True, "overridden": True},
            {"name": "browser", "label": "Browser", "editable": True, "overridden": False},
        ],
    }


def _doctor(_recipe):
    return {
        "compatibility": {
            "status": "compatible",
            "errors_count": 0,
            "warnings_count": 0,
        }
    }
