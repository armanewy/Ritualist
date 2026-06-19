from __future__ import annotations

from datetime import datetime, timezone

from setpiece.agent.instrument_model import InstrumentState, build_instrument_model
from setpiece.agent.models import AgentConfirmation, AgentRunState, AgentState, AgentStep
from setpiece.runtime_models import RunStarted, StepStarted, StepWaiting


FIXED_TIME = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)


def test_ready_model_combines_preflight_transparency_doctor_dry_run_and_target() -> None:
    model = build_instrument_model(
        agent_state=AgentState(
            state=AgentRunState.READY,
            active_ritual_id="gaming_mode",
            active_ritual_name="Gaming Mode",
            step_count=3,
        ),
        recipe_transparency=_transparency(),
        doctor={
            "compatibility": {
                "status": "compatible_with_warnings",
                "errors_count": 0,
                "warnings_count": 1,
            },
            "warnings": ("Battle.net window is not visible yet.",),
            "missing_capabilities": ("windows_uia",),
        },
        dry_run={
            "status": "dry-run",
            "planned_step_count": 3,
            "confirmation_count": 1,
            "unresolved_inputs": ("battle_net_path",),
        },
        target_readiness={
            "target_display_name": "Diablo IV",
            "state": "update_available",
            "recommended_next_action": "Review Battle.net manually before updating Diablo IV.",
        },
    )

    assert model.state == InstrumentState.READY
    assert model.ritual_name == "Gaming Mode"
    assert model.intent == "Prepare the game workspace."
    assert model.step_count == 3
    assert model.confirmation_count == 1
    assert "Target: Diablo IV" in model.affected
    assert "Setup: Battle.net path" in model.affected
    assert "Capability: windows_uia" in model.prerequisites
    assert "Input: battle_net_path" in model.prerequisites
    assert "Battle.net window is not visible yet." in model.warnings
    assert [action.label for action in model.actions] == ["Start ritual", "Edit setup", "Details"]
    assert model.actions[0].enabled is True


def test_ready_start_is_disabled_when_doctor_has_errors() -> None:
    model = build_instrument_model(
        agent_state=AgentState(
            state=AgentRunState.PREFLIGHT,
            active_ritual_id="support_triage",
            active_ritual_name="Support Triage",
        ),
        doctor={"compatibility": {"errors_count": 1}},
    )

    assert model.state == InstrumentState.PREFLIGHT
    assert model.actions[0].label == "Start ritual"
    assert model.actions[0].enabled is False
    assert model.actions[0].reason == "Review Doctor errors before starting."


def test_running_model_uses_runtime_events_direct_verb_next_step_elapsed_and_safe_pause() -> None:
    model = build_instrument_model(
        runtime_events=[
            RunStarted(
                run_id="run-1",
                sequence=0,
                occurred_at=FIXED_TIME,
                recipe_id="gaming_mode",
                recipe_name="Gaming Mode",
                steps_total=3,
            ),
            StepStarted(
                run_id="run-1",
                sequence=1,
                occurred_at=FIXED_TIME,
                step_index=2,
                step_name="Open Battle.net",
                action="app.launch",
            ),
        ],
        ritual_state={
            "recipe_id": "gaming_mode",
            "active_run": {
                "run_id": "run-1",
                "state": "running",
                "elapsed_seconds": 75,
                "steps_total": 3,
                "current_step": {
                    "index": 2,
                    "name": "Open Battle.net",
                    "action": "app.launch",
                    "state": "running",
                    "safe_to_pause": True,
                },
            },
        },
        recipe_transparency=_transparency(),
    )

    assert model.state == InstrumentState.RUNNING
    assert model.headline == "Open Battle.net"
    assert model.subheadline == "Step 2 of 3"
    assert model.current_verb == "Open Battle.net"
    assert model.next_step == "Confirm Play: invoke exact visible desktop text after confirmation."
    assert model.progress.elapsed_seconds == 75
    assert "percentage" not in model.to_dict()["progress"]
    assert [action.label for action in model.actions] == ["Pause", "Stop"]


def test_running_model_omits_pause_when_safety_is_not_known() -> None:
    model = build_instrument_model(
        agent_state=AgentState(
            state=AgentRunState.RUNNING,
            active_ritual_id="gaming_mode",
            current_step=AgentStep(
                index=1,
                name="Launch app",
                action="app.launch",
                state="running",
            ),
            step_count=2,
        )
    )

    assert [action.label for action in model.actions] == ["Stop"]


