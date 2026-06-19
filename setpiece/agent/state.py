from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from setpiece.runtime_models import RunState, StepState

from .models import (
    AgentConfirmation,
    AgentFailure,
    AgentNotificationRecommendation,
    AgentNotificationRoute,
    AgentRecoveryCheckpoint,
    AgentRoom,
    AgentRunState,
    AgentState,
    AgentStep,
    AgentWait,
)


def initial_agent_state(
    *,
    room: AgentRoom | Mapping[str, Any] | None = None,
    instrument_visible: bool = False,
    instrument_pinned: bool = False,
) -> AgentState:
    return _with_derived_fields(
        AgentState(
            room=_room(room),
            instrument_visible=instrument_visible,
            instrument_pinned=instrument_pinned,
        )
    )


def derive_agent_state(state: AgentState) -> AgentState:
    return _with_derived_fields(state)


def apply_runtime_event(state: AgentState, event: Any) -> AgentState:
    event_type = str(getattr(event, "type", "") or "")
    values = state.model_dump()
    values["updated_at"] = _event_time(event)

    if event_type == "run.started":
        values.update(
            {
                "state": AgentRunState.RUNNING,
                "run_id": _safe_text(getattr(event, "run_id", "")),
                "active_ritual_id": _safe_text(getattr(event, "recipe_id", "")),
                "active_ritual_name": _safe_text(getattr(event, "recipe_name", "")),
                "step_count": _int_value(getattr(event, "steps_total", None)) or 0,
                "current_step": None,
                "wait": None,
                "pending_confirmation": None,
                "latest_failure": None,
                "recovery_checkpoint": None,
                "instrument_visible": True,
            }
        )
    elif event_type == "run.state_changed":
        values["state"] = _agent_state_from_run_state(getattr(event, "state", None))
        if values["state"] == AgentRunState.FAILURE:
            values["latest_failure"] = AgentFailure(
                message=_safe_text(getattr(event, "message", "")),
                occurred_at=_event_time(event),
            )
    elif event_type == "step.started":
        values.update(
            {
                "state": AgentRunState.RUNNING,
                "current_step": _step_from_event(event, state_name="running"),
                "wait": None,
                "pending_confirmation": None,
            }
        )
    elif event_type == "step.waiting":
        values.update(
            {
                "state": AgentRunState.WAITING,
                "current_step": _step_from_event(event, state_name="waiting"),
                "wait": AgentWait(
                    reason=_safe_text(getattr(event, "reason", "")),
                    target=_safe_text(getattr(event, "target", "")),
                    started_at=_datetime_value(getattr(event, "started_at", None)),
                    elapsed_seconds=_float_value(getattr(event, "elapsed_seconds", None)),
                    timeout_seconds=_float_value(getattr(event, "timeout_seconds", None)),
                ),
                "pending_confirmation": None,
            }
        )
    elif event_type == "step.paused":
        values.update(
            {
                "state": AgentRunState.PAUSED,
                "current_step": _step_from_event(event, state_name="paused"),
            }
        )
    elif event_type == "step.resumed":
        resumed_state = _event_value(getattr(event, "state", "")) or "running"
        values.update(
            {
                "state": AgentRunState.WAITING if resumed_state == "waiting" else AgentRunState.RUNNING,
                "current_step": _step_from_event(event, state_name=resumed_state),
            }
        )
    elif event_type == "confirmation.requested":
        values.update(
            {
                "state": AgentRunState.CONFIRMATION,
                "current_step": _step_from_event(event, state_name="confirmation"),
                "pending_confirmation": AgentConfirmation(
                    confirmation_id=_safe_text(getattr(event, "confirmation_id", "")),
                    step_index=_int_value(getattr(event, "step_index", None)),
                    step_name=_safe_text(getattr(event, "step_name", "")),
                    action=_safe_text(getattr(event, "action", "")),
                    prompt=_safe_text(getattr(event, "prompt", ""), limit=1000),
                    target=_safe_text(getattr(event, "target", "")),
                    target_type=_safe_text(getattr(event, "target_type", "")),
                ),
            }
        )
    elif event_type == "confirmation.resolved":
        approved = bool(getattr(event, "approved", False))
        values["pending_confirmation"] = None
        values["state"] = AgentRunState.RUNNING if approved else AgentRunState.STOPPED
        values["current_step"] = _step_from_event(
            event,
            state_name="running" if approved else "cancelled",
            message=_safe_text(getattr(event, "message", "")),
        )
    elif event_type == "step.finished":
        step_state = _event_value(getattr(event, "state", ""))
        message = _safe_text(getattr(event, "message", ""))
        values["current_step"] = _step_from_event(event, state_name=step_state, message=message)
        values["wait"] = None
        values["pending_confirmation"] = None
        if step_state == StepState.FAILED.value or _event_blocked(event):
            values["state"] = AgentRunState.FAILURE
            values["latest_failure"] = AgentFailure(
                message=message,
                step_index=_int_value(getattr(event, "step_index", None)),
                step_name=_safe_text(getattr(event, "step_name", "")),
                action=_safe_text(getattr(event, "action", "")),
                occurred_at=_event_time(event),
            )
    elif event_type == "heartbeat":
        run_state = _agent_state_from_run_state(getattr(event, "run_state", None))
        step_state = _event_value(getattr(event, "step_state", ""))
        values["state"] = run_state
        values["current_step"] = AgentStep(
            index=_int_value(getattr(event, "step_index", None)),
            name=_safe_text(getattr(event, "step_name", "")),
            action=_safe_text(getattr(event, "action", "")),
            state=step_state,
        )
        wait = _wait_from_heartbeat(event)
        if wait is not None:
            values["wait"] = wait
    elif event_type == "run.finished":
        final_state = _agent_state_from_run_state(getattr(event, "state", None))
        values["state"] = final_state
        values["wait"] = None
        values["pending_confirmation"] = None
        if final_state == AgentRunState.INTERRUPTED:
            values["recovery_checkpoint"] = AgentRecoveryCheckpoint(
                run_id=_safe_text(getattr(event, "run_id", "")),
                interrupted=True,
                safe_next_actions=("inspect_run", "doctor", "start_fresh"),
                last_step=state.current_step,
            )
        if final_state == AgentRunState.FAILURE and values.get("latest_failure") is None:
            values["latest_failure"] = AgentFailure(
                message=_safe_text(getattr(event, "message", "")),
                occurred_at=_event_time(event),
            )

    return _with_derived_fields(AgentState.model_validate(values))


