from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from ritualist.canvas import (
    CanvasBindingKind,
    CanvasComponent,
    CanvasComponentBinding,
    CanvasDocument,
    CanvasRuntimeContext,
    CanvasRuntimeController,
    build_canvas_runtime_model,
)
from ritualist.actions.base import RunSummary, StepResult
from ritualist.canvas.app import build_canvas_use_payload
from ritualist.canvas.ritual_state import (
    RITUAL_STATE_SCHEMA_VERSION,
    RitualStateInputs,
    build_ritual_state,
    ritual_state_from_action_result,
    ritual_state_from_runtime_event,
)
from ritualist.run_logs import RunRecord


def _canvas() -> CanvasDocument:
    return CanvasDocument(
        id="ritual_state_canvas",
        name="Ritual State Canvas",
        components=(
            CanvasComponent(
                id="card",
                type="ritual.card",
                width=320,
                height=180,
                props={"title": "Gaming", "recipe_id": "gaming_mode"},
            ),
            CanvasComponent(
                id="status",
                type="ritual.status",
                width=320,
                height=90,
                binding=CanvasComponentBinding(kind=CanvasBindingKind.RECIPE, recipe_id="gaming_mode"),
            ),
            CanvasComponent(
                id="controller",
                type="ritual.controller",
                width=320,
                height=90,
                binding=CanvasComponentBinding(kind=CanvasBindingKind.RECIPE, recipe_id="gaming_mode"),
            ),
            CanvasComponent(
                id="doctor",
                type="doctor.badge",
                width=220,
                height=90,
                binding=CanvasComponentBinding(kind=CanvasBindingKind.RECIPE, recipe_id="gaming_mode"),
            ),
        ),
    )


def _run_record(
    tmp_path: Path,
    *,
    status: str,
    message: str = "finished",
    extra_metadata: dict[str, object] | None = None,
) -> RunRecord:
    run_dir = tmp_path / f"20260618T000000Z_{status}"
    run_dir.mkdir()
    (run_dir / "run.json").write_text("{}", encoding="utf-8")
    (run_dir / "steps.jsonl").write_text("", encoding="utf-8")
    metadata = {
        "recipe_id": "gaming_mode",
        "final_state": status,
        "status": status,
        "final_message": message,
        "ended_at": "2026-06-18T00:00:00+00:00",
    }
    metadata.update(extra_metadata or {})
    return RunRecord(
        run_id=run_dir.name,
        path=run_dir,
        metadata=metadata,
        steps=[
            {
                "index": 1,
                "step_name": "Ask before Play",
                "action": "confirm.ask",
                "status": status,
            }
        ],
    )


def test_canvas_runtime_embeds_ready_ritual_state_contract() -> None:
    model = build_canvas_runtime_model(
        _canvas(),
        context=CanvasRuntimeContext(recipe_ids={"gaming_mode"}, recent_runs=()),
    )

    state = model.ritual_states["gaming_mode"]
    card_state = model.component_state("card").data["ritual_state"]

    assert state["schema_version"] == RITUAL_STATE_SCHEMA_VERSION
    assert state["doctor"]["status"] == "unknown"
    assert state["dry_run"]["status"] == "not_run"
    assert state["active_run"]["state"] == "idle"
    assert state["last_run"]["state"] == "none"
    assert card_state == state


def test_doctor_state_summarizes_compatible_and_incompatible_reports() -> None:
    compatible = build_ritual_state(
        RitualStateInputs(
            recipe_id="gaming_mode",
            doctor={
                "compatibility": {"status": "compatible", "errors_count": 0, "warnings_count": 0},
                "checks": [],
                "variables": [],
                "capabilities": [],
                "completed_at": "2026-06-18T00:00:00+00:00",
            },
        )
    )
    incompatible = build_ritual_state(
        RitualStateInputs(
            recipe_id="gaming_mode",
            doctor={
                "compatibility": {"status": "incompatible", "errors_count": 1, "warnings_count": 1},
                "checks": [
                    {"status": "error", "message": "missing editor"},
                    {"status": "warning", "message": "optional terminal missing"},
                ],
                "variables": [{"name": "project_path", "status": "missing"}],
                "capabilities": [{"id": "windows_uia", "status": "error"}],
            },
        )
    )

    assert compatible["doctor"]["status"] == "compatible"
    assert compatible["doctor"]["errors_count"] == 0
    assert incompatible["doctor"]["status"] == "incompatible"
    assert incompatible["doctor"]["errors"] == ("missing editor",)
    assert incompatible["doctor"]["warnings"] == ("optional terminal missing",)
    assert incompatible["doctor"]["missing_inputs"] == ("project_path",)
    assert incompatible["doctor"]["missing_capabilities"] == ("windows_uia",)


