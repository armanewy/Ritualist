from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from setpiece.agent.instrument_model import build_instrument_model
from setpiece.agent.instrument_presenter import (
    PresentedInstrument,
    build_instrument_presentation,
    present_instrument,
)
from setpiece.agent.models import AgentConfirmation, AgentRunState, AgentState, AgentStep


def test_presenter_groups_ready_overview_and_primary_actions() -> None:
    presentation = build_instrument_presentation(
        agent_state=AgentState(
            state=AgentRunState.READY,
            active_ritual_id="gaming_mode",
            active_ritual_name="Gaming Mode",
            step_count=2,
        ),
        recipe_transparency={
            "purpose": "Prepare the game workspace.",
            "affected_apps": ("Battle.net",),
            "setup_fields": ({"label": "Target game", "editable": True},),
            "confirmations": ({"name": "Confirm Play"},),
        },
        dry_run={"confirmation_count": 1},
    )

    assert isinstance(presentation, PresentedInstrument)
    assert presentation.title == "Ready"
    assert [action.label for action in presentation.primary_actions] == ["Start ritual"]
    assert [section.title for section in presentation.sections] == ["Overview"]
    overview = presentation.sections[0]
    rows = {row.label: row.text for row in overview.rows}
    assert rows["Intent"] == "Prepare the game workspace."
    assert rows["Affected apps/settings"] == "App: Battle.net; Setup: Target game"


def test_presenter_shows_running_state_without_fake_percentage() -> None:
    model = build_instrument_model(
        agent_state=AgentState(
            state=AgentRunState.RUNNING,
            active_ritual_id="coding_mode",
            active_ritual_name="Coding Mode",
            current_step=AgentStep(
                index=1,
                name="Open editor",
                action="wait.for_window",
                state="running",
            ),
            step_count=2,
        ),
        ritual_state={
            "recipe_id": "coding_mode",
            "active_run": {
                "state": "running",
                "elapsed_seconds": 9,
                "current_step": {
                    "index": 1,
                    "name": "Open editor",
                    "action": "wait.for_window",
                    "safe_to_pause": True,
                },
            },
        },
        recipe_transparency={
            "ordered_steps": (
                {"index": 1, "name": "Open editor", "summary": "Open editor"},
                {"index": 2, "name": "Arrange windows", "summary": "Arrange windows"},
            )
        },
    )

    presentation = present_instrument(model)
    running = presentation.sections[1]
    rows = {row.label: row.text for row in running.rows}

    assert presentation.title == "Open editor"
    assert rows["Step"] == "1 of 2"
    assert rows["Elapsed"] == "9s"
    assert rows["Next"] == "Arrange windows"
    assert "percentage" not in str(presentation.to_dict()).casefold()
    assert [action.label for action in presentation.secondary_actions] == ["Pause", "Stop"]


def test_presenter_confirmation_uses_safe_title_and_explicit_gate_actions() -> None:
    presentation = build_instrument_presentation(
        agent_state=AgentState(
            state=AgentRunState.CONFIRMATION,
            active_ritual_id="gaming_mode",
            pending_confirmation=AgentConfirmation(
                confirmation_id="c1",
                step_index=3,
                step_name="Confirm Play",
                action="desktop.click_text",
                prompt="desktop.click_text will press Play. Continue?",
                target="#play > button",
                target_type="selector",
            ),
            step_count=3,
        ),
        ritual_state={
            "recipe_id": "gaming_mode",
            "active_run": {
                "state": "confirming",
                "confirmation": {"required": True, "remember_eligible": False},
            },
        },
    )

    assert "desktop.click_text" not in presentation.title
    assert "selected control" in presentation.title
    assert [action.label for action in presentation.primary_actions] == ["Approve once"]
    assert [action.label for action in presentation.secondary_actions] == ["Cancel safely"]
    confirmation = presentation.sections[1]
    rows = {row.label: row.text for row in confirmation.rows}
    assert rows["Target"] == "#play > button"
    assert rows["Safe negative path"].startswith("Cancel stops before this action")


def test_presenter_failure_surfaces_open_logs_and_remedy() -> None:
    presentation = build_instrument_presentation(
        agent_state=AgentState(
            state=AgentRunState.FAILURE,
            active_ritual_id="support_triage",
            current_step=AgentStep(
                index=2,
                name="Collect diagnostics",
                action="diagnostics.collect",
                state="failed",
                message="access denied",
            ),
            step_count=3,
        ),
        ritual_state={
            "recipe_id": "support_triage",
            "active_run": {"state": "failed", "message": "access denied"},
            "last_run": {
                "state": "failed",
                "steps_completed": 1,
                "not_run_count": 1,
                "run_log_path": "C:/runs/support",
            },
        },
        doctor={"errors": ("Grant access to the diagnostics folder.",)},
    )

    assert presentation.title == "Collect diagnostics failed"
    assert [action.label for action in presentation.primary_actions] == ["Open logs"]
    failure = presentation.sections[1]
    rows = {row.label: row.text for row in failure.rows}
    assert rows["Cause"] == "access denied"
    assert rows["Remedy"] == "Grant access to the diagnostics folder."
    assert rows["Run log"] == "C:/runs/support"


def test_presenter_keeps_interruption_history_compact_until_explicitly_opened() -> None:
    compact = build_instrument_presentation(
        agent_state=AgentState(state=AgentRunState.RECOVERY, active_ritual_id="gaming_mode"),
        ritual_state=_interrupted_state(),
    )
    opened = build_instrument_presentation(
        agent_state=AgentState(state=AgentRunState.RECOVERY, active_ritual_id="gaming_mode"),
        ritual_state=_interrupted_state(),
        show_history=True,
    )

    assert compact.compact_history is True
    assert compact.sections[-1].title == "History"
    assert compact.sections[-1].collapsed is True
    assert [row.label for row in compact.sections[-1].rows] == ["Interrupted run"]
    assert opened.compact_history is False
    assert opened.sections[-1].collapsed is False
    assert [row.text for row in opened.sections[-1].rows] == [
        "Setpiece exited before finalizing this run.",
        "Step 1: Open launcher (success)",
        "Step 2: Wait for Play (waiting)",
    ]


def test_instrument_modules_import_without_gui_or_windows_dependencies() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    code = """
import sys
import setpiece.agent.instrument_model
import setpiece.agent.instrument_presenter

blocked = ["PySide6", "pywinauto", "win32api", "win32gui", "win32con"]
loaded = [name for name in blocked if name in sys.modules]
if loaded:
    raise SystemExit(f"instrument modules loaded GUI/Windows modules: {loaded}")
"""

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def _interrupted_state() -> dict[str, object]:
    return {
        "recipe_id": "gaming_mode",
        "last_run": {
            "state": "interrupted",
            "final_message": "Setpiece exited before finalizing this run.",
            "run_log_path": "C:/runs/run-2",
            "step_summaries": (
                {"index": 1, "name": "Open launcher", "state": "success"},
                {"index": 2, "name": "Wait for Play", "state": "waiting"},
            ),
        },
        "recovery": {
            "interrupted": True,
            "repaired_status": "interrupted",
            "safe_next_actions": ("inspect_run", "doctor", "start_fresh"),
        },
    }