def apply_ritual_state(
    state: AgentState,
    ritual_state: Mapping[str, Any],
    *,
    room: AgentRoom | Mapping[str, Any] | None = None,
) -> AgentState:
    active = _mapping(ritual_state.get("active_run"))
    last_run = _mapping(ritual_state.get("last_run"))
    recovery = _mapping(ritual_state.get("recovery"))
    values = state.model_dump()
    values["updated_at"] = datetime.now(timezone.utc)
    if room is not None:
        values["room"] = _room(room)
    recipe_id = _safe_text(ritual_state.get("recipe_id", ""))
    if recipe_id:
        values["active_ritual_id"] = recipe_id

    active_state = _safe_text(active.get("state") or active.get("status") or "")
    if active_state and active_state != "idle":
        values["state"] = _agent_state_from_text(active_state)
        values["run_id"] = _safe_text(active.get("run_id", values.get("run_id", "")))
        values["step_count"] = _int_value(active.get("steps_total")) or values.get("step_count", 0)
        values["current_step"] = _step_from_mapping(_mapping(active.get("current_step")))
        values["wait"] = _wait_from_mapping(_mapping(active.get("wait")))
        values["pending_confirmation"] = _confirmation_from_mapping(_mapping(active.get("confirmation")))
        if values["state"] == AgentRunState.FAILURE:
            current = _mapping(active.get("current_step"))
            values["latest_failure"] = AgentFailure(
                message=_safe_text(active.get("message") or current.get("message") or ""),
                step_index=_int_value(current.get("index") or current.get("step_index")),
                step_name=_safe_text(current.get("name") or current.get("step_name") or ""),
                action=_safe_text(current.get("action") or ""),
            )

    if bool(recovery.get("interrupted")):
        values["state"] = AgentRunState.RECOVERY
        values["recovery_checkpoint"] = AgentRecoveryCheckpoint(
            run_id=_safe_text(active.get("run_id") or values.get("run_id") or ""),
            interrupted=True,
            repaired_status=_safe_text(recovery.get("repaired_status") or ""),
            safe_next_actions=tuple(
                _safe_text(item)
                for item in _sequence(recovery.get("safe_next_actions"))
                if _safe_text(item)
            ),
            last_step=_step_from_mapping(_mapping(last_run.get("last_step"))),
        )
    elif _safe_text(last_run.get("state")) == "interrupted":
        values["state"] = AgentRunState.INTERRUPTED

    return _with_derived_fields(AgentState.model_validate(values))


