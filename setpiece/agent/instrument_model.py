from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime, timezone
from enum import StrEnum
import re
from typing import Any

from setpiece.agent.models import AgentRunState, AgentState
from setpiece.agent.state import apply_ritual_state, apply_runtime_event, initial_agent_state


INSTRUMENT_MODEL_SCHEMA_VERSION = "setpiece.agent.instrument.v1"


class InstrumentState(StrEnum):
    READY = "ready"
    PREFLIGHT = "preflight"
    RUNNING = "running"
    WAITING = "waiting"
    CONFIRMATION = "confirmation"
    FAILURE = "failure"
    RECOVERY = "recovery"
    COMPLETED = "completed"
    STOPPED = "stopped"
    INTERRUPTED = "interrupted"


class InstrumentActionRole(StrEnum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    LINK = "link"


@dataclass(frozen=True, slots=True)
class InstrumentAction:
    action: str
    label: str
    role: InstrumentActionRole = InstrumentActionRole.SECONDARY
    enabled: bool = True
    reason: str = ""
    tone: str = "normal"

    def to_dict(self) -> dict[str, Any]:
        return _dataclass_to_dict(self)


@dataclass(frozen=True, slots=True)
class InstrumentFact:
    label: str
    value: str
    severity: str = "info"

    def to_dict(self) -> dict[str, Any]:
        return _dataclass_to_dict(self)


@dataclass(frozen=True, slots=True)
class InstrumentProgress:
    step_index: int | None = None
    total_steps: int = 0
    completed_steps: int = 0
    steps_not_run: int = 0
    elapsed_seconds: float | None = None
    timeout_seconds: float | None = None
    next_check_seconds: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return _dataclass_to_dict(self)


@dataclass(frozen=True, slots=True)
class InstrumentWait:
    dependency: str
    user_action_required: bool = False
    elapsed_seconds: float | None = None
    timeout_seconds: float | None = None
    next_check_seconds: float | None = None
    check_again_available: bool = False

    def to_dict(self) -> dict[str, Any]:
        return _dataclass_to_dict(self)


@dataclass(frozen=True, slots=True)
class InstrumentConfirmation:
    consequence: str
    target: str
    preserved_work: str
    safe_negative_path: str
    remembered_approval_eligible: bool = False
    remembered_approval_applied: bool = False
    remembered_approval_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _dataclass_to_dict(self)


@dataclass(frozen=True, slots=True)
class InstrumentFailure:
    failed_step: str
    cause: str
    completed_work: str
    steps_not_run: int = 0
    remedy: str = ""
    run_log_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _dataclass_to_dict(self)


@dataclass(frozen=True, slots=True)
class InstrumentRecovery:
    checkpoint: str
    repair_steps: tuple[str, ...] = ()
    progress: str = ""
    resume_available: bool = True

    def to_dict(self) -> dict[str, Any]:
        return _dataclass_to_dict(self)


@dataclass(frozen=True, slots=True)
class InstrumentHistory:
    collapsed: bool = True
    summary: str = ""
    entries: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return _dataclass_to_dict(self)


@dataclass(frozen=True, slots=True)
class InstrumentSources:
    agent_state: AgentState | None = None
    runtime_events: Sequence[Any] = ()
    ritual_state: Mapping[str, Any] | None = None
    doctor: Any = None
    dry_run: Any = None
    target_readiness: Any = None
    recipe_transparency: Mapping[str, Any] | None = None
    remembered_approvals: Any = None
    run_logs: Sequence[Any] = ()
    now: datetime | None = None
    show_history: bool = False


@dataclass(frozen=True, slots=True)
class InstrumentModel:
    schema_version: str
    state: InstrumentState
    ritual_id: str
    ritual_name: str
    intent: str
    headline: str
    subheadline: str = ""
    affected: tuple[str, ...] = ()
    prerequisites: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    facts: tuple[InstrumentFact, ...] = ()
    step_count: int = 0
    confirmation_count: int = 0
    current_verb: str = ""
    next_step: str = ""
    progress: InstrumentProgress = InstrumentProgress()
    wait: InstrumentWait | None = None
    confirmation: InstrumentConfirmation | None = None
    failure: InstrumentFailure | None = None
    recovery: InstrumentRecovery | None = None
    history: InstrumentHistory = InstrumentHistory()
    actions: tuple[InstrumentAction, ...] = ()
    details: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return _dataclass_to_dict(self)


def build_instrument_model(
    sources: InstrumentSources | None = None,
    **overrides: Any,
) -> InstrumentModel:
    resolved = _sources_from_args(sources, overrides)
    now = resolved.now or datetime.now(timezone.utc)
    ritual_state = _mapping(resolved.ritual_state)
    transparency = _mapping(resolved.recipe_transparency)
    doctor = _data_mapping(resolved.doctor) or _mapping(ritual_state.get("doctor"))
    dry_run = _data_mapping(resolved.dry_run) or _mapping(ritual_state.get("dry_run"))
    target = _data_mapping(resolved.target_readiness)
    agent_state = _build_agent_state(resolved)

    state = _instrument_state(agent_state)
    ritual_id = _first_text(
        agent_state.active_ritual_id,
        ritual_state.get("recipe_id"),
        transparency.get("recipe_id"),
        doctor.get("recipe_id"),
        fallback="",
    )
    ritual_name = _ritual_name(agent_state, transparency, doctor, ritual_id)
    intent = _intent(transparency, ritual_name)
    active_run = _mapping(ritual_state.get("active_run"))
    last_run = _mapping(ritual_state.get("last_run"))
    recovery_state = _mapping(ritual_state.get("recovery"))
    ordered_steps = _ordered_steps(transparency, dry_run)
    step_count = _step_count(agent_state, active_run, dry_run, ordered_steps)
    confirmation_count = _confirmation_count(transparency, dry_run, active_run)
    current_step = _current_step(agent_state, active_run)
    completed_steps = _completed_steps(current_step, active_run, last_run)
    steps_not_run = _steps_not_run(current_step, step_count, last_run)
    elapsed = _elapsed_seconds(active_run, now)

    progress = InstrumentProgress(
        step_index=_int_value(current_step.get("index")),
        total_steps=step_count,
        completed_steps=completed_steps,
        steps_not_run=steps_not_run,
        elapsed_seconds=elapsed,
    )
    affected = _affected_items(transparency, target)
    prerequisites = _prerequisites(transparency, doctor, dry_run)
    warnings = _warnings(doctor, target)
    facts = _facts(
        step_count=step_count,
        confirmation_count=confirmation_count,
        affected=affected,
        prerequisites=prerequisites,
        warnings=warnings,
    )
    history = _history(agent_state, last_run, show_history=resolved.show_history)

    wait = None
    confirmation = None
    failure = None
    recovery = None
    current_verb = ""
    next_step = ""
    details = _details(transparency)

    if state == InstrumentState.RUNNING:
        current_verb = _current_verb(current_step)
        next_step = _next_step(current_step, ordered_steps)
        headline = current_verb or "Running ritual"
        subheadline = _step_position(current_step, step_count)
        actions = _running_actions(current_step, active_run)
    elif state == InstrumentState.WAITING:
        wait = _wait(agent_state, active_run, current_step)
        progress = InstrumentProgress(
            step_index=progress.step_index,
            total_steps=progress.total_steps,
            completed_steps=progress.completed_steps,
            steps_not_run=progress.steps_not_run,
            elapsed_seconds=wait.elapsed_seconds,
            timeout_seconds=wait.timeout_seconds,
            next_check_seconds=wait.next_check_seconds,
        )
        current_verb = _current_verb(current_step) or "Waiting"
        next_step = _next_step(current_step, ordered_steps)
        headline = f"Waiting for {wait.dependency}" if wait.dependency else "Waiting"
        subheadline = (
            "User action required"
            if wait.user_action_required
            else _step_position(current_step, step_count)
        )
        actions = _waiting_actions(wait)
    elif state == InstrumentState.CONFIRMATION:
        confirmation = _confirmation(agent_state, active_run, last_run, resolved)
        headline = _confirmation_headline(confirmation)
        subheadline = confirmation.safe_negative_path
        actions = _confirmation_actions(confirmation)
    elif state == InstrumentState.FAILURE:
        failure = _failure(
            agent_state,
            current_step,
            active_run,
            last_run,
            target,
            doctor,
            resolved.run_logs,
        )
        headline = f"{failure.failed_step} failed" if failure.failed_step else "Ritual failed"
        subheadline = failure.cause
        actions = _failure_actions(failure)
    elif state == InstrumentState.RECOVERY:
        recovery = _recovery(agent_state, recovery_state, last_run)
        headline = "Recovery checkpoint available"
        subheadline = recovery.progress
        actions = _recovery_actions(recovery)
    elif state == InstrumentState.INTERRUPTED:
        recovery = _recovery(agent_state, recovery_state, last_run)
        headline = "Ritual was interrupted"
        subheadline = history.summary
        actions = _interrupted_actions(_run_log_path(last_run, resolved.run_logs))
    elif state in {InstrumentState.COMPLETED, InstrumentState.STOPPED}:
        headline = _terminal_headline(state, ritual_name)
        subheadline = _safe_text(last_run.get("final_message") or active_run.get("message") or "")
        actions = _terminal_actions(_run_log_path(last_run, resolved.run_logs))
    else:
        headline = "Ready for preflight" if state == InstrumentState.PREFLIGHT else "Ready"
        subheadline = intent
        actions = _ready_actions(ritual_id, doctor)

    return InstrumentModel(
        schema_version=INSTRUMENT_MODEL_SCHEMA_VERSION,
        state=state,
        ritual_id=ritual_id,
        ritual_name=ritual_name,
        intent=intent,
        headline=headline,
        subheadline=subheadline,
        affected=affected,
        prerequisites=prerequisites,
        warnings=warnings,
        facts=facts,
        step_count=step_count,
        confirmation_count=confirmation_count,
        current_verb=current_verb,
        next_step=next_step,
        progress=progress,
        wait=wait,
        confirmation=confirmation,
        failure=failure,
        recovery=recovery,
        history=history,
        actions=actions,
        details=details,
    )


def _sources_from_args(
    sources: InstrumentSources | None,
    overrides: Mapping[str, Any],
) -> InstrumentSources:
    if sources is None:
        return InstrumentSources(**dict(overrides))
    if not overrides:
        return sources
    values = _dataclass_to_dict(sources)
    values.update(overrides)
    return InstrumentSources(**values)


def _build_agent_state(sources: InstrumentSources) -> AgentState:
    state = sources.agent_state or initial_agent_state()
    for event in sources.runtime_events:
        state = apply_runtime_event(state, event)
    if sources.ritual_state and sources.agent_state is None and not sources.runtime_events:
        state = apply_ritual_state(state, sources.ritual_state)
    return state


def _instrument_state(agent_state: AgentState) -> InstrumentState:
    mapping = {
        AgentRunState.IDLE: InstrumentState.READY,
        AgentRunState.READY: InstrumentState.READY,
        AgentRunState.PREFLIGHT: InstrumentState.PREFLIGHT,
        AgentRunState.RUNNING: InstrumentState.RUNNING,
        AgentRunState.PAUSED: InstrumentState.RUNNING,
        AgentRunState.WAITING: InstrumentState.WAITING,
        AgentRunState.CONFIRMATION: InstrumentState.CONFIRMATION,
        AgentRunState.FAILURE: InstrumentState.FAILURE,
        AgentRunState.RECOVERY: InstrumentState.RECOVERY,
        AgentRunState.COMPLETED: InstrumentState.COMPLETED,
        AgentRunState.STOPPED: InstrumentState.STOPPED,
        AgentRunState.INTERRUPTED: InstrumentState.INTERRUPTED,
    }
    return mapping[agent_state.state]


def _ritual_name(
    agent_state: AgentState,
    transparency: Mapping[str, Any],
    doctor: Mapping[str, Any],
    ritual_id: str,
) -> str:
    return _first_text(
        agent_state.active_ritual_name,
        transparency.get("recipe_name"),
        doctor.get("recipe_name"),
        _title_from_id(ritual_id),
        fallback="Ritual",
    )


def _intent(transparency: Mapping[str, Any], ritual_name: str) -> str:
    purpose = _safe_text(transparency.get("purpose"))
    if purpose:
        return purpose
    for item in _sequence(transparency.get("plain_language_plan")):
        text = _safe_text(item)
        if text:
            return text.removeprefix("Purpose:").strip() or text
    return f"Prepare {ritual_name}."


def _ordered_steps(
    transparency: Mapping[str, Any],
    dry_run: Mapping[str, Any],
) -> tuple[Mapping[str, Any], ...]:
    rows = [
        _mapping(item)
        for item in _sequence(transparency.get("ordered_steps"))
        if isinstance(item, Mapping)
    ]
    if rows:
        return tuple(rows)
    return tuple(
        _mapping(item)
        for item in _sequence(dry_run.get("step_summaries"))
        if isinstance(item, Mapping)
    )


def _step_count(
    agent_state: AgentState,
    active_run: Mapping[str, Any],
    dry_run: Mapping[str, Any],
    ordered_steps: Sequence[Mapping[str, Any]],
) -> int:
    return _first_int(
        agent_state.step_count,
        active_run.get("steps_total"),
        dry_run.get("planned_step_count"),
        len(ordered_steps),
    )


def _confirmation_count(
    transparency: Mapping[str, Any],
    dry_run: Mapping[str, Any],
    active_run: Mapping[str, Any],
) -> int:
    active_confirmation = _mapping(active_run.get("confirmation"))
    return _first_int(
        dry_run.get("confirmation_count"),
        len(_sequence(transparency.get("confirmations"))),
        1 if bool(active_confirmation.get("required")) else 0,
    )


def _current_step(agent_state: AgentState, active_run: Mapping[str, Any]) -> dict[str, Any]:
    if agent_state.current_step is not None:
        return {
            "index": agent_state.current_step.index,
            "name": agent_state.current_step.name,
            "action": agent_state.current_step.action,
            "state": agent_state.current_step.state,
            "message": agent_state.current_step.message,
        }
    return _mapping(active_run.get("current_step"))


def _completed_steps(
    current_step: Mapping[str, Any],
    active_run: Mapping[str, Any],
    last_run: Mapping[str, Any],
) -> int:
    explicit = _int_value(last_run.get("steps_completed"))
    if explicit is not None:
        return explicit
    explicit = _int_value(active_run.get("steps_completed"))
    if explicit is not None:
        return explicit
    index = _int_value(current_step.get("index"))
    if index is None:
        return 0
    state = _safe_text(current_step.get("state")).casefold()
    return index if state in {"success", "skipped", "dry-run"} else max(0, index - 1)


def _steps_not_run(
    current_step: Mapping[str, Any],
    step_count: int,
    last_run: Mapping[str, Any],
) -> int:
    explicit = _int_value(last_run.get("not_run_count"))
    if explicit is not None:
        return max(0, explicit)
    index = _int_value(current_step.get("index"))
    if index is None or step_count <= 0:
        return 0
    return max(0, step_count - index)


def _elapsed_seconds(active_run: Mapping[str, Any], now: datetime) -> float | None:
    explicit = _float_value(active_run.get("elapsed_seconds"))
    if explicit is not None:
        return explicit
    started_at = _datetime_value(active_run.get("started_at"))
    if started_at is None:
        return None
    return max(0.0, (now - started_at).total_seconds())


def _affected_items(
    transparency: Mapping[str, Any],
    target: Mapping[str, Any],
) -> tuple[str, ...]:
    rows: list[str] = []
    for key, prefix in (("affected_apps", "App"), ("affected_settings", "Setting")):
        for item in _sequence(transparency.get(key)):
            text = _safe_text(item)
            if text:
                rows.append(f"{prefix}: {text}")
    target_name = _first_text(
        target.get("target_display_name"),
        _mapping(target.get("target")).get("display_name"),
        fallback="",
    )
    if target_name:
        rows.append(f"Target: {target_name}")
    setup_fields = [
        _safe_text(_mapping(item).get("label") or _mapping(item).get("name"))
        for item in _sequence(transparency.get("setup_fields"))
        if isinstance(item, Mapping) and bool(item.get("editable", True))
    ]
    for label in setup_fields[:4]:
        if label:
            rows.append(f"Setup: {label}")
    for item in _sequence(transparency.get("ordered_steps")):
        step = _mapping(item)
        action = _safe_text(step.get("action"))
        label = _affected_from_action(action)
        if label:
            rows.append(label)
    return tuple(dict.fromkeys(rows))


def _affected_from_action(action: str) -> str:
    if action.startswith("browser."):
        return "App: Browser"
    if action == "app.launch":
        return "App: Local app"
    if action.startswith("window.") or action.startswith("wait."):
        return "App: Desktop window"
    if action.startswith("target."):
        return "Target: Local target readiness"
    return ""


def _prerequisites(
    transparency: Mapping[str, Any],
    doctor: Mapping[str, Any],
    dry_run: Mapping[str, Any],
) -> tuple[str, ...]:
    rows: list[str] = []
    rows.extend(f"Input: {item}" for item in _string_sequence(doctor.get("missing_inputs")))
    rows.extend(
        f"Capability: {item}" for item in _string_sequence(doctor.get("missing_capabilities"))
    )
    for item in _sequence(doctor.get("variables")):
        row = _mapping(item)
        if row.get("status") == "missing":
            name = _safe_text(row.get("name"))
            if name:
                rows.append(f"Input: {name}")
    for item in _sequence(doctor.get("capabilities")):
        row = _mapping(item)
        status = _safe_text(row.get("status")).casefold()
        if status and status not in {"ok", "configured"}:
            name = _safe_text(row.get("id") or row.get("name"))
            if name:
                rows.append(f"Capability: {name}")
    rows.extend(f"Input: {item}" for item in _string_sequence(dry_run.get("unresolved_inputs")))
    preflight = _mapping(transparency.get("live_preflight_requirements"))
    rows.extend(f"OS: {item}" for item in _string_sequence(preflight.get("os")))
    rows.extend(
        f"Capability: {item}" for item in _string_sequence(preflight.get("required_capabilities"))
    )
    for item in _sequence(preflight.get("expected_windows")):
        row = _mapping(item)
        label = _first_text(row.get("title_contains"), row.get("process_name"), fallback="")
        if label:
            rows.append(f"Window: {label}")
    for item in _sequence(preflight.get("expected_labels")):
        row = _mapping(item)
        label = _first_text(row.get("text"), row.get("window_title_contains"), fallback="")
        if label:
            rows.append(f"Label: {label}")
    return tuple(dict.fromkeys(row for row in rows if row))


def _warnings(doctor: Mapping[str, Any], target: Mapping[str, Any]) -> tuple[str, ...]:
    rows: list[str] = []
    rows.extend(_string_sequence(doctor.get("errors")))
    rows.extend(_string_sequence(doctor.get("warnings")))
    for item in _sequence(doctor.get("checks")):
        row = _mapping(item)
        status = _safe_text(row.get("status")).casefold()
        if status in {"error", "failed", "incompatible", "warn", "warning"}:
            message = _safe_text(row.get("message"))
            if message:
                rows.append(message)
    rows.extend(_string_sequence(target.get("unresolved_questions")))
    recommendation = _safe_text(target.get("recommended_next_action"))
    if (
        recommendation
        and _safe_text(target.get("state")).casefold() not in {"ready", "running"}
    ):
        rows.append(recommendation)
    return tuple(dict.fromkeys(row for row in rows if row))


def _facts(
    *,
    step_count: int,
    confirmation_count: int,
    affected: Sequence[str],
    prerequisites: Sequence[str],
    warnings: Sequence[str],
) -> tuple[InstrumentFact, ...]:
    return (
        InstrumentFact("Steps", str(max(0, step_count))),
        InstrumentFact("Confirmations", str(max(0, confirmation_count))),
        InstrumentFact("Affected", _count_label(affected, "item")),
        InstrumentFact("Prerequisites", _count_label(prerequisites, "item")),
        InstrumentFact(
            "Warnings",
            _count_label(warnings, "warning"),
            severity="warning" if warnings else "info",
        ),
    )


def _details(transparency: Mapping[str, Any]) -> tuple[str, ...]:
    details = []
    for item in _sequence(transparency.get("plain_language_plan")):
        text = _safe_text(item, limit=400)
        if text:
            details.append(text)
    for item in _sequence(transparency.get("what_setpiece_will_never_do")):
        text = _safe_text(item, limit=400)
        if text:
            details.append(text)
    return tuple(details)


def _current_verb(current_step: Mapping[str, Any]) -> str:
    name = _safe_text(current_step.get("name"))
    if name:
        return name
    action = _safe_text(current_step.get("action"))
    if action == "app.launch":
        return "Launching app"
    if action in {"window.wait", "wait.for_window"}:
        return "Waiting for window"
    if action == "target.inspect":
        return "Checking target readiness"
    if action == "target.wait_state":
        return "Waiting for target readiness"
    if action.startswith("assert."):
        return "Checking prerequisite"
    if action.startswith("human."):
        return "Waiting for operator review"
    if action.startswith("browser."):
        return "Using browser"
    return "Running step" if action else ""


def _next_step(
    current_step: Mapping[str, Any],
    ordered_steps: Sequence[Mapping[str, Any]],
) -> str:
    index = _int_value(current_step.get("index"))
    if index is None:
        return ""
    for step in ordered_steps:
        step_index = _int_value(step.get("index"))
        if step_index == index + 1:
            return _first_text(step.get("summary"), step.get("name"), fallback="")
    return ""


def _step_position(current_step: Mapping[str, Any], step_count: int) -> str:
    index = _int_value(current_step.get("index"))
    if index is None or step_count <= 0:
        return ""
    return f"Step {index} of {step_count}"


def _running_actions(
    current_step: Mapping[str, Any],
    active_run: Mapping[str, Any],
) -> tuple[InstrumentAction, ...]:
    actions: list[InstrumentAction] = []
    if _pause_is_safe(current_step, active_run):
        actions.append(
            InstrumentAction("pause_ritual", "Pause", role=InstrumentActionRole.SECONDARY)
        )
    actions.append(
        InstrumentAction(
            "stop_ritual",
            "Stop",
            role=InstrumentActionRole.SECONDARY,
            tone="destructive",
        )
    )
    return tuple(actions)


def _pause_is_safe(current_step: Mapping[str, Any], active_run: Mapping[str, Any]) -> bool:
    explicit = _bool_or_none(active_run.get("safe_to_pause"))
    if explicit is not None:
        return explicit
    current = _mapping(active_run.get("current_step"))
    explicit = _bool_or_none(current.get("safe_to_pause"))
    if explicit is not None:
        return explicit
    action = _safe_text(current_step.get("action"))
    return action.startswith(("wait.", "assert.", "human.")) or action in {
        "window.wait",
        "target.inspect",
        "target.wait_state",
        "browser.wait_media_playing",
    }


def _wait(
    agent_state: AgentState,
    active_run: Mapping[str, Any],
    current_step: Mapping[str, Any],
) -> InstrumentWait:
    wait_data = _mapping(active_run.get("wait"))
    agent_wait = agent_state.wait
    dependency = _first_text(
        wait_data.get("dependency"),
        wait_data.get("target"),
        agent_wait.target if agent_wait else "",
        wait_data.get("reason"),
        agent_wait.reason if agent_wait else "",
        fallback="dependency",
    )
    elapsed = _first_float(
        wait_data.get("elapsed_seconds"),
        agent_wait.elapsed_seconds if agent_wait else None,
    )
    timeout = _first_float(
        wait_data.get("timeout_seconds"),
        agent_wait.timeout_seconds if agent_wait else None,
    )
    user_action = _user_action_required(wait_data)
    next_check = _first_float(
        wait_data.get("next_check_seconds"),
        wait_data.get("check_after_seconds"),
    )
    check_again = _check_again_available(wait_data, current_step, user_action)
    return InstrumentWait(
        dependency=dependency,
        user_action_required=user_action,
        elapsed_seconds=elapsed,
        timeout_seconds=timeout,
        next_check_seconds=next_check,
        check_again_available=check_again,
    )


def _user_action_required(wait_data: Mapping[str, Any]) -> bool:
    explicit = _bool_or_none(wait_data.get("user_action_required"))
    if explicit is not None:
        return explicit
    text = " ".join(
        _safe_text(wait_data.get(key)).casefold()
        for key in ("reason", "dependency", "target", "message")
    )
    return any(token in text for token in ("user", "manual", "login", "log in", "operator"))


def _check_again_available(
    wait_data: Mapping[str, Any],
    current_step: Mapping[str, Any],
    user_action_required: bool,
) -> bool:
    explicit = _bool_or_none(
        _first_present(
            wait_data.get("check_again_available"),
            wait_data.get("can_check_again"),
            wait_data.get("idempotent"),
        )
    )
    if explicit is not None:
        return explicit
    if user_action_required:
        return False
    action = _safe_text(current_step.get("action"))
    return action.startswith(("wait.", "assert.")) or action in {
        "window.wait",
        "target.inspect",
        "target.wait_state",
    }


def _waiting_actions(wait: InstrumentWait) -> tuple[InstrumentAction, ...]:
    actions = []
    if wait.check_again_available:
        actions.append(
            InstrumentAction("check_again", "Check again", role=InstrumentActionRole.PRIMARY)
        )
    actions.append(
        InstrumentAction(
            "stop_ritual",
            "Stop",
            role=InstrumentActionRole.SECONDARY,
            tone="destructive",
        )
    )
    return tuple(actions)


def _confirmation(
    agent_state: AgentState,
    active_run: Mapping[str, Any],
    last_run: Mapping[str, Any],
    sources: InstrumentSources,
) -> InstrumentConfirmation:
    confirmation = agent_state.pending_confirmation
    active_confirmation = _mapping(active_run.get("confirmation"))
    consequence = _clean_confirmation_text(
        _first_text(
            confirmation.prompt if confirmation else "",
            active_confirmation.get("message"),
            active_confirmation.get("prompt"),
            fallback="Continue this step.",
        )
    )
    target = _first_text(
        confirmation.target if confirmation else "",
        active_confirmation.get("target"),
        fallback="current target",
    )
    completed = _first_int(last_run.get("steps_completed"), active_run.get("steps_completed"), 0)
    preserved_work = (
        f"Completed work remains recorded ({completed} step{'s' if completed != 1 else ''})."
        if completed
        else "No completed work will be discarded."
    )
    safe_negative = "Cancel stops before this action; completed work and logs stay available."
    eligible, applied, summary = _remembered_approval_status(
        agent_state,
        active_confirmation,
        sources.remembered_approvals,
        sources.run_logs,
    )
    return InstrumentConfirmation(
        consequence=consequence,
        target=_safe_text(target),
        preserved_work=preserved_work,
        safe_negative_path=safe_negative,
        remembered_approval_eligible=eligible,
        remembered_approval_applied=applied,
        remembered_approval_summary=summary,
    )


def _confirmation_headline(confirmation: InstrumentConfirmation) -> str:
    consequence = confirmation.consequence.rstrip(".?")
    target = _safe_target_for_headline(confirmation.target)
    if target and target.casefold() not in consequence.casefold():
        return f"Confirm {consequence} for {target}"
    return f"Confirm {consequence}"


def _clean_confirmation_text(value: str) -> str:
    text = _safe_text(value, limit=400)
    text = re.sub(r"\b[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)?\b", "action", text)
    return text or "Continue this step."


def _safe_target_for_headline(target: str) -> str:
    text = _safe_text(target)
    lowered = text.casefold()
    if not text:
        return ""
    if any(marker in lowered for marker in ("xpath", "css=", "selector=", "//")):
        return "selected control"
    if any(marker in text for marker in ("#", ">", "[", "]", "{", "}")):
        return "selected control"
    return text


def _remembered_approval_status(
    agent_state: AgentState,
    active_confirmation: Mapping[str, Any],
    remembered_approvals: Any,
    run_logs: Sequence[Any],
) -> tuple[bool, bool, str]:
    config = _data_mapping(remembered_approvals)
    applied = _remembered_applied(config, run_logs)
    if applied:
        return True, True, "A remembered local approval was applied for this exact target."
    explicit = _bool_or_none(
        _first_present(
            active_confirmation.get("remembered_approval_eligible"),
            active_confirmation.get("remember_eligible"),
            config.get("eligible"),
        )
    )
    if explicit is not None:
        reason = _safe_text(
            config.get("reason") or active_confirmation.get("remember_reason") or ""
        )
        if reason:
            return explicit, False, reason
        summary = (
            "This approval can be remembered locally."
            if explicit
            else "This approval cannot be remembered."
        )
        return explicit, False, summary
    if _matching_approval(agent_state, remembered_approvals):
        return (
            True,
            False,
            "A matching remembered approval exists, but this confirmation still requires an "
            "explicit decision.",
        )
    return False, False, "Remembering is unavailable for this confirmation."


def _remembered_applied(config: Mapping[str, Any], run_logs: Sequence[Any]) -> bool:
    if bool(config.get("applied")):
        return True
    for record in run_logs:
        metadata = _record_metadata(record)
        if metadata.get("remembered_approval_applied"):
            return True
    return False


def _matching_approval(agent_state: AgentState, remembered_approvals: Any) -> bool:
    if isinstance(remembered_approvals, str) or remembered_approvals is None:
        return False
    if isinstance(remembered_approvals, Mapping):
        rows = remembered_approvals.get("items") or remembered_approvals.get("remembered_approvals")
    else:
        rows = remembered_approvals
    if isinstance(rows, str) or not isinstance(rows, Sequence):
        return False
    confirmation = agent_state.pending_confirmation
    if confirmation is None:
        return False
    for item in rows:
        entry = _mapping(item)
        scope = _mapping(entry.get("scope"))
        if scope.get("recipe_or_intent_id") != agent_state.active_ritual_id:
            continue
        target_text = _safe_text(scope.get("target_text"))
        if target_text and target_text == confirmation.target:
            return True
    return False


def _confirmation_actions(
    confirmation: InstrumentConfirmation,
) -> tuple[InstrumentAction, ...]:
    actions = [
        InstrumentAction("approve_once", "Approve once", role=InstrumentActionRole.PRIMARY),
        InstrumentAction(
            "cancel_confirmation",
            "Cancel safely",
            role=InstrumentActionRole.SECONDARY,
        ),
    ]
    if confirmation.remembered_approval_eligible and not confirmation.remembered_approval_applied:
        actions.insert(
            1,
            InstrumentAction(
                "approve_and_remember",
                "Approve and remember locally",
                role=InstrumentActionRole.SECONDARY,
            ),
        )
    return tuple(actions)


def _failure(
    agent_state: AgentState,
    current_step: Mapping[str, Any],
    active_run: Mapping[str, Any],
    last_run: Mapping[str, Any],
    target: Mapping[str, Any],
    doctor: Mapping[str, Any],
    run_logs: Sequence[Any],
) -> InstrumentFailure:
    failure = agent_state.latest_failure
    failed_step = _first_text(
        failure.step_name if failure else "",
        current_step.get("name"),
        last_run.get("last_step"),
        fallback="Current step",
    )
    cause = _first_text(
        failure.message if failure else "",
        active_run.get("message"),
        current_step.get("message"),
        last_run.get("final_message"),
        fallback="The step did not complete.",
    )
    completed = _first_int(last_run.get("steps_completed"), active_run.get("steps_completed"), 0)
    not_run = _first_int(last_run.get("not_run_count"), 0)
    remedy = _first_text(
        target.get("recommended_next_action"),
        _first_sequence_text(target.get("suggestions")),
        _first_sequence_text(doctor.get("errors")),
        fallback="Review the failed step, adjust setup if needed, then retry.",
    )
    run_log = _run_log_path(last_run, run_logs)
    return InstrumentFailure(
        failed_step=failed_step,
        cause=cause,
        completed_work=f"{completed} step{'s' if completed != 1 else ''} completed before failure.",
        steps_not_run=not_run,
        remedy=remedy,
        run_log_path=run_log,
    )


def _failure_actions(failure: InstrumentFailure) -> tuple[InstrumentAction, ...]:
    return (
        InstrumentAction(
            "open_logs",
            "Open logs",
            role=InstrumentActionRole.PRIMARY,
            enabled=bool(failure.run_log_path),
            reason="" if failure.run_log_path else "No run log path is available.",
        ),
        InstrumentAction("details", "Details", role=InstrumentActionRole.SECONDARY),
    )


def _recovery(
    agent_state: AgentState,
    recovery_state: Mapping[str, Any],
    last_run: Mapping[str, Any],
) -> InstrumentRecovery:
    checkpoint = _first_text(
        agent_state.recovery_checkpoint.run_id if agent_state.recovery_checkpoint else "",
        last_run.get("run_log_path"),
        fallback="Last interrupted run",
    )
    raw_steps = (
        agent_state.recovery_checkpoint.safe_next_actions
        if agent_state.recovery_checkpoint and agent_state.recovery_checkpoint.safe_next_actions
        else _sequence(recovery_state.get("safe_next_actions"))
    )
    repair_steps = tuple(
        _repair_step_label(_safe_text(item)) for item in raw_steps if _safe_text(item)
    )
    progress = _first_text(
        recovery_state.get("repaired_status"),
        agent_state.recovery_checkpoint.repaired_status if agent_state.recovery_checkpoint else "",
        last_run.get("final_message"),
        fallback="The interrupted run has a checkpoint and can be reviewed.",
    )
    return InstrumentRecovery(
        checkpoint=checkpoint,
        repair_steps=repair_steps,
        progress=progress,
        resume_available=True,
    )


def _repair_step_label(value: str) -> str:
    labels = {
        "inspect_run": "Inspect the interrupted run log",
        "doctor": "Run Doctor before resuming",
        "start_fresh": "Start fresh if the checkpoint is unsafe",
    }
    return labels.get(value, value.replace("_", " ").title())


def _recovery_actions(recovery: InstrumentRecovery) -> tuple[InstrumentAction, ...]:
    return (
        InstrumentAction(
            "resume_ritual",
            "Resume ritual",
            role=InstrumentActionRole.PRIMARY,
            enabled=recovery.resume_available,
        ),
        InstrumentAction("leave_restored", "Leave restored", role=InstrumentActionRole.SECONDARY),
    )


def _history(
    agent_state: AgentState,
    last_run: Mapping[str, Any],
    *,
    show_history: bool,
) -> InstrumentHistory:
    interrupted = (
        agent_state.state == AgentRunState.INTERRUPTED
        or _safe_text(last_run.get("state")).casefold() == "interrupted"
    )
    if not interrupted:
        return InstrumentHistory()
    summary = _first_text(
        last_run.get("final_message"),
        last_run.get("last_step"),
        fallback="A previous run was interrupted.",
    )
    entries = ()
    if show_history:
        entries = tuple(
            _step_history_label(_mapping(item))
            for item in _sequence(last_run.get("step_summaries"))
            if isinstance(item, Mapping)
        )
    return InstrumentHistory(collapsed=not show_history, summary=summary, entries=entries)


def _step_history_label(step: Mapping[str, Any]) -> str:
    index = _int_value(step.get("index"))
    name = _safe_text(step.get("name") or step.get("step_name"))
    state = _safe_text(step.get("state") or step.get("status"))
    prefix = f"Step {index}: " if index is not None else ""
    suffix = f" ({state})" if state else ""
    return f"{prefix}{name}{suffix}".strip()


def _ready_actions(
    ritual_id: str,
    doctor: Mapping[str, Any],
) -> tuple[InstrumentAction, ...]:
    errors = _first_int(
        _mapping(doctor.get("compatibility")).get("errors_count"),
        doctor.get("errors_count"),
        0,
    )
    can_start = bool(ritual_id) and errors == 0
    reason = "Review Doctor errors before starting." if errors else ""
    return (
        InstrumentAction(
            "start_ritual",
            "Start ritual",
            role=InstrumentActionRole.PRIMARY,
            enabled=can_start,
            reason=reason,
        ),
        InstrumentAction("edit_setup", "Edit setup", role=InstrumentActionRole.SECONDARY),
        InstrumentAction("details", "Details", role=InstrumentActionRole.LINK),
    )


def _interrupted_actions(run_log_path: str) -> tuple[InstrumentAction, ...]:
    return (
        InstrumentAction(
            "open_logs",
            "Open logs",
            role=InstrumentActionRole.PRIMARY,
            enabled=bool(run_log_path),
        ),
        InstrumentAction("details", "Details", role=InstrumentActionRole.SECONDARY),
    )


def _terminal_actions(run_log_path: str) -> tuple[InstrumentAction, ...]:
    return (
        InstrumentAction(
            "open_logs",
            "Open logs",
            role=InstrumentActionRole.SECONDARY,
            enabled=bool(run_log_path),
        ),
        InstrumentAction("details", "Details", role=InstrumentActionRole.LINK),
    )


def _terminal_headline(state: InstrumentState, ritual_name: str) -> str:
    if state == InstrumentState.COMPLETED:
        return f"{ritual_name} completed"
    return f"{ritual_name} stopped"


def _run_log_path(last_run: Mapping[str, Any], run_logs: Sequence[Any]) -> str:
    path = _safe_text(last_run.get("run_log_path"))
    if path:
        return path
    for record in run_logs:
        record_path = _record_path(record)
        if record_path:
            return record_path
    return ""


def _record_metadata(record: Any) -> dict[str, Any]:
    metadata = getattr(record, "metadata", None)
    if metadata is None and isinstance(record, Mapping):
        metadata = record.get("metadata")
    return _mapping(metadata)


def _record_path(record: Any) -> str:
    path = getattr(record, "path", None)
    if path is None and isinstance(record, Mapping):
        path = record.get("path")
    return _safe_text(path)


def _data_mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "to_dict"):
        converted = value.to_dict()
        if isinstance(converted, Mapping):
            return dict(converted)
    if hasattr(value, "model_dump"):
        converted = value.model_dump(mode="json")
        if isinstance(converted, Mapping):
            return dict(converted)
    return _mapping(value)


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _sequence(value: object) -> Sequence[Any]:
    if value is None or isinstance(value, str):
        return ()
    if isinstance(value, Sequence):
        return value
    return ()


