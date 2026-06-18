from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ritualist.run_logs import RunRecord, summarize_run_record

RITUAL_STATE_SCHEMA_VERSION = "ritualist.canvas.ritual_state.v1"
MAX_STEP_SUMMARIES = 12
MAX_ARTIFACTS = 8


@dataclass(frozen=True)
class RitualStateInputs:
    recipe_id: str
    active: Mapping[str, Any] | None = None
    doctor: Mapping[str, Any] | None = None
    dry_run: Mapping[str, Any] | None = None
    recent_runs: Sequence[RunRecord] = ()


def build_ritual_state(inputs: RitualStateInputs) -> dict[str, Any]:
    recipe_id = str(inputs.recipe_id or "").strip()
    active = _mapping(inputs.active)
    last_record = _latest_run_for_recipe(recipe_id, inputs.recent_runs)
    return {
        "schema_version": RITUAL_STATE_SCHEMA_VERSION,
        "recipe_id": recipe_id,
        "doctor": _doctor_state(inputs.doctor),
        "dry_run": _dry_run_state(inputs.dry_run),
        "active_run": _active_run_state(active),
        "last_run": _last_run_state(last_record),
        "recovery": _recovery_state(active, last_record),
    }


def normalize_ritual_state(recipe_id: str, value: Mapping[str, Any] | None) -> dict[str, Any]:
    data = _mapping(value)
    if not data:
        return build_ritual_state(RitualStateInputs(recipe_id=recipe_id))
    return {
        "schema_version": RITUAL_STATE_SCHEMA_VERSION,
        "recipe_id": _safe_text(data.get("recipe_id") or recipe_id),
        "doctor": _doctor_state(_mapping(data.get("doctor"))),
        "dry_run": _dry_run_state(_mapping(data.get("dry_run"))),
        "active_run": _active_run_state(_mapping(data.get("active_run"))),
        "last_run": _normalize_last_run_state(_mapping(data.get("last_run"))),
        "recovery": _normalize_recovery_state(_mapping(data.get("recovery"))),
    }


