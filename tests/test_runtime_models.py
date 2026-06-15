from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from ritualist.runtime_models import (
    RUNTIME_EVENT_TYPES,
    ConfirmationRequested,
    ConfirmationResolved,
    Heartbeat,
    LogMessage,
    RunFinished,
    RunStarted,
    RunState,
    RunStateChanged,
    RuntimeEvent,
    StepFinished,
    StepPaused,
    StepResumed,
    StepStarted,
    StepState,
    StepWaiting,
)


FIXED_TIME = datetime(2026, 6, 15, 22, 0, tzinfo=timezone.utc)
EVENT_ADAPTER = TypeAdapter(RuntimeEvent)


def test_run_state_values_are_stable():
    assert [state.value for state in RunState] == [
        "idle",
        "running",
        "waiting",
        "paused",
        "confirming",
        "stopping",
        "success",
        "stopped",
        "failed",
        "interrupted",
    ]


def test_step_state_values_are_stable():
    assert [state.value for state in StepState] == [
        "pending",
        "running",
        "waiting",
        "paused",
        "confirming",
        "success",
        "failed",
        "cancelled",
        "skipped",
    ]


def test_run_started_serializes_to_stable_payload():
    event = RunStarted(
        run_id="run-1",
        sequence=0,
        occurred_at=FIXED_TIME,
        recipe_id="demo",
        recipe_name="Demo",
        steps_total=2,
    )

    expected = {
        "type": "run.started",
        "run_id": "run-1",
        "sequence": 0,
        "occurred_at": "2026-06-15T22:00:00Z",
        "recipe_id": "demo",
        "recipe_name": "Demo",
        "steps_total": 2,
        "dry_run": False,
        "state": "running",
    }
    assert event.model_dump(mode="json") == expected
    assert json.loads(event.model_dump_json()) == expected


@pytest.mark.parametrize(
    ("event_cls", "fields"),
    [
        (
            RunStarted,
            (
                "type",
                "run_id",
                "sequence",
                "occurred_at",
                "recipe_id",
                "recipe_name",
                "steps_total",
                "dry_run",
                "state",
            ),
        ),
        (
            RunStateChanged,
            ("type", "run_id", "sequence", "occurred_at", "previous_state", "state", "message"),
        ),
        (
            StepStarted,
            ("type", "run_id", "sequence", "occurred_at", "step_index", "step_name", "action", "state"),
        ),
        (
            StepWaiting,
            (
                "type",
                "run_id",
                "sequence",
                "occurred_at",
                "step_index",
                "step_name",
                "action",
                "reason",
                "state",
            ),
        ),
        (
            StepPaused,
            (
                "type",
                "run_id",
                "sequence",
                "occurred_at",
                "step_index",
                "step_name",
                "action",
                "reason",
                "state",
            ),
        ),
        (
            StepResumed,
            (
                "type",
                "run_id",
                "sequence",
                "occurred_at",
                "step_index",
                "step_name",
                "action",
                "previous_state",
                "state",
            ),
        ),
        (
            ConfirmationRequested,
            (
                "type",
                "run_id",
                "sequence",
                "occurred_at",
                "confirmation_id",
                "step_index",
                "step_name",
                "action",
                "prompt",
                "state",
            ),
        ),
        (
            ConfirmationResolved,
            (
                "type",
                "run_id",
                "sequence",
                "occurred_at",
                "confirmation_id",
                "step_index",
                "step_name",
                "action",
                "approved",
                "state",
                "message",
            ),
        ),
        (
            StepFinished,
            (
                "type",
                "run_id",
                "sequence",
                "occurred_at",
                "step_index",
                "step_name",
                "action",
                "state",
                "message",
                "duration_seconds",
            ),
        ),
        (
            RunFinished,
            ("type", "run_id", "sequence", "occurred_at", "state", "success", "message", "duration_seconds"),
        ),
        (
            LogMessage,
            ("type", "run_id", "sequence", "occurred_at", "level", "message", "step_index"),
        ),
        (
            Heartbeat,
            ("type", "run_id", "sequence", "occurred_at", "run_state", "step_index", "step_state"),
        ),
    ],
)
def test_event_models_have_stable_fields(event_cls, fields):
    assert tuple(event_cls.model_fields) == fields