def _string_sequence(value: object) -> tuple[str, ...]:
    return tuple(_safe_text(item) for item in _sequence(value) if _safe_text(item))


def _first_sequence_text(value: object) -> str:
    for item in _sequence(value):
        text = _safe_text(item)
        if text:
            return text
    return ""


def _first_text(*values: object, fallback: str) -> str:
    for value in values:
        text = _safe_text(value)
        if text:
            return text
    return fallback


def _safe_text(value: object, *, limit: int = 240) -> str:
    text = str(getattr(value, "value", value) or "").replace("\r", " ").replace("\n", " ").strip()
    for marker in ("token=", "password=", "passwd=", "secret=", "api_key=", "apikey="):
        lowered = text.casefold()
        index = lowered.find(marker)
        if index >= 0:
            text = text[: index + len(marker)] + "[redacted]"
    text = " ".join(text.split())
    if len(text) > limit:
        return text[: limit - 1].rstrip() + "..."
    return text


def _title_from_id(value: str) -> str:
    return value.replace("_", " ").replace("-", " ").title() if value else ""


def _count_label(values: Sequence[Any], noun: str) -> str:
    count = len(values)
    return f"{count} {noun}{'s' if count != 1 else ''}"


def _first_int(*values: object) -> int:
    for value in values:
        parsed = _int_value(value)
        if parsed is not None:
            return max(0, parsed)
    return 0


