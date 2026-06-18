from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from ritualist.agent.models import AgentNotificationRoute, AgentRunState, AgentState
from ritualist.agent.state import apply_ritual_state, apply_runtime_event, initial_agent_state
from ritualist.runtime_models import (
    ConfirmationRequested,
    Heartbeat,
    RunFinished,
    RunStarted,
    RunState,
    StepFinished,
    StepPaused,
    StepState,
    StepWaiting,
)


FIXED_TIME = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)


def test_agent_state_values_cover_quiet_instrument_states() -> None:
    assert [state.value for state in AgentRunState] == [
        "idle",
        "ready",
        "preflight",
        "running",
        "waiting",
        "confirmation",
        "paused",
        "failure",
        "recovery",
        "completed",
        "stopped",
        "interrupted",
    ]


def test_initial_agent_state_is_ipc_serializable() -> None:
    state = initial_agent_state(room={"id": "gaming", "name": "Gaming Room", "canvas_id": "gaming_desktop"})

    payload = state.to_ipc_payload()
    restored = AgentState.model_validate_json(state.model_dump_json())

    assert payload["schema_version"] == "ritualist.agent.state.v1"
    assert payload["state"] == "idle"
    assert payload["room"]["name"] == "Gaming Room"
    assert restored == state


def test_runtime_events_project_to_resident_agent_state() -> None:
    state = initial_agent_state()
    state = apply_runtime_event(
        state,
        RunStarted(
            run_id="run-1",
            sequence=0,
            occurred_at=FIXED_TIME,
            recipe_id="gaming_mode",
            recipe_name="Gaming Mode",
            steps_total=3,
        ),
    )
    state = apply_runtime_event(
        state,
        StepWaiting(
            run_id="run-1",
            sequence=1,
            step_index=1,
            step_name="Wait for launcher",
            action="window.wait",
            reason="waiting",
            target="launcher",
            elapsed_seconds=2,
            timeout_seconds=30,
            started_at=FIXED_TIME,
        ),
    )
    state = apply_runtime_event(
        state,
        ConfirmationRequested(
            run_id="run-1",
            sequence=2,
            confirmation_id="confirm-1",
            step_index=2,
            step_name="Click Play",
            action="desktop.click_text",
            prompt="Click Play?",
            target="Play",
            target_type="text",
        ),
    )
    state = apply_runtime_event(
        state,
        StepPaused(
            run_id="run-1",
            sequence=3,
            step_index=2,
            step_name="Click Play",
            action="desktop.click_text",
            reason="user pause",
        ),
    )

    assert state.state == AgentRunState.PAUSED
    assert state.active_ritual_id == "gaming_mode"
    assert state.active_ritual_name == "Gaming Mode"
    assert state.step_count == 3
    assert state.wait is not None
    assert state.wait.target == "launcher"
    assert state.pending_confirmation is not None
    assert state.pending_confirmation.target == "Play"
    assert state.current_step is not None
    assert state.current_step.state == "paused"
    assert state.tray_tooltip == "Ritualist - Paused: Gaming Mode"


def test_failure_and_interrupted_events_capture_review_and_recovery_state() -> None:
    state = apply_runtime_event(
        initial_agent_state(),
        RunStarted(
            run_id="run-1",
            sequence=0,
            recipe_id="support_triage_workspace",
            recipe_name="Support Triage",
            steps_total=2,
        ),
    )
    state = apply_runtime_event(
        state,
        StepFinished(
            run_id="run-1",
            sequence=1,
            step_index=2,
            step_name="Launch app",
            action="app.launch",
            state=StepState.FAILED,
            message="launcher failed with token=secret",
        ),
    )

    payload = json.dumps(state.to_ipc_payload())
    assert state.state == AgentRunState.FAILURE
    assert state.latest_failure is not None
    assert state.latest_failure.message == "launcher failed with token=[redacted]"
    assert state.notification_recommendation.route == AgentNotificationRoute.OPEN_REVIEW
    assert "token=secret" not in payload

    state = apply_runtime_event(
        state,
        RunFinished(
            run_id="run-1",
            sequence=2,
            state=RunState.INTERRUPTED,
            success=False,
            message="Ritualist exited before finalizing this run.",
        ),
    )

    assert state.state == AgentRunState.INTERRUPTED
    assert state.recovery_checkpoint is not None
    assert state.recovery_checkpoint.safe_next_actions == ("inspect_run", "doctor", "start_fresh")


def test_heartbeat_waiting_state_keeps_wait_timing() -> None:
    state = apply_runtime_event(
        initial_agent_state(),
        Heartbeat(
            run_id="run-1",
            sequence=0,
            run_state=RunState.WAITING,
            step_index=1,
            step_name="Wait for title",
            action="window.wait",
            step_state=StepState.WAITING,
            wait_target="Game Window",
            wait_started_at=FIXED_TIME,
            wait_elapsed_seconds=5,
            wait_timeout_seconds=60,
        ),
    )

    assert state.state == AgentRunState.WAITING
    assert state.wait is not None
    assert state.wait.elapsed_seconds == 5
    assert state.wait.timeout_seconds == 60
    assert state.notification_recommendation.route == AgentNotificationRoute.OPEN_INSTRUMENT


def test_ritual_state_projection_consumes_canvas_contract_without_executor_duplication() -> None:
    state = apply_ritual_state(
        initial_agent_state(),
        {
            "recipe_id": "project_setup",
            "active_run": {
                "run_id": "run-2",
                "state": "confirming",
                "steps_total": 4,
                "current_step": {
                    "index": 3,
                    "name": "Confirm editor launch",
                    "action": "app.launch",
                    "state": "confirming",
                },
                "confirmation": {
                    "required": True,
                    "step_index": 3,
                    "step_name": "Confirm editor launch",
                    "action": "app.launch",
                    "target": "Editor",
                    "target_type": "app",
                    "message": "Launch editor?",
                },
            },
            "recovery": {"interrupted": False},
        },
        room={"id": "project", "name": "Project Room", "canvas_id": "project_room"},
    )

    assert state.state == AgentRunState.CONFIRMATION
    assert state.active_ritual_id == "project_setup"
    assert state.room is not None
    assert state.room.name == "Project Room"
    assert state.pending_confirmation is not None
    assert state.pending_confirmation.prompt == "Launch editor?"


def test_ritual_state_interrupted_recovery_maps_to_recovery_checkpoint() -> None:
    state = apply_ritual_state(
        initial_agent_state(),
        {
            "recipe_id": "gaming_mode",
            "active_run": {"run_id": "run-3", "state": "idle"},
            "last_run": {"state": "interrupted", "last_step": "Click Play"},
            "recovery": {
                "interrupted": True,
                "repaired_status": "interrupted",
                "safe_next_actions": ["inspect_run", "doctor", "start_fresh"],
            },
        },
    )

    assert state.state == AgentRunState.RECOVERY
    assert state.recovery_checkpoint is not None
    assert state.recovery_checkpoint.interrupted is True
    assert state.notification_recommendation.route == AgentNotificationRoute.OPEN_REVIEW


def test_agent_modules_import_without_gui_or_windows_dependencies() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    code = """
import sys
import ritualist.agent.models
import ritualist.agent.state
import ritualist.agent.run_coordinator

blocked = ["PySide6", "pywinauto", "win32api", "win32gui", "win32con"]
loaded = [name for name in blocked if name in sys.modules]
if loaded:
    raise SystemExit(f"agent modules loaded GUI/Windows modules: {loaded}")
"""

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