def ritual_state_from_action_result(
    recipe_id: str,
    action: str,
    result: Any,
    *,
    existing: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    base = normalize_ritual_state(recipe_id, existing)
    if action == "doctor":
        base["doctor"] = _doctor_state(_result_mapping(result))
    elif action == "dry_run":
        base["dry_run"] = _dry_run_state(_result_mapping(result))
    elif action == "run":
        base["last_run"] = _last_run_state_from_result(result)
        base["recovery"] = _normalize_recovery_state(
            {
                "interrupted": base["last_run"].get("state") == "interrupted",
                "repaired_status": "interrupted" if base["last_run"].get("state") == "interrupted" else "",
                "safe_next_actions": ("inspect_run", "doctor", "start_fresh"),
            }
        )
    return base


def ritual_state_from_runtime_event(
    existing: Mapping[str, Any] | None,
    event: Any,
) -> dict[str, Any]:
    state = normalize_ritual_state(
        str(getattr(event, "recipe_id", "") or _mapping(existing).get("recipe_id") or ""),
        existing,
    )
    active = dict(_mapping(state.get("active_run")))
    event_type = str(getattr(event, "type", "") or "")
    if event_type == "run.started":
        active.update(
            {
                "run_id": str(getattr(event, "run_id", "") or ""),
                "state": "running",
                "started_at": _datetime_value(getattr(event, "occurred_at", None)),
                "elapsed_seconds": 0,
                "steps_total": _int_value(getattr(event, "steps_total", None)),
                "dry_run": bool(getattr(event, "dry_run", False)),
            }
        )
    elif event_type == "run.state_changed":
        active["state"] = _string_value(getattr(event, "state", None))
        active["message"] = _safe_text(getattr(event, "message", None))
    elif event_type == "step.started":
        active["current_step"] = _step_summary_from_event(event, state_name="running")
        active["state"] = "running"
    elif event_type == "step.waiting":
        active["current_step"] = _step_summary_from_event(event, state_name="waiting")
        active["state"] = "waiting"
        active["wait"] = _wait_state_from_event(event)
    elif event_type == "step.paused":
        active["current_step"] = _step_summary_from_event(event, state_name="paused")
        active["state"] = "paused"
        active["paused"] = {"active": True, "reason": _safe_text(getattr(event, "reason", None))}
    elif event_type == "step.resumed":
        active["current_step"] = _step_summary_from_event(event, state_name=_string_value(getattr(event, "state", None)))
        active["state"] = "running"
        active["paused"] = {"active": False, "reason": ""}
    elif event_type == "confirmation.requested":
        active["current_step"] = _step_summary_from_event(event, state_name="confirming")
        active["state"] = "confirming"
        active["confirmation"] = _confirmation_state_from_event(event)
    elif event_type == "confirmation.resolved":
        previous_confirmation = _mapping(active.get("confirmation"))
        approved = bool(getattr(event, "approved", False))
        message = "Starting..." if approved else _safe_text(getattr(event, "message", None))
        active["state"] = "starting" if approved else "stopped"
        active["message"] = message
        active["current_step"] = _step_summary_from_event(event, state_name="starting" if approved else "cancelled")
        active["current_step"]["message"] = message
        active["confirmation"] = {
            "required": False,
            "approved": approved,
            "step_index": _int_value(getattr(event, "step_index", None)),
            "step_name": _safe_text(getattr(event, "step_name", None)),
            "action": _safe_action(getattr(event, "action", None)),
            "target": _safe_text(previous_confirmation.get("target") or ""),
            "target_type": _safe_text(previous_confirmation.get("target_type") or ""),
            "message": _safe_text(getattr(event, "message", None)),
        }
    elif event_type == "step.finished":
        step_state = _string_value(getattr(event, "state", None))
        visual_state = _finished_step_visual_state(event, step_state)
        active["current_step"] = _step_summary_from_event(event, state_name=visual_state)
        active["current_step"]["message"] = _safe_text(getattr(event, "message", None))
        if visual_state in {"blocked", "failed"}:
            active["state"] = visual_state
            active["message"] = active["current_step"]["message"]
    elif event_type == "heartbeat":
        active["state"] = _string_value(getattr(event, "run_state", None)) or active.get("state", "")
        active["current_step"] = _step_summary_from_event(event, state_name=_string_value(getattr(event, "step_state", None)))
        wait = _wait_state_from_heartbeat(event)
        if wait["target"] or wait["timeout_seconds"] is not None:
            active["wait"] = wait
    elif event_type == "run.finished":
        state_name = _string_value(getattr(event, "state", None))
        active["state"] = state_name
        state["last_run"] = {
            "state": state_name,
            "final_message": _safe_text(getattr(event, "message", None)),
            "stopped_reason": "",
            "last_step": _safe_text(_mapping(active.get("current_step")).get("name")),
            "run_log_path": "",
            "artifacts": (),
            "finished_at": _datetime_value(getattr(event, "occurred_at", None)),
            "step_summaries": (),
            "steps_total": 0,
            "steps_completed": 0,
            "steps_failed": 0,
            "not_run_count": 0,
            "operator_notes_count": 0,
            "last_operator_note_at": "",
        }
        if state_name == "interrupted":
            state["recovery"] = {
                "interrupted": True,
                "repaired_status": "interrupted",
                "safe_next_actions": ("inspect_run", "doctor", "start_fresh"),
            }
        active = {}
    state["active_run"] = _active_run_state(active)
    if event_type != "run.finished" or state.get("last_run", {}).get("state") != "interrupted":
        state["recovery"] = _recovery_state(active, None)
    return state


def _doctor_state(value: Mapping[str, Any] | None) -> dict[str, Any]:
    data = _mapping(value)
    compatibility = _mapping(data.get("compatibility"))
    checks = [item for item in _sequence(data.get("checks")) if isinstance(item, Mapping)]
    errors = [
        _safe_text(item.get("message"))
        for item in checks
        if str(item.get("status") or "").casefold() in {"error", "failed", "incompatible"}
    ]
    warnings = [
        _safe_text(item.get("message"))
        for item in checks
        if str(item.get("status") or "").casefold() in {"warn", "warning"}
    ]
    missing_inputs = [
        str(item.get("name") or "")
        for item in _sequence(data.get("variables"))
        if isinstance(item, Mapping) and item.get("status") == "missing"
    ]
    capabilities = [
        str(item.get("id") or "")
        for item in _sequence(data.get("capabilities"))
        if isinstance(item, Mapping) and str(item.get("status") or "").casefold() not in {"ok", "configured"}
    ]
    return {
        "status": _safe_text(compatibility.get("status") or data.get("status") or data.get("compatibility") or "unknown"),
        "errors_count": _int_value(_first_present(compatibility.get("errors_count"), data.get("errors_count"))),
        "warnings_count": _int_value(_first_present(compatibility.get("warnings_count"), data.get("warnings_count"))),
        "warnings": tuple(item for item in warnings if item),
        "errors": tuple(item for item in errors if item),
        "checked_at": _safe_text(data.get("checked_at") or data.get("completed_at") or ""),
        "missing_inputs": tuple(item for item in missing_inputs if item),
        "missing_capabilities": tuple(item for item in capabilities if item),
        "summary": _safe_text(data.get("message") or ""),
    }


def _dry_run_state(value: Mapping[str, Any] | None) -> dict[str, Any]:
    data = _mapping(value)
    results = _result_steps(data)
    confirmations = [
        step
        for step in results
        if str(step.get("action") or "").startswith("confirm.")
        or bool(_mapping(step.get("metadata")).get("requires_confirmation"))
        or "confirm" in str(step.get("message") or "").casefold()
    ]
    unresolved_inputs = sorted(
        {
            str(item)
            for step in results
            for item in _sequence(_mapping(step.get("metadata")).get("missing_inputs"))
            if str(item)
        }
    )
    status = _safe_text(data.get("status") or ("dry-run" if results else "not_run"))
    return {
        "status": status,
        "planned_step_count": len(results),
        "step_summaries": tuple(_step_summary_from_mapping(step) for step in results[:MAX_STEP_SUMMARIES]),
        "confirmation_count": len(confirmations),
        "unresolved_inputs": tuple(unresolved_inputs),
        "completed_at": _safe_text(data.get("completed_at") or data.get("ended_at") or ""),
    }


def _active_run_state(value: Mapping[str, Any] | None) -> dict[str, Any]:
    data = _mapping(value)
    wait = _mapping(data.get("wait"))
    paused = _mapping(data.get("paused"))
    confirmation = _mapping(data.get("confirmation"))
    current_step = _current_step_from_mapping(data)
    return {
        "run_id": _safe_text(data.get("run_id") or ""),
        "state": _safe_text(data.get("state") or data.get("status") or "idle"),
        "message": _safe_text(data.get("message") or ""),
        "current_step": current_step,
        "elapsed_seconds": _float_value(data.get("elapsed_seconds")),
        "wait": {
            "target": _safe_text(wait.get("target") or data.get("wait_target") or ""),
            "elapsed_seconds": _float_value(wait.get("elapsed_seconds") or data.get("wait_elapsed_seconds")),
            "timeout_seconds": _float_value(wait.get("timeout_seconds") or data.get("wait_timeout_seconds")),
            "started_at": _safe_text(wait.get("started_at") or data.get("wait_started_at") or ""),
        },
        "paused": {
            "active": bool(paused.get("active") or data.get("state") == "paused" or data.get("status") == "paused"),
            "reason": _safe_text(paused.get("reason") or ""),
        },
        "confirmation": {
            "required": bool(confirmation.get("required") or data.get("state") == "confirming" or data.get("status") == "confirming"),
            "approved": bool(confirmation.get("approved")),
            "step_index": _int_value(confirmation.get("step_index")),
            "step_name": _safe_text(confirmation.get("step_name") or ""),
            "action": _safe_action(confirmation.get("action") or ""),
            "target": _safe_text(confirmation.get("target") or ""),
            "target_type": _safe_text(confirmation.get("target_type") or ""),
            "message": _safe_text(confirmation.get("message") or ""),
        },
        "started_at": _safe_text(data.get("started_at") or ""),
    }


def _last_run_state(record: RunRecord | None) -> dict[str, Any]:
    if record is None:
        return _empty_last_run_state()
    metadata = record.metadata
    summary = summarize_run_record(record)
    ledger = _last_run_ledger(record)
    return {
        "state": _safe_text(metadata.get("final_state") or metadata.get("status") or summary.final_status),
        "final_message": _safe_text(metadata.get("final_message") or summary.last_step),
        "stopped_reason": _safe_text(metadata.get("stopped_reason") or ""),
        "last_step": _safe_text(summary.last_step),
        "run_log_path": str(record.path),
        "artifacts": tuple(_artifact_metadata(record)),
        "finished_at": _safe_text(metadata.get("ended_at") or metadata.get("interrupted_at") or ""),
        **ledger,
    }


def _normalize_last_run_state(data: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "state": _safe_text(data.get("state") or "none"),
        "final_message": _safe_text(data.get("final_message") or ""),
        "stopped_reason": _safe_text(data.get("stopped_reason") or ""),
        "last_step": _safe_text(data.get("last_step") or ""),
        "run_log_path": _safe_text(data.get("run_log_path") or ""),
        "artifacts": tuple(_normalize_artifact(item) for item in _sequence(data.get("artifacts")) if isinstance(item, Mapping))[
            :MAX_ARTIFACTS
        ],
        "finished_at": _safe_text(data.get("finished_at") or ""),
        "step_summaries": tuple(
            _step_summary_from_mapping(item)
            for item in _sequence(data.get("step_summaries"))
            if isinstance(item, Mapping)
        )[:MAX_STEP_SUMMARIES],
        "steps_total": _int_value(data.get("steps_total")) or 0,
        "steps_completed": _int_value(data.get("steps_completed")) or 0,
        "steps_failed": _int_value(data.get("steps_failed")) or 0,
        "not_run_count": _int_value(data.get("not_run_count")) or 0,
        "operator_notes_count": _int_value(data.get("operator_notes_count")) or 0,
        "last_operator_note_at": _safe_text(data.get("last_operator_note_at") or ""),
    }


def _last_run_state_from_result(result: Any) -> dict[str, Any]:
    data = _result_mapping(result)
    run_dir = data.get("run_dir")
    raw_status = data.get("final_state") or data.get("state") or data.get("status")
    if raw_status:
        status = _safe_text(raw_status)
    else:
        status = "success" if bool(data.get("success")) else "failed"
    return {
        "state": status,
        "final_message": _safe_text(data.get("final_message") or data.get("message") or ""),
        "stopped_reason": "",
        "last_step": "",
        "run_log_path": str(run_dir) if run_dir else "",
        "artifacts": (),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "step_summaries": (),
        "steps_total": 0,
        "steps_completed": 0,
        "steps_failed": 0,
        "not_run_count": 0,
        "operator_notes_count": 0,
        "last_operator_note_at": "",
    }


def _recovery_state(active: Mapping[str, Any], record: RunRecord | None) -> dict[str, Any]:
    active_state = str(active.get("state") or active.get("status") or "")
    last_state = str(record.metadata.get("final_state") or record.metadata.get("status") or "") if record else ""
    interrupted = active_state == "interrupted" or last_state == "interrupted"
    repaired = bool(record and record.metadata.get("interrupted_at"))
    return {
        "interrupted": interrupted,
        "repaired_status": "interrupted" if repaired else "",
        "safe_next_actions": ("inspect_run", "doctor", "start_fresh") if interrupted else (),
    }


def _normalize_recovery_state(data: Mapping[str, Any]) -> dict[str, Any]:
    interrupted = bool(data.get("interrupted"))
    actions = tuple(_safe_text(item) for item in _sequence(data.get("safe_next_actions")) if _safe_text(item))
    return {
        "interrupted": interrupted,
        "repaired_status": _safe_text(data.get("repaired_status") or ""),
        "safe_next_actions": actions if interrupted else (),
    }


def _latest_run_for_recipe(recipe_id: str, records: Sequence[RunRecord]) -> RunRecord | None:
    for record in records:
        if str(record.metadata.get("recipe_id") or "") == recipe_id:
            return record
    return None


def _result_mapping(result: Any) -> dict[str, Any]:
    if result is None:
        return {}
    if hasattr(result, "to_dict"):
        converted = result.to_dict()
        if isinstance(converted, Mapping):
            return dict(converted)
    if hasattr(result, "model_dump"):
        converted = result.model_dump(mode="json")
        if isinstance(converted, Mapping):
            return dict(converted)
    if isinstance(result, Mapping):
        return dict(result)
    payload: dict[str, Any] = {}
    for name in ("status", "success", "results", "run_dir", "recipe_id", "recipe_name"):
        if hasattr(result, name):
            payload[name] = getattr(result, name)
    return payload


def _result_steps(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = data.get("results") or data.get("steps") or []
    steps: list[dict[str, Any]] = []
    for item in _sequence(raw):
        if isinstance(item, Mapping):
            steps.append(dict(item))
            continue
        converted = _result_mapping(item)
        if converted:
            steps.append(converted)
    return steps


def _empty_last_run_state() -> dict[str, Any]:
    return {
        "state": "none",
        "final_message": "",
        "stopped_reason": "",
        "last_step": "",
        "run_log_path": "",
        "artifacts": (),
        "finished_at": "",
        "step_summaries": (),
        "steps_total": 0,
        "steps_completed": 0,
        "steps_failed": 0,
        "not_run_count": 0,
        "operator_notes_count": 0,
        "last_operator_note_at": "",
    }


def _last_run_ledger(record: RunRecord) -> dict[str, Any]:
    steps = [
        _step_summary_from_mapping(step)
        for step in record.steps
        if isinstance(step, Mapping)
    ]
    steps_total = _int_value(record.metadata.get("steps_total")) or _max_step_index(steps) or len(steps)
    attempted_count = len(steps)
    completed_count = sum(1 for step in steps if step["state"] in {"success", "dry-run", "skipped"})
    failed_count = sum(1 for step in steps if step["state"] in {"failed", "error", "cancelled"})
    notes_count = _int_value(record.metadata.get("operator_notes_count"))
    if notes_count is None:
        notes_count = len(record.notes)
    last_note_at = _safe_text(record.metadata.get("last_operator_note_at") or "")
    if not last_note_at and record.notes:
        last_note_at = _safe_text(record.notes[-1].get("at") or "")
    return {
        "step_summaries": tuple(steps[:MAX_STEP_SUMMARIES]),
        "steps_total": steps_total,
        "steps_completed": completed_count,
        "steps_failed": failed_count,
        "not_run_count": max(0, steps_total - attempted_count),
        "operator_notes_count": notes_count,
        "last_operator_note_at": last_note_at,
    }


def _max_step_index(steps: Sequence[Mapping[str, Any]]) -> int:
    values = [
        int(step["index"])
        for step in steps
        if isinstance(step.get("index"), int)
    ]
    return max(values, default=0)


def _step_summary_from_mapping(step: Mapping[str, Any]) -> dict[str, Any]:
    summary = {
        "index": _int_value(step.get("index") or step.get("step_index")),
        "name": _safe_text(step.get("step_name") or step.get("name") or ""),
        "action": _safe_action(step.get("action") or ""),
        "state": _safe_text(step.get("status") or step.get("state") or ""),
        "message": _safe_text(step.get("message") or ""),
    }
    verification = _verification_summary(_mapping(step.get("metadata")).get("verification") or step.get("verification"))
    if verification:
        summary["verification"] = verification
    return summary


def _step_summary_from_event(event: Any, *, state_name: str) -> dict[str, Any]:
    summary = {
        "index": _int_value(getattr(event, "step_index", None)),
        "name": _safe_text(getattr(event, "step_name", None)),
        "action": _safe_action(getattr(event, "action", None)),
        "state": _safe_text(state_name or ""),
        "message": "",
    }
    verification = _verification_summary(_mapping(getattr(event, "metadata", None)).get("verification"))
    if verification:
        summary["verification"] = verification
    return summary


def _finished_step_visual_state(event: Any, step_state: str) -> str:
    if _event_blocked(event):
        return "blocked"
    if step_state == "failed":
        return "failed"
    if step_state == "cancelled":
        return "cancelled"
    return _safe_text(step_state)


def _event_blocked(event: Any) -> bool:
    metadata = _mapping(getattr(event, "metadata", None))
    target_resolution = _mapping(metadata.get("target_resolution"))
    if str(target_resolution.get("status") or "").casefold() == "blocked":
        return True
    message = str(getattr(event, "message", "") or "").casefold()
    return "blocked" in message


def _verification_summary(value: object) -> dict[str, str]:
    data = _mapping(value)
    if not data:
        return {}
    status = _safe_text(data.get("status") or "")
    message = _safe_text(data.get("message") or "")
    name = _safe_text(data.get("name") or "")
    if not (status or message or name):
        return {}
    return {"name": name, "status": status, "message": message}


def _current_step_from_mapping(data: Mapping[str, Any]) -> dict[str, Any]:
    current = _mapping(data.get("current_step"))
    if current:
        return {
            "index": _int_value(current.get("index") or current.get("step_index")),
            "name": _safe_text(current.get("name") or current.get("step_name") or ""),
            "action": _safe_action(current.get("action") or ""),
            "state": _safe_text(current.get("state") or ""),
            "message": _safe_text(current.get("message") or ""),
        }
    return {
        "index": _int_value(data.get("current_step_index") or data.get("step_index")),
        "name": _safe_text(data.get("current_step") or data.get("step_name") or ""),
        "action": _safe_action(data.get("action") or ""),
        "state": _safe_text(data.get("current_step_state") or data.get("step_state") or ""),
        "message": _safe_text(data.get("message") or ""),
    }


def _wait_state_from_event(event: Any) -> dict[str, Any]:
    return {
        "target": _safe_text(getattr(event, "target", None)),
        "elapsed_seconds": _float_value(getattr(event, "elapsed_seconds", None)),
        "timeout_seconds": _float_value(getattr(event, "timeout_seconds", None)),
        "started_at": _datetime_value(getattr(event, "started_at", None)),
    }


def _wait_state_from_heartbeat(event: Any) -> dict[str, Any]:
    return {
        "target": _safe_text(getattr(event, "wait_target", None)),
        "elapsed_seconds": _float_value(getattr(event, "wait_elapsed_seconds", None)),
        "timeout_seconds": _float_value(getattr(event, "wait_timeout_seconds", None)),
        "started_at": _datetime_value(getattr(event, "wait_started_at", None)),
    }


def _confirmation_state_from_event(event: Any) -> dict[str, Any]:
    return {
        "required": True,
        "step_index": _int_value(getattr(event, "step_index", None)),
        "step_name": _safe_text(getattr(event, "step_name", None)),
        "action": _safe_action(getattr(event, "action", None)),
        "target": _safe_text(getattr(event, "target", None)),
        "target_type": _safe_text(getattr(event, "target_type", None)),
        "message": _safe_text(getattr(event, "prompt", None)),
    }


def _artifact_metadata(record: RunRecord) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for path in (record.path / "run.json", record.path / "steps.jsonl"):
        if path.exists():
            artifacts.append({"name": path.name, "kind": path.suffix.lstrip("."), "path": str(path)})
    for item in artifacts:
        if len(artifacts) >= MAX_ARTIFACTS:
            break
        item["user_visible"] = True
    return artifacts[:MAX_ARTIFACTS]


def _normalize_artifact(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "name": _safe_text(item.get("name") or ""),
        "kind": _safe_text(item.get("kind") or ""),
        "path": _safe_text(item.get("path") or ""),
        "user_visible": bool(item.get("user_visible", True)),
    }


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _first_present(*values: object) -> object:
    for value in values:
        if value is not None:
            return value
    return None


def _sequence(value: object) -> Sequence[Any]:
    if isinstance(value, str) or value is None:
        return ()
    if isinstance(value, Sequence):
        return value
    return ()


def _int_value(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_value(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _datetime_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return _safe_text(value)


def _string_value(value: object) -> str:
    return str(getattr(value, "value", value) or "")


def _safe_action(value: object) -> str:
    return _safe_text(value)


def _safe_text(value: object, *, limit: int = 240) -> str:
    text = str(getattr(value, "value", value) or "").replace("\r", " ").replace("\n", " ").strip()
    for marker in ("token=", "password=", "passwd=", "secret=", "api_key=", "apikey="):
        lowered = text.casefold()
        index = lowered.find(marker)
        if index >= 0:
            text = text[: index + len(marker)] + "[redacted]"
    if len(text) > limit:
        return text[: limit - 1].rstrip() + "..."
    return text