def _int_value(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _first_float(*values: object) -> float | None:
    for value in values:
        parsed = _float_value(value)
        if parsed is not None:
            return parsed
    return None


def _float_value(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _datetime_value(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    return None


def _bool_or_none(value: object) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "1", "yes", "y", "on"}:
            return True
        if normalized in {"false", "0", "no", "n", "off"}:
            return False
    return None


def _first_present(*values: object) -> object:
    for value in values:
        if value is not None:
            return value
    return None


def _dataclass_to_dict(instance: object) -> dict[str, Any]:
    return {field.name: _to_json_value(getattr(instance, field.name)) for field in fields(instance)}


def _to_json_value(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if is_dataclass(value):
        return _dataclass_to_dict(value)
    if isinstance(value, tuple):
        return [_to_json_value(item) for item in value]
    if isinstance(value, list):
        return [_to_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _to_json_value(item) for key, item in value.items()}
    return value


__all__ = [
    "INSTRUMENT_MODEL_SCHEMA_VERSION",
    "InstrumentAction",
    "InstrumentActionRole",
    "InstrumentConfirmation",
    "InstrumentFact",
    "InstrumentFailure",
    "InstrumentHistory",
    "InstrumentModel",
    "InstrumentProgress",
    "InstrumentRecovery",
    "InstrumentSources",
    "InstrumentState",
    "InstrumentWait",
    "build_instrument_model",
]