def test_paused_model_stays_distinct_from_running_and_failure() -> None:
    model = build_instrument_model(
        agent_state=AgentState(
            state=AgentRunState.PAUSED,
            active_ritual_id="gaming_mode",
            active_ritual_name="Gaming Mode",
            current_step=AgentStep(
                index=2,
                name="Wait for Battle.net",
                action="target.wait_state",
                state="paused",
                message="operator requested pause",
            ),
            step_count=3,
        ),
        ritual_state={
            "recipe_id": "gaming_mode",
            "active_run": {
                "state": "paused",
                "message": "paused by operator",
                "paused": {"active": True, "reason": "operator requested pause"},
            },
        },
        recipe_transparency=_transparency(),
    )

    assert model.state == InstrumentState.PAUSED
    assert model.headline == "Paused: Gaming Mode"
    assert model.subheadline == "operator requested pause"
    assert [action.label for action in model.actions] == ["Resume", "Stop"]
    assert model.current_verb == "Wait for Battle.net"


def test_waiting_model_reports_dependency_timing_and_idempotent_check_again_without_fake_progress(
) -> None:
    model = build_instrument_model(
        runtime_events=[
            RunStarted(
                run_id="run-1",
                sequence=0,
                recipe_id="gaming_mode",
                recipe_name="Gaming Mode",
                steps_total=2,
            ),
            StepWaiting(
                run_id="run-1",
                sequence=1,
                step_index=1,
                step_name="Wait for Battle.net",
                action="target.wait_state",
                reason="Waiting for Battle.net readiness",
                target="Battle.net Play button",
                elapsed_seconds=12,
                timeout_seconds=60,
            ),
        ],
        ritual_state={
            "recipe_id": "gaming_mode",
            "active_run": {
                "state": "waiting",
                "wait": {
                    "dependency": "Battle.net Play button",
                    "elapsed_seconds": 12,
                    "timeout_seconds": 60,
                    "next_check_seconds": 5,
                    "idempotent": True,
                    "user_action_required": False,
                },
            },
        },
    )

    assert model.state == InstrumentState.WAITING
    assert model.wait is not None
    assert model.wait.dependency == "Battle.net Play button"
    assert model.wait.user_action_required is False
    assert model.wait.next_check_seconds == 5
    assert model.wait.check_again_available is True
    assert "Check again" in [action.label for action in model.actions]
    assert "percentage" not in model.to_dict()["progress"]


def test_waiting_model_blocks_check_again_when_user_action_is_required() -> None:
    model = build_instrument_model(
        agent_state=AgentState(
            state=AgentRunState.WAITING,
            active_ritual_id="gaming_mode",
            current_step=AgentStep(
                index=1,
                name="Wait for login",
                action="target.wait_state",
                state="waiting",
            ),
            step_count=2,
        ),
        ritual_state={
            "recipe_id": "gaming_mode",
            "active_run": {
                "state": "waiting",
                "wait": {
                    "dependency": "Battle.net login",
                    "user_action_required": True,
                    "can_check_again": False,
                },
            },
        },
    )

    assert model.wait is not None
    assert model.wait.user_action_required is True
    assert model.wait.check_again_available is False
    assert "Check again" not in [action.label for action in model.actions]


def test_confirmation_model_preserves_consequence_target_negative_path_and_remembered_eligibility(
) -> None:
    model = build_instrument_model(
        agent_state=AgentState(
            state=AgentRunState.CONFIRMATION,
            active_ritual_id="gaming_mode",
            active_ritual_name="Gaming Mode",
            pending_confirmation=AgentConfirmation(
                confirmation_id="confirm-1",
                step_index=2,
                step_name="Confirm Play",
                action="desktop.click_text",
                prompt="desktop.click_text will press Play. Continue?",
                target="Play",
                target_type="button",
            ),
            step_count=3,
        ),
        ritual_state={
            "recipe_id": "gaming_mode",
            "active_run": {
                "state": "confirming",
                "steps_completed": 1,
                "confirmation": {
                    "required": True,
                    "remember_eligible": True,
                    "remember_reason": "This exact local target can be remembered.",
                },
            },
        },
    )

    assert model.state == InstrumentState.CONFIRMATION
    assert model.confirmation is not None
    assert model.confirmation.consequence == "action will press Play. Continue?"
    assert model.confirmation.target == "Play"
    assert model.confirmation.preserved_work == "Completed work remains recorded (1 step)."
    assert model.confirmation.safe_negative_path.startswith("Cancel stops before this action")
    assert model.confirmation.remembered_approval_eligible is True
    assert "desktop.click_text" not in model.headline
    assert [action.label for action in model.actions] == [
        "Approve once",
        "Approve and remember locally",
        "Cancel safely",
    ]