@pytest.mark.parametrize(
    "event",
    [
        RunStarted(
            run_id="run-1",
            sequence=0,
            occurred_at=FIXED_TIME,
            recipe_id="demo",
            recipe_name="Demo",
            steps_total=2,
        ),
        RunStateChanged(
            run_id="run-1",
            sequence=1,
            occurred_at=FIXED_TIME,
            previous_state=RunState.RUNNING,
            state=RunState.CONFIRMING,
            message="waiting for confirmation",
        ),
        StepStarted(
            run_id="run-1",
            sequence=2,
            occurred_at=FIXED_TIME,
            step_index=1,
            step_name="Open app",
            action="app.launch",
        ),
        StepWaiting(
            run_id="run-1",
            sequence=3,
            occurred_at=FIXED_TIME,
            step_index=1,
            step_name="Open app",
            action="app.launch",
            reason="process startup",
        ),
        StepPaused(
            run_id="run-1",
            sequence=4,
            occurred_at=FIXED_TIME,
            step_index=1,
            step_name="Open app",
            action="app.launch",
            reason="user pause",
        ),
        StepResumed(
            run_id="run-1",
            sequence=5,
            occurred_at=FIXED_TIME,
            step_index=1,
            step_name="Open app",
            action="app.launch",
        ),
        ConfirmationRequested(
            run_id="run-1",
            sequence=6,
            occurred_at=FIXED_TIME,
            confirmation_id="confirm-1",
            step_index=2,
            step_name="Click Play",
            action="desktop.click_text",
            prompt="Click Play?",
        ),
        ConfirmationResolved(
            run_id="run-1",
            sequence=7,
            occurred_at=FIXED_TIME,
            confirmation_id="confirm-1",
            step_index=2,
            step_name="Click Play",
            action="desktop.click_text",
            approved=True,
            state=StepState.RUNNING,
        ),
        StepFinished(
            run_id="run-1",
            sequence=8,
            occurred_at=FIXED_TIME,
            step_index=2,
            step_name="Click Play",
            action="desktop.click_text",
            state=StepState.SUCCESS,
            message="clicked",
            duration_seconds=0.25,
        ),
        RunFinished(
            run_id="run-1",
            sequence=9,
            occurred_at=FIXED_TIME,
            state=RunState.SUCCESS,
            success=True,
            duration_seconds=1.5,
        ),
        LogMessage(
            run_id="run-1",
            sequence=10,
            occurred_at=FIXED_TIME,
            level="info",
            message="run progressed",
            step_index=2,
        ),
        Heartbeat(
            run_id="run-1",
            sequence=11,
            occurred_at=FIXED_TIME,
            run_state=RunState.RUNNING,
            step_index=2,
            step_state=StepState.RUNNING,
        ),
    ],
)
def test_runtime_event_union_round_trips_by_type(event):
    payload = event.model_dump(mode="json")

    parsed = EVENT_ADAPTER.validate_python(payload)

    assert type(parsed) is type(event)
    assert parsed.model_dump(mode="json") == payload


def test_runtime_event_type_registry_matches_union_members():
    assert RUNTIME_EVENT_TYPES == (
        RunStarted,
        RunStateChanged,
        StepStarted,
        StepWaiting,
        StepPaused,
        StepResumed,
        ConfirmationRequested,
        ConfirmationResolved,
        StepFinished,
        RunFinished,
        LogMessage,
        Heartbeat,
    )


def test_finished_events_require_terminal_states():
    with pytest.raises(ValidationError, match="StepFinished state must be terminal"):
        StepFinished(
            run_id="run-1",
            sequence=0,
            occurred_at=FIXED_TIME,
            step_index=1,
            step_name="Open app",
            action="app.launch",
            state=StepState.RUNNING,
        )

    with pytest.raises(ValidationError, match="RunFinished state must be terminal"):
        RunFinished(
            run_id="run-1",
            sequence=1,
            occurred_at=FIXED_TIME,
            state=RunState.RUNNING,
            success=False,
        )


def test_runtime_models_import_without_gui_or_windows_dependencies():
    repo_root = Path(__file__).resolve().parents[1]
    code = """
import sys
import ritualist.runtime_models

blocked = ["PySide6", "pywinauto", "win32api", "win32gui", "win32con"]
loaded = [name for name in blocked if name in sys.modules]
if loaded:
    raise SystemExit(f"runtime_models loaded GUI/Windows modules: {loaded}")
"""

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