def _with_derived_fields(state: AgentState) -> AgentState:
    values = state.model_dump()
    values["tray_tooltip"] = _tray_tooltip(state)
    values["notification_recommendation"] = _notification_recommendation(state)
    return AgentState.model_validate(values)


def _tray_tooltip(state: AgentState) -> str:
    label = state.active_ritual_name or state.active_ritual_id
    if state.state == AgentRunState.IDLE:
        return "Setpiece - Ready"
    if label:
        return f"Setpiece - {_state_label(state.state)}: {label}"
    return f"Setpiece - {_state_label(state.state)}"


def _notification_recommendation(state: AgentState) -> AgentNotificationRecommendation:
    if state.state in {AgentRunState.CONFIRMATION, AgentRunState.FAILURE, AgentRunState.RECOVERY}:
        return AgentNotificationRecommendation(
            route=AgentNotificationRoute.OPEN_REVIEW,
            reason=state.state.value,
        )
    if state.state in {AgentRunState.WAITING, AgentRunState.PAUSED, AgentRunState.INTERRUPTED}:
        return AgentNotificationRecommendation(
            route=AgentNotificationRoute.OPEN_INSTRUMENT,
            reason=state.state.value,
        )
    return AgentNotificationRecommendation()


def _state_label(state: AgentRunState) -> str:
    if state == AgentRunState.PREFLIGHT:
        return "Preflight"
    if state == AgentRunState.CONFIRMATION:
        return "Confirmation"
    return state.value.replace("_", " ").title()


def _agent_state_from_run_state(value: object) -> AgentRunState:
    text = _event_value(value)
    if text == RunState.RUNNING.value:
        return AgentRunState.RUNNING
    if text == RunState.WAITING.value:
        return AgentRunState.WAITING
    if text == RunState.PAUSED.value:
        return AgentRunState.PAUSED
    if text == RunState.CONFIRMING.value:
        return AgentRunState.CONFIRMATION
    if text == RunState.SUCCESS.value:
        return AgentRunState.COMPLETED
    if text == RunState.STOPPED.value or text == RunState.STOPPING.value:
        return AgentRunState.STOPPED
    if text == RunState.FAILED.value:
        return AgentRunState.FAILURE
    if text == RunState.INTERRUPTED.value:
        return AgentRunState.INTERRUPTED
    return _agent_state_from_text(text)


def _agent_state_from_text(value: object) -> AgentRunState:
    text = _safe_text(value).casefold()
    mapping = {
        "idle": AgentRunState.IDLE,
        "ready": AgentRunState.READY,
        "preflight": AgentRunState.PREFLIGHT,
        "starting": AgentRunState.PREFLIGHT,
        "running": AgentRunState.RUNNING,
        "waiting": AgentRunState.WAITING,
        "confirming": AgentRunState.CONFIRMATION,
        "confirmation": AgentRunState.CONFIRMATION,
        "paused": AgentRunState.PAUSED,
        "failed": AgentRunState.FAILURE,
        "failure": AgentRunState.FAILURE,
        "blocked": AgentRunState.FAILURE,
        "recovery": AgentRunState.RECOVERY,
        "success": AgentRunState.COMPLETED,
        "completed": AgentRunState.COMPLETED,
        "stopped": AgentRunState.STOPPED,
        "interrupted": AgentRunState.INTERRUPTED,
    }
    return mapping.get(text, AgentRunState.IDLE)