def test_failure_model_reports_failed_step_cause_completed_work_not_run_remedy_and_logs() -> None:
    model = build_instrument_model(
        agent_state=AgentState(
            state=AgentRunState.FAILURE,
            active_ritual_id="gaming_mode",
            latest_failure=None,
            current_step=AgentStep(
                index=2,
                name="Click Play",
                action="desktop.click_text",
                state="failed",
                message="target disappeared",
            ),
            step_count=4,
        ),
        ritual_state={
            "recipe_id": "gaming_mode",
            "active_run": {
                "state": "failed",
                "message": "target disappeared",
                "current_step": {"index": 2, "name": "Click Play", "state": "failed"},
            },
            "last_run": {
                "state": "failed",
                "steps_completed": 1,
                "not_run_count": 2,
                "run_log_path": "C:/runs/run-1",
            },
        },
        target_readiness={
            "recommended_next_action": "Check Battle.net readiness, then retry.",
            "suggestions": ("Bring Battle.net forward manually.",),
        },
    )

    assert model.state == InstrumentState.FAILURE
    assert model.failure is not None
    assert model.failure.failed_step == "Click Play"
    assert model.failure.cause == "target disappeared"
    assert model.failure.completed_work == "1 step completed before failure."
    assert model.failure.steps_not_run == 2
    assert model.failure.remedy == "Check Battle.net readiness, then retry."
    assert model.failure.run_log_path == "C:/runs/run-1"
    assert model.actions[0].label == "Open logs"
    assert model.actions[0].enabled is True


def test_recovery_model_and_historical_interruption_stay_compact_until_opened() -> None:
    compact = build_instrument_model(
        agent_state=AgentState(state=AgentRunState.RECOVERY, active_ritual_id="gaming_mode"),
        ritual_state={
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
        },
    )

    opened = build_instrument_model(
        agent_state=AgentState(state=AgentRunState.RECOVERY, active_ritual_id="gaming_mode"),
        ritual_state={
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
        },
        show_history=True,
    )

    assert compact.state == InstrumentState.RECOVERY
    assert compact.recovery is not None
    assert compact.recovery.checkpoint == "C:/runs/run-2"
    assert compact.recovery.repair_steps == (
        "Inspect the interrupted run log",
        "Run Doctor before resuming",
        "Start fresh if the checkpoint is unsafe",
    )
    assert [action.label for action in compact.actions] == ["Resume ritual", "Leave restored"]
    assert compact.history.collapsed is True
    assert compact.history.entries == ()
    assert opened.history.collapsed is False
    assert opened.history.entries == (
        "Step 1: Open launcher (success)",
        "Step 2: Wait for Play (waiting)",
    )


def _transparency() -> dict[str, object]:
    return {
        "recipe_id": "gaming_mode",
        "recipe_name": "Gaming Mode",
        "purpose": "Prepare the game workspace.",
        "affected_apps": ("Battle.net",),
        "setup_fields": (
            {"name": "battle_net_path", "label": "Battle.net path", "editable": True},
            {"name": "target_game", "label": "Target game", "editable": True},
        ),
        "live_preflight_requirements": {
            "os": ("windows",),
            "required_capabilities": ("windows_uia",),
            "expected_windows": ({"title_contains": "Battle.net"},),
        },
        "confirmations": ({"name": "Confirm Play"},),
        "ordered_steps": (
            {
                "index": 1,
                "name": "Inspect readiness",
                "action": "target.inspect",
                "summary": "Inspect readiness",
            },
            {
                "index": 2,
                "name": "Open Battle.net",
                "action": "app.launch",
                "summary": "Open Battle.net",
            },
            {
                "index": 3,
                "name": "Confirm Play",
                "action": "desktop.click_text",
                "summary": "Confirm Play: invoke exact visible desktop text after confirmation.",
            },
        ),
        "plain_language_plan": ("Purpose: Prepare the game workspace.",),
    }