def test_dry_run_state_records_plan_without_raw_payload() -> None:
    state = build_ritual_state(
        RitualStateInputs(
            recipe_id="gaming_mode",
            dry_run={
                "status": "dry-run",
                "results": [
                    {
                        "index": 1,
                        "step_name": "Open launcher",
                        "action": "app.launch",
                        "status": "dry-run",
                        "message": "would launch app",
                    },
                    {
                        "index": 2,
                        "step_name": "Confirm Play",
                        "action": "confirm.ask",
                        "status": "dry-run",
                        "message": "would ask for confirmation",
                    },
                ],
                "completed_at": "2026-06-18T00:00:01+00:00",
            },
        )
    )

    dry_run = state["dry_run"]

    assert dry_run["status"] == "dry-run"
    assert dry_run["planned_step_count"] == 2
    assert dry_run["confirmation_count"] == 1
    assert dry_run["step_summaries"][0]["name"] == "Open launcher"
    assert "metadata" not in dry_run["step_summaries"][0]


def test_runtime_events_update_running_waiting_confirming_and_paused_states() -> None:
    state = ritual_state_from_runtime_event(
        None,
        SimpleNamespace(
            type="run.started",
            run_id="run-1",
            recipe_id="gaming_mode",
            steps_total=4,
            dry_run=False,
            occurred_at="2026-06-18T00:00:00+00:00",
        ),
    )
    state = ritual_state_from_runtime_event(
        state,
        SimpleNamespace(type="step.started", step_index=1, step_name="Open launcher", action="app.launch"),
    )
    state = ritual_state_from_runtime_event(
        state,
        SimpleNamespace(
            type="step.waiting",
            step_index=2,
            step_name="Wait for user",
            action="wait.for_user",
            target="manual ready",
            elapsed_seconds=3,
            timeout_seconds=60,
            started_at="2026-06-18T00:00:03+00:00",
        ),
    )
    state = ritual_state_from_runtime_event(
        state,
        SimpleNamespace(
            type="confirmation.requested",
            step_index=3,
            step_name="Confirm Play",
            action="desktop.click_text",
            prompt="Clicking Play requires confirmation",
            target="Play",
            target_type="text",
        ),
    )
    state = ritual_state_from_runtime_event(
        state,
        SimpleNamespace(type="step.paused", step_index=3, step_name="Confirm Play", action="desktop.click_text", reason="user"),
    )

    active = state["active_run"]

    assert active["run_id"] == "run-1"
    assert active["state"] == "paused"
    assert active["current_step"]["name"] == "Confirm Play"
    assert active["wait"]["target"] == "manual ready"
    assert active["wait"]["timeout_seconds"] == 60
    assert active["confirmation"]["required"] is True
    assert active["confirmation"]["action"] == "desktop.click_text"
    assert active["confirmation"]["target"] == "Play"
    assert active["confirmation"]["target_type"] == "text"
    assert active["paused"]["active"] is True


def test_failed_and_finished_runtime_events_move_to_last_run() -> None:
    state = ritual_state_from_runtime_event(
        {"recipe_id": "gaming_mode"},
        SimpleNamespace(type="run.state_changed", state="failed", message="path missing"),
    )

    assert state["active_run"]["state"] == "failed"
    assert state["active_run"]["message"] == "path missing"

    state = ritual_state_from_runtime_event(
        state,
        SimpleNamespace(type="run.finished", state="stopped", message="declined confirmation", occurred_at="2026-06-18T00:01:00+00:00"),
    )

    assert state["active_run"]["state"] == "idle"
    assert state["last_run"]["state"] == "stopped"
    assert state["last_run"]["final_message"] == "declined confirmation"


def test_interrupted_finished_event_populates_recovery_actions() -> None:
    state = ritual_state_from_runtime_event(
        {"recipe_id": "gaming_mode"},
        SimpleNamespace(
            type="run.finished",
            state="interrupted",
            message="Ritualist exited before finalizing this run.",
            occurred_at="2026-06-18T00:01:00+00:00",
        ),
    )

    assert state["last_run"]["state"] == "interrupted"
    assert state["recovery"]["interrupted"] is True
    assert state["recovery"]["safe_next_actions"] == ("inspect_run", "doctor", "start_fresh")


def test_last_run_artifacts_and_interrupted_recovery_are_bounded(tmp_path: Path) -> None:
    record = _run_record(
        tmp_path,
        status="interrupted",
        message="Ritualist exited before finalizing this run.",
        extra_metadata={"interrupted_at": "2026-06-18T00:02:00+00:00"},
    )

    state = build_ritual_state(RitualStateInputs(recipe_id="gaming_mode", recent_runs=(record,)))

    assert state["last_run"]["state"] == "interrupted"
    assert state["last_run"]["run_log_path"] == str(record.path)
    assert {artifact["name"] for artifact in state["last_run"]["artifacts"]} == {"run.json", "steps.jsonl"}
    assert state["recovery"]["interrupted"] is True
    assert state["recovery"]["repaired_status"] == "interrupted"
    assert state["recovery"]["safe_next_actions"] == ("inspect_run", "doctor", "start_fresh")