def _step_from_event(event: Any, *, state_name: str, message: str = "") -> AgentStep:
    return AgentStep(
        index=_int_value(getattr(event, "step_index", None)),
        name=_safe_text(getattr(event, "step_name", "")),
        action=_safe_text(getattr(event, "action", "")),
        state=_safe_text(state_name),
        message=message,
    )


def _step_from_mapping(data: Mapping[str, Any]) -> AgentStep | None:
    if not data:
        return None
    return AgentStep(
        index=_int_value(data.get("index") or data.get("step_index")),
        name=_safe_text(data.get("name") or data.get("step_name") or ""),
        action=_safe_text(data.get("action") or ""),
        state=_safe_text(data.get("state") or data.get("status") or ""),
        message=_safe_text(data.get("message") or ""),
    )


def _wait_from_mapping(data: Mapping[str, Any]) -> AgentWait | None:
    if not data:
        return None
    target = _safe_text(data.get("target") or "")
    reason = _safe_text(data.get("reason") or "")
    started_at = _datetime_value(data.get("started_at"))
    elapsed = _float_value(data.get("elapsed_seconds"))
    timeout = _float_value(data.get("timeout_seconds"))
    if not any((target, reason, started_at, elapsed is not None, timeout is not None)):
        return None
    return AgentWait(
        reason=reason,
        target=target,
        started_at=started_at,
        elapsed_seconds=elapsed,
        timeout_seconds=timeout,
    )


def _wait_from_heartbeat(event: Any) -> AgentWait | None:
    target = _safe_text(getattr(event, "wait_target", ""))
    started_at = _datetime_value(getattr(event, "wait_started_at", None))
    elapsed = _float_value(getattr(event, "wait_elapsed_seconds", None))
    timeout = _float_value(getattr(event, "wait_timeout_seconds", None))
    if not any((target, started_at, elapsed is not None, timeout is not None)):
        return None
    return AgentWait(
        reason="heartbeat",
        target=target,
        started_at=started_at,
        elapsed_seconds=elapsed,
        timeout_seconds=timeout,
    )


def _confirmation_from_mapping(data: Mapping[str, Any]) -> AgentConfirmation | None:
    if not data or not bool(data.get("required")):
        return None
    return AgentConfirmation(
        step_index=_int_value(data.get("step_index")),
        step_name=_safe_text(data.get("step_name") or ""),
        action=_safe_text(data.get("action") or ""),
        prompt=_safe_text(data.get("message") or data.get("prompt") or "", limit=1000),
        target=_safe_text(data.get("target") or ""),
        target_type=_safe_text(data.get("target_type") or ""),
    )


def _event_blocked(event: Any) -> bool:
    metadata = _mapping(getattr(event, "metadata", None))
    target_resolution = _mapping(metadata.get("target_resolution"))
    if str(target_resolution.get("status") or "").casefold() == "blocked":
        return True
    return "blocked" in _safe_text(getattr(event, "message", "")).casefold()


def _room(value: AgentRoom | Mapping[str, Any] | None) -> AgentRoom | None:
    if value is None or isinstance(value, AgentRoom):
        return value
    return AgentRoom(
        id=_safe_text(value.get("id") or value.get("room_id") or ""),
        name=_safe_text(value.get("name") or ""),
        canvas_id=_safe_text(value.get("canvas_id") or ""),
    )


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _sequence(value: object) -> Sequence[Any]:
    if value is None or isinstance(value, str):
        return ()
    if isinstance(value, Sequence):
        return value
    return ()


def _event_value(value: object) -> str:
    return str(getattr(value, "value", value) or "")


def _event_time(event: Any) -> datetime:
    return _datetime_value(getattr(event, "occurred_at", None)) or datetime.now(timezone.utc)


def _datetime_value(value: object) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return None
    return None


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
