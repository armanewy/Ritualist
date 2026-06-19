from __future__ import annotations

from setpiece.agent.models import AgentRoom, AgentRunState
from setpiece.agent.run_coordinator import (
    AgentRunCoordinator,
    AgentStartDecision,
    AgentStartKind,
)
from setpiece.runtime_models import RunFinished, RunStarted, RunState


def test_attended_start_claims_single_run_slot() -> None:
    coordinator = AgentRunCoordinator()

    result = coordinator.request_start(
        "gaming_mode",
        ritual_name="Gaming Mode",
        room=AgentRoom(id="gaming", name="Gaming Room", canvas_id="gaming_desktop"),
        step_count=3,
    )

    assert result.decision == AgentStartDecision.STARTED
    assert coordinator.attended_slot_occupied is True
    assert coordinator.state.state == AgentRunState.READY
    assert coordinator.state.active_ritual_id == "gaming_mode"
    assert coordinator.state.instrument_visible is True
    assert coordinator.state.tray_tooltip == "Setpiece - Ready: Gaming Mode"


def test_starting_same_attended_ritual_returns_to_active() -> None:
    coordinator = AgentRunCoordinator()
    coordinator.request_start("gaming_mode", ritual_name="Gaming Mode")

    result = coordinator.request_start("gaming_mode", ritual_name="Gaming Mode")

    assert result.decision == AgentStartDecision.RETURN_TO_ACTIVE
    assert result.active_ritual_id == "gaming_mode"
    assert coordinator.state.active_ritual_id == "gaming_mode"


def test_starting_different_attended_ritual_requires_stop_and_switch() -> None:
    coordinator = AgentRunCoordinator()
    coordinator.request_start("gaming_mode", ritual_name="Gaming Mode")

    result = coordinator.request_start("support_triage_workspace", ritual_name="Support Triage")

    assert result.decision == AgentStartDecision.STOP_AND_SWITCH_REQUIRED
    assert result.active_ritual_id == "gaming_mode"
    assert coordinator.state.active_ritual_id == "gaming_mode"


def test_shortcuts_do_not_occupy_attended_run_slot() -> None:
    coordinator = AgentRunCoordinator()

    result = coordinator.request_start(
        "open_docs",
        kind=AgentStartKind.SHORTCUT,
    )

    assert result.decision == AgentStartDecision.STARTED
    assert coordinator.attended_slot_occupied is False
    assert coordinator.state.active_ritual_id == ""
    assert coordinator.state.state == AgentRunState.IDLE


def test_close_and_hide_never_stop_running_ritual() -> None:
    coordinator = AgentRunCoordinator()
    coordinator.apply_runtime_event(
        RunStarted(
            run_id="run-1",
            sequence=0,
            recipe_id="gaming_mode",
            recipe_name="Gaming Mode",
            steps_total=2,
        )
    )

    hidden = coordinator.hide_instrument()
    closed = coordinator.close_instrument()

    assert hidden.state == AgentRunState.RUNNING
    assert closed.state == AgentRunState.RUNNING
    assert closed.active_ritual_id == "gaming_mode"
    assert closed.instrument_visible is False
    assert coordinator.attended_slot_occupied is True


def test_terminal_run_releases_attended_slot_for_next_ritual() -> None:
    coordinator = AgentRunCoordinator()
    coordinator.apply_runtime_event(
        RunStarted(
            run_id="run-1",
            sequence=0,
            recipe_id="gaming_mode",
            recipe_name="Gaming Mode",
            steps_total=1,
        )
    )
    coordinator.apply_runtime_event(
        RunFinished(
            run_id="run-1",
            sequence=1,
            state=RunState.SUCCESS,
            success=True,
            message="run completed",
        )
    )

    result = coordinator.request_start("project_setup", ritual_name="Project Setup")

    assert coordinator.attended_slot_occupied is True
    assert result.decision == AgentStartDecision.STARTED
    assert coordinator.state.active_ritual_id == "project_setup"