def test_ritual_state_sanitizes_sensitive_text_and_has_no_raw_log_payload(tmp_path: Path) -> None:
    record = _run_record(tmp_path, status="failed", message="browser failed with token=secret")
    state = build_ritual_state(
        RitualStateInputs(
            recipe_id="gaming_mode",
            active={
                "status": "confirming",
                "confirmation": {"required": True, "message": "confirm password=secret before continuing"},
            },
            recent_runs=(record,),
        )
    )

    payload = json.dumps(state)

    assert "token=secret" not in payload
    assert "password=secret" not in payload
    assert "steps_jsonl" not in payload
    assert "token=[redacted]" in payload
    assert "password=[redacted]" in payload


def test_action_result_refreshes_doctor_and_dry_run_sections() -> None:
    doctor_state = ritual_state_from_action_result(
        "gaming_mode",
        "doctor",
        {
            "compatibility": {"status": "compatible", "errors_count": 0, "warnings_count": 0},
            "checks": [],
        },
    )
    dry_run_state = ritual_state_from_action_result(
        "gaming_mode",
        "dry_run",
        {
            "status": "dry-run",
            "results": [
                {"index": 1, "step_name": "Open", "action": "app.launch", "status": "dry-run"},
            ],
        },
        existing=doctor_state,
    )

    assert dry_run_state["doctor"]["status"] == "compatible"
    assert dry_run_state["dry_run"]["planned_step_count"] == 1
    assert dry_run_state["dry_run"]["step_summaries"][0]["action"] == "app.launch"


def test_run_action_result_preserves_dict_status_message_and_path() -> None:
    state = ritual_state_from_action_result(
        "gaming_mode",
        "run",
        {
            "status": "stopped",
            "message": "Confirmation declined",
            "run_dir": "runs/declined",
            "success": False,
        },
        existing={"recipe_id": "gaming_mode", "last_run": {"state": "success"}},
    )

    assert state["last_run"]["state"] == "stopped"
    assert state["last_run"]["final_message"] == "Confirmation declined"
    assert state["last_run"]["run_log_path"] == "runs/declined"
    assert state["recovery"]["interrupted"] is False


def test_canvas_action_dry_run_result_has_structured_steps_for_refresh() -> None:
    now = datetime.now(timezone.utc)

    class Service:
        def run_recipe(self, recipe_ref: str, *, dry_run: bool, **_kwargs: Any) -> RunSummary:
            assert dry_run is True
            return RunSummary(
                recipe_id=recipe_ref,
                recipe_name="Gaming",
                results=[
                    StepResult(
                        index=1,
                        step_name="Open launcher",
                        action="app.launch",
                        status="dry-run",
                        message="would launch app",
                        started_at=now,
                        ended_at=now,
                        metadata={"raw": "not exposed"},
                    )
                ],
            )

    controller = CanvasRuntimeController(
        action_service=Service(),  # type: ignore[arg-type]
        context=CanvasRuntimeContext(recipe_ids={"gaming_mode"}),
    )

    result = controller.dispatch(_canvas(), "card", "dry_run")

    assert result.data["results"][0]["step_name"] == "Open launcher"
    assert result.data["results"][0]["action"] == "app.launch"
    assert "metadata" not in result.data["results"][0]


def test_canvas_use_payload_exposes_ritual_state_for_qml() -> None:
    payload = build_canvas_use_payload(
        _canvas(),
        recipe_ids={"gaming_mode"},
        dry_run_summaries={
            "gaming_mode": {
                "status": "dry-run",
                "results": [{"index": 1, "step_name": "Open", "action": "app.launch", "status": "dry-run"}],
            }
        },
    )
    components = {component["id"]: component for component in payload["components"]}

    assert payload["runtime"]["ritual_states"]["gaming_mode"]["dry_run"]["planned_step_count"] == 1
    assert components["card"]["data"]["ritual_state"]["dry_run"]["step_summaries"][0]["name"] == "Open"


def test_existing_cached_ritual_state_is_renormalized_before_qml() -> None:
    model = build_canvas_runtime_model(
        _canvas(),
        context=CanvasRuntimeContext(
            recipe_ids={"gaming_mode"},
            runtime_state={
                "gaming_mode": {
                    "ritual_state": {
                        "schema_version": "bad",
                        "recipe_id": "gaming_mode",
                        "doctor": {"status": "compatible", "summary": "token=secret"},
                        "dry_run": {"status": "dry-run", "step_summaries": [{"name": "raw", "metadata": {"secret": "x"}}]},
                        "active_run": {
                            "state": "confirming",
                            "confirmation": {"required": True, "message": "password=secret", "target": "Play"},
                        },
                        "last_run": {"state": "failed", "final_message": "token=secret", "artifacts": [{"name": "run.json"}]},
                        "recovery": {"interrupted": True, "safe_next_actions": ["inspect_run"]},
                    }
                }
            },
            recent_runs=(),
        ),
    )
    payload = json.dumps(model.to_dict())
    state = model.ritual_states["gaming_mode"]

    assert state["schema_version"] == RITUAL_STATE_SCHEMA_VERSION
    assert state["active_run"]["confirmation"]["target"] == "Play"
    assert "token=secret" not in payload
    assert "password=secret" not in payload
    assert '"metadata"' not in payload
