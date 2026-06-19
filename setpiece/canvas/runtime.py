from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.parse import urlparse

from setpiece.intent_planner import build_plan_doctor_report
from setpiece.recipe_loader import discover_recipes
from setpiece.run_logs import RunRecord, list_recent_runs, summarize_run_record
from setpiece.shortcuts import (
    ShortcutKind,
    shortcut_kind_for_component,
    shortcut_request_from_component,
    shortcut_setup_issue,
)
from setpiece.target_resolution import (
    TargetResolutionResult,
    build_target_plan_summary,
    builtin_target_catalog,
    compile_target_start_plan,
    resolve_target,
)

from .models import CanvasBindingKind, CanvasComponent, CanvasComponentBinding, CanvasDocument
from .registry import create_component_registry, normalize_canvas_bindings, validate_canvas_structure
from .ritual_state import RitualStateInputs, build_ritual_state, normalize_ritual_state
from .theme_bridge import resolve_canvas_theme

CANVAS_RUNTIME_SCHEMA_VERSION = "setpiece.canvas.runtime.v1"


class CanvasComponentAction(StrEnum):
    RUN = "run"
    DRY_RUN = "dry_run"
    DOCTOR = "doctor"
    VIEW_RECIPE = "view_recipe"
    EDIT_SETUP = "edit_setup"
    EDIT_RECIPE = "edit_recipe"
    OPEN_YAML = "open_yaml"
    OPEN_LOGS = "open_logs"
    OPEN_RUN_LOG = "open_run_log"
    PAUSE = "pause"
    RESUME = "resume"
    STOP = "stop"
    PREVIEW_PLAN = "preview_plan"
    OPEN = "open"
    LAUNCH = "launch"


class CanvasRuntimeCommand(StrEnum):
    BUILD_MODEL = "build_model"
    DISPATCH_ACTION = "dispatch_action"


@dataclass(frozen=True)
class CanvasRuntimeEvent:
    component_id: str
    event_type: str
    state: str = ""
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "type": self.event_type,
            "state": self.state,
            "message": self.message,
            "data": self.data,
        }


@dataclass(frozen=True)
class CanvasComponentRuntimeState:
    component_id: str
    component_type: str
    state: str = "idle"
    status: str = "ready"
    title: str = ""
    subtitle: str = ""
    message: str = ""
    binding_kind: str = ""
    binding_reference: str = ""
    enabled_actions: tuple[str, ...] = ()
    disabled_actions: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "component_type": self.component_type,
            "state": self.state,
            "status": self.status,
            "title": self.title,
            "subtitle": self.subtitle,
            "message": self.message,
            "binding": {
                "kind": self.binding_kind,
                "reference": self.binding_reference,
            },
            "enabled_actions": list(self.enabled_actions),
            "disabled_actions": list(self.disabled_actions),
            "warnings": list(self.warnings),
            "data": self.data,
        }


@dataclass(frozen=True)
class CanvasComponentActionResult:
    component_id: str
    action_id: str
    status: str
    message: str = ""
    dry_run: bool = False
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status in {"success", "dry-run"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "action_id": self.action_id,
            "status": self.status,
            "message": self.message,
            "dry_run": self.dry_run,
            "data": self.data,
        }


@dataclass(frozen=True)
class CanvasRuntimeModel:
    canvas_id: str
    component_states: tuple[CanvasComponentRuntimeState, ...]
    active_runs: dict[str, dict[str, Any]] = field(default_factory=dict)
    recent_activity: tuple[dict[str, Any], ...] = ()
    last_run_messages: dict[str, str] = field(default_factory=dict)
    doctor_summaries: dict[str, dict[str, Any]] = field(default_factory=dict)
    ritual_states: dict[str, dict[str, Any]] = field(default_factory=dict)
    target_plan_summaries: dict[str, dict[str, Any]] = field(default_factory=dict)
    unresolved_binding_warnings: tuple[str, ...] = ()
    performance_counters: dict[str, float | int] = field(default_factory=dict)
    theme: dict[str, Any] = field(default_factory=dict)
    schema_version: str = CANVAS_RUNTIME_SCHEMA_VERSION

    def component_state(self, component_id: str) -> CanvasComponentRuntimeState:
        for state in self.component_states:
            if state.component_id == component_id:
                return state
        raise KeyError(component_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "canvas_id": self.canvas_id,
            "components": [state.to_dict() for state in self.component_states],
            "active_runs": self.active_runs,
            "recent_activity": list(self.recent_activity),
            "last_run_messages": self.last_run_messages,
            "doctor_summaries": self.doctor_summaries,
            "ritual_states": self.ritual_states,
            "target_plan_summaries": self.target_plan_summaries,
            "unresolved_binding_warnings": list(self.unresolved_binding_warnings),
            "performance_counters": self.performance_counters,
            "theme": self.theme,
        }


@dataclass
class CanvasRuntimeContext:
    recipe_ids: set[str] | None = None
    target_ids: set[str] | None = None
    active_runs: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    runtime_state: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    recent_runs: Sequence[RunRecord] | None = None
    recent_runs_loader: Callable[..., Sequence[RunRecord]] | None = None
    target_plan_summaries: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    doctor_summaries: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    dry_run_summaries: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    resolve_targets: bool = False
    target_resolver: Callable[[str], TargetResolutionResult] | None = None
    clock: Callable[[], datetime] | None = None
    category_filter: str = ""


def build_canvas_runtime_model(
    document: CanvasDocument,
    *,
    context: CanvasRuntimeContext | None = None,
) -> CanvasRuntimeModel:
    started = perf_counter()
    resolved_context = context or CanvasRuntimeContext()
    normalized = normalize_canvas_bindings(document)
    theme = resolve_canvas_theme(normalized)
    structural_validation = validate_canvas_structure(normalized)
    registry = create_component_registry()
    recipe_ids = _recipe_ids(resolved_context)
    target_ids = _target_ids(resolved_context)
    recent_records = _recent_records(resolved_context)
    recent_activity, last_run_messages, last_run_status = _recent_activity(
        resolved_context,
        records=recent_records,
    )
    states: list[CanvasComponentRuntimeState] = []
    warnings: list[str] = list(structural_validation.errors) + list(structural_validation.warnings)
    target_summaries: dict[str, dict[str, Any]] = dict(resolved_context.target_plan_summaries)
    doctor_summaries = dict(resolved_context.doctor_summaries)
    ritual_states = _build_ritual_states(
        normalized,
        context=resolved_context,
        recent_records=recent_records,
    )

    for component in normalized.components:
        state = _component_runtime_state(
            component,
            registry=registry,
            context=resolved_context,
            recipe_ids=recipe_ids,
            target_ids=target_ids,
            last_run_messages=last_run_messages,
            last_run_status=last_run_status,
            target_summaries=target_summaries,
            ritual_states=ritual_states,
        )
        states.append(state)
        warnings.extend(state.warnings)

    return CanvasRuntimeModel(
        canvas_id=normalized.id,
        component_states=tuple(states),
        active_runs={key: dict(value) for key, value in resolved_context.active_runs.items()},
        recent_activity=tuple(recent_activity),
        last_run_messages=last_run_messages,
        doctor_summaries=doctor_summaries,
        ritual_states=ritual_states,
        target_plan_summaries=target_summaries,
        unresolved_binding_warnings=tuple(dict.fromkeys(warnings)),
        performance_counters={
            "component_count": len(normalized.components),
            "runtime_state_build_ms": max(0.0, (perf_counter() - started) * 1000),
            "warnings_count": len(dict.fromkeys(warnings)),
            "recent_activity_count": len(recent_activity),
        },
        theme=theme.to_dict(),
    )


def _component_runtime_state(
    component: CanvasComponent,
    *,
    registry: Any,
    context: CanvasRuntimeContext,
    recipe_ids: set[str],
    target_ids: set[str],
    last_run_messages: dict[str, str],
    last_run_status: dict[str, str],
    target_summaries: dict[str, dict[str, Any]],
    ritual_states: dict[str, dict[str, Any]],
) -> CanvasComponentRuntimeState:
    props = component.props_dict()
    binding = component.binding
    binding_kind = binding.kind if binding is not None else CanvasBindingKind.STATIC
    reference = binding.reference if binding is not None else ""
    title = _component_title(component)
    warnings: list[str] = []

    shortcut_kind = shortcut_kind_for_component(component.type)
    if shortcut_kind is not None:
        return _shortcut_runtime_state(
            component,
            kind=shortcut_kind,
            title=title,
            binding_kind=binding_kind,
            reference=reference,
        )

    if component.type == "ritual.card":
        reference = reference or str(props.get("recipe_id") or component.id)
        warnings.extend(_unresolved_recipe_warnings(component.id, reference, recipe_ids))
        active = _active_state(context, reference)
        active_payload = _sanitized_runtime_mapping(active)
        status = str(active_payload.get("status") or last_run_status.get(reference) or "ready")
        return CanvasComponentRuntimeState(
            component.id,
            component.type,
            state=status,
            status=_status_for_run(status),
            title=title,
            subtitle=str(props.get("subtitle") or ""),
            message=str(active_payload.get("message") or last_run_messages.get(reference, "")),
            binding_kind=CanvasBindingKind.RECIPE.value,
            binding_reference=reference,
            enabled_actions=() if warnings else (
                "run",
                "dry_run",
                "doctor",
                "view_recipe",
                "edit_setup",
                "edit_recipe",
                "open_yaml",
                "open_logs",
            ),
            disabled_actions=(
                "run",
                "dry_run",
                "doctor",
                "view_recipe",
                "edit_setup",
                "edit_recipe",
                "open_yaml",
                "open_logs",
            ) if warnings else (),
            warnings=tuple(warnings),
            data={"recipe_id": reference, "active_run": active_payload, "ritual_state": ritual_states.get(reference, {})},
        )

    if component.type == "ritual.status":
        reference = reference or str(props.get("recipe_id") or "")
        warnings.extend(_unresolved_recipe_warnings(component.id, reference, recipe_ids))
        active = _active_state(context, reference)
        active_payload = _sanitized_runtime_mapping(active)
        status = str(active_payload.get("status") or last_run_status.get(reference) or "idle")
        return CanvasComponentRuntimeState(
            component.id,
            component.type,
            state=status,
            status=_status_for_run(status),
            title=title or reference,
            message=str(active_payload.get("current_step") or last_run_messages.get(reference, "")),
            binding_kind=CanvasBindingKind.RECIPE.value,
            binding_reference=reference,
            warnings=tuple(warnings),
            data={
                "recipe_id": reference,
                "current_step": active_payload.get("current_step", ""),
                "ritual_state": ritual_states.get(reference, {}),
            },
        )

    if component.type == "ritual.controller":
        reference = reference or str(props.get("recipe_id") or "")
        active = _active_state(context, reference)
        active_payload = _sanitized_runtime_mapping(active)
        enabled = ("pause", "resume", "stop", "open_run_log") if active_payload else ()
        return CanvasComponentRuntimeState(
            component.id,
            component.type,
            state=str(active_payload.get("status") or "idle"),
            status="enabled" if active_payload else "disabled",
            title=title,
            message=str(active_payload.get("message") or ""),
            binding_kind=binding_kind.value,
            binding_reference=reference,
            enabled_actions=enabled,
            disabled_actions=() if active_payload else ("pause", "resume", "stop", "open_run_log"),
            data={"recipe_id": reference, "active_run": active_payload, "ritual_state": ritual_states.get(reference, {})},
        )

    if component.type in {"target.card", "target.status"}:
        reference = reference or str(props.get("target") or props.get("target_id") or "")
        warnings.extend(_unresolved_target_warnings(component.id, reference, target_ids))
        summary = _target_summary(reference, context, target_summaries, warnings)
        state = str(summary.get("state") or ("unresolved" if warnings else "unknown"))
        return CanvasComponentRuntimeState(
            component.id,
            component.type,
            state=state,
            status="warning" if warnings else "ready",
            title=title,
            message=str(summary.get("recommended_next_action") or summary.get("best_candidate_summary") or ""),
            binding_kind=CanvasBindingKind.TARGET_START.value,
            binding_reference=reference,
            enabled_actions=() if component.type == "target.status" else ("preview_plan",),
            warnings=tuple(warnings),
            data={"target_id": reference, "summary": summary},
        )

    if component.type == "doctor.badge":
        reference = reference or str(props.get("recipe_id") or "")
        summary = dict(context.doctor_summaries.get(reference, {}))
        status = str(summary.get("status") or summary.get("compatibility") or "unknown")
        return CanvasComponentRuntimeState(
            component.id,
            component.type,
            state=status,
            status=_status_for_doctor(status),
            title=title or "Doctor",
            message=str(summary.get("message") or ""),
            binding_kind=binding_kind.value,
            binding_reference=reference,
            enabled_actions=("doctor",) if reference else (),
            warnings=tuple(_unresolved_recipe_warnings(component.id, reference, recipe_ids) if reference else ()),
            data={"summary": summary, "ritual_state": ritual_states.get(reference, {})},
        )

    if component.type == "recent.activity":
        return CanvasComponentRuntimeState(
            component.id,
            component.type,
            state="ready",
            status="ready",
            title=title or "Recent Activity",
            message=f"{len(last_run_messages)} recent recipe(s)",
            binding_kind=binding_kind.value,
            binding_reference=reference,
            enabled_actions=("open_logs",),
            data={"items": list(_recent_activity(context)[0])},
        )

    if component.type == "category.dock":
        categories = _component_categories(component, registry)
        return CanvasComponentRuntimeState(
            component.id,
            component.type,
            state=str(context.category_filter or "all"),
            status="ready",
            title=title,
            binding_kind=binding_kind.value,
            binding_reference=reference,
            data={"categories": categories, "selected": context.category_filter},
        )

    return CanvasComponentRuntimeState(
        component.id,
        component.type,
        state="static",
        status="ready",
        title=title,
        binding_kind=binding_kind.value,
        binding_reference=reference,
        data=_display_data(component, context),
    )


def _shortcut_runtime_state(
    component: CanvasComponent,
    *,
    kind: ShortcutKind,
    title: str,
    binding_kind: CanvasBindingKind,
    reference: str,
) -> CanvasComponentRuntimeState:
    request = shortcut_request_from_component(component)
    action = request.action_id
    issue = shortcut_setup_issue(request)
    disabled = (action,) if issue else ()
    enabled = () if issue else (action,)
    state = "needs_setup" if issue else "ready"
    return CanvasComponentRuntimeState(
        component.id,
        component.type,
        state=state,
        status="warning" if issue else "ready",
        title=title,
        message=issue or f"{kind.value} shortcut ready",
        binding_kind=binding_kind.value,
        binding_reference=reference or request.target,
        enabled_actions=enabled,
        disabled_actions=disabled,
        warnings=(issue,) if issue else (),
        data={
            "shortcut": {
                "kind": kind.value,
                "action": action,
                "target_label": _shortcut_target_label(request),
            }
        },
    )


def _recipe_ids(context: CanvasRuntimeContext) -> set[str]:
    if context.recipe_ids is not None:
        return set(context.recipe_ids)
    ids: set[str] = set()
    for path, recipe, _error in discover_recipes():
        ids.add(recipe.id if recipe is not None else path.stem)
    return ids


def _build_ritual_states(
    document: CanvasDocument,
    *,
    context: CanvasRuntimeContext,
    recent_records: Sequence[RunRecord],
) -> dict[str, dict[str, Any]]:
    recipe_refs = _ritual_recipe_refs(document)
    recipe_refs.update(str(key) for key in context.runtime_state)
    recipe_refs.update(str(key) for key in context.doctor_summaries)
    recipe_refs.update(str(key) for key in context.dry_run_summaries)
    recipe_refs.update(str(record.metadata.get("recipe_id") or "") for record in recent_records)
    states: dict[str, dict[str, Any]] = {}
    for recipe_id in sorted(item for item in recipe_refs if item):
        active = dict(context.runtime_state.get(recipe_id, {}))
        existing = active.get("ritual_state")
        if isinstance(existing, dict):
            states[recipe_id] = normalize_ritual_state(recipe_id, existing)
            continue
        states[recipe_id] = build_ritual_state(
            RitualStateInputs(
                recipe_id=recipe_id,
                active=active,
                doctor=context.doctor_summaries.get(recipe_id),
                dry_run=context.dry_run_summaries.get(recipe_id),
                recent_runs=recent_records,
            )
        )
    return states


def _ritual_recipe_refs(document: CanvasDocument) -> set[str]:
    refs: set[str] = set()
    for component in document.components:
        if component.type not in {"ritual.card", "ritual.status", "ritual.controller", "doctor.badge"}:
            continue
        binding = component.binding
        if binding is not None and binding.kind is CanvasBindingKind.RECIPE:
            refs.add(binding.reference)
            continue
        props = component.props_dict()
        refs.add(str(props.get("recipe_id") or "").strip())
    return {item for item in refs if item}


def _target_ids(context: CanvasRuntimeContext) -> set[str]:
    if context.target_ids is not None:
        return set(context.target_ids)
    return {target.id for target in builtin_target_catalog().targets}


def _recent_records(context: CanvasRuntimeContext) -> list[RunRecord]:
    if context.recent_runs is not None:
        return list(context.recent_runs)
    if context.recent_runs_loader is not None:
        return list(context.recent_runs_loader(limit=20))
    return list_recent_runs(limit=20)


def _recent_activity(
    context: CanvasRuntimeContext,
    *,
    records: Sequence[RunRecord] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, str]]:
    resolved_records = list(records) if records is not None else _recent_records(context)
    activity: list[dict[str, Any]] = []
    messages: dict[str, str] = {}
    statuses: dict[str, str] = {}
    for record in resolved_records[:20]:
        recipe_id = str(record.metadata.get("recipe_id") or "").strip()
        summary = summarize_run_record(record)
        status = str(record.metadata.get("final_state") or summary.final_status or "")
        message = str(record.metadata.get("final_message") or summary.last_step or status)
        row = {
            "run_id": record.run_id,
            "recipe_id": recipe_id,
            "status": status,
            "message": message,
            "last_step": summary.last_step,
            "path": str(record.path),
            "stopped_reason": str(record.metadata.get("stopped_reason") or ""),
            "cleanup_available": _cleanup_available(record.metadata.get("cleanup_offer")),
            "cleanup_choice": _cleanup_choice(record.metadata.get("cleanup_choice")),
            "ownership_count": _ownership_count(record.metadata.get("ownership_ledger")),
            **_recent_ledger_metadata(record),
        }
        activity.append(row)
        if recipe_id and recipe_id not in messages:
            messages[recipe_id] = message
            statuses[recipe_id] = status
    return activity, messages, statuses


def _cleanup_available(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    options = value.get("options")
    if not isinstance(options, list):
        return False
    for option in options:
        if isinstance(option, dict) and option.get("id") == "clean_up_setpiece_opened":
            return bool(option.get("available"))
    return False


def _cleanup_choice(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    return str(value.get("choice") or "")


def _ownership_count(value: object) -> int:
    if isinstance(value, list):
        return len(value)
    return 0


def _recent_ledger_metadata(record: RunRecord) -> dict[str, Any]:
    steps = [
        _recent_step_summary(step)
        for step in record.steps
        if isinstance(step, Mapping)
    ]
    steps_total = _safe_int(record.metadata.get("steps_total")) or _max_step_index(steps) or len(steps)
    notes_count = _safe_int(record.metadata.get("operator_notes_count"))
    if notes_count is None:
        notes_count = len(record.notes)
    last_note_at = str(record.metadata.get("last_operator_note_at") or "")
    if not last_note_at and record.notes:
        last_note_at = str(record.notes[-1].get("at") or "")
    return {
        "step_summaries": steps[:6],
        "steps_total": steps_total,
        "steps_completed": sum(1 for step in steps if step["state"] in {"success", "dry-run", "skipped"}),
        "steps_failed": sum(1 for step in steps if step["state"] in {"failed", "error", "cancelled"}),
        "not_run_count": max(0, steps_total - len(steps)),
        "operator_notes_count": notes_count,
        "last_operator_note_at": last_note_at[:80],
    }


def _recent_step_summary(step: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "index": _safe_int(step.get("index") or step.get("step_index")),
        "name": _sanitize_runtime_text(str(step.get("step_name") or step.get("name") or "")),
        "action": _sanitize_runtime_text(str(step.get("action") or "")),
        "state": _sanitize_runtime_text(str(step.get("status") or step.get("state") or "")),
        "message": _sanitize_runtime_text(str(step.get("message") or "")),
    }


def _safe_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _max_step_index(steps: Sequence[Mapping[str, Any]]) -> int:
    values = [
        int(step["index"])
        for step in steps
        if isinstance(step.get("index"), int)
    ]
    return max(values, default=0)


def _active_state(context: CanvasRuntimeContext, reference: str) -> dict[str, Any]:
    if not reference:
        return {}
    state = context.runtime_state.get(reference) or context.active_runs.get(reference) or {}
    return dict(state)


def _sanitized_runtime_mapping(value: Mapping[str, Any], *, depth: int = 0) -> dict[str, Any]:
    if depth > 3:
        return {}
    sanitized: dict[str, Any] = {}
    for key, item in value.items():
        key_text = str(key)
        if key_text == "ritual_state":
            continue
        if isinstance(item, Mapping):
            sanitized[key_text] = _sanitized_runtime_mapping(item, depth=depth + 1)
        elif isinstance(item, (list, tuple)):
            sanitized[key_text] = [
                _sanitize_runtime_value(child, depth=depth + 1)
                for child in item[:20]
            ]
        else:
            sanitized[key_text] = _sanitize_runtime_value(item, depth=depth)
    return sanitized


def _sanitize_runtime_value(value: Any, *, depth: int = 0) -> Any:
    if isinstance(value, Mapping):
        return _sanitized_runtime_mapping(value, depth=depth + 1)
    if isinstance(value, (list, tuple)):
        return [_sanitize_runtime_value(item, depth=depth + 1) for item in value[:20]]
    if isinstance(value, str):
        return _sanitize_runtime_text(value)
    return value


def _sanitize_runtime_text(value: str) -> str:
    text = value.replace("\r", " ").replace("\n", " ").strip()
    for marker in ("token=", "password=", "passwd=", "secret=", "api_key=", "apikey="):
        lowered = text.casefold()
        index = lowered.find(marker)
        if index >= 0:
            text = text[: index + len(marker)] + "[redacted]"
    if len(text) > 240:
        return text[:239].rstrip() + "..."
    return text


def _target_summary(
    reference: str,
    context: CanvasRuntimeContext,
    target_summaries: dict[str, dict[str, Any]],
    warnings: list[str],
) -> dict[str, Any]:
    if not reference:
        return {}
    if reference in target_summaries:
        return target_summaries[reference]
    if not context.resolve_targets:
        return {}
    try:
        resolver = context.target_resolver or resolve_target
        resolution = resolver(reference)
        plan = compile_target_start_plan(reference, resolution=resolution)
        doctor = build_plan_doctor_report(plan)
        summary = build_target_plan_summary(resolution, plan, doctor).to_dict()
        target_summaries[reference] = summary
        return summary
    except Exception as exc:  # pragma: no cover - defensive side-effect-free diagnostics
        warnings.append(f"target binding '{reference}' could not be resolved: {exc}")
        return {}


def _component_categories(component: CanvasComponent, registry: Any) -> list[str]:
    categories: list[str] = []
    for category in component.props_dict().get("categories") or []:
        text = str(category).strip()
        if text:
            categories.append(text)
    if categories:
        return categories
    return sorted({spec.category for spec in registry.all()})


def _display_data(component: CanvasComponent, context: CanvasRuntimeContext) -> dict[str, Any]:
    props = component.props_dict()
    if component.type == "clock":
        now = (context.clock or datetime.now)()
        return {"text": now.strftime("%H:%M"), "format": str(props.get("format") or "short")}
    if component.type in {"text.label", "image", "shape", "spacer/divider"}:
        return props
    return props


def _shortcut_target_label(request: Any) -> str:
    target = str(getattr(request, "target", "") or "")
    if getattr(request, "kind", None) is ShortcutKind.URL:
        return urlparse(target).netloc or target
    if target:
        return Path(target).name or target
    return str(
        getattr(request, "app_id", "")
        or getattr(request, "title", "")
        or getattr(request, "component_id", "")
        or ""
    )


def _unresolved_recipe_warnings(component_id: str, reference: str, recipe_ids: set[str]) -> tuple[str, ...]:
    if not reference:
        return (f"{component_id}: recipe binding is missing",)
    if reference not in recipe_ids:
        return (f"{component_id}: recipe binding '{reference}' is unresolved",)
    return ()


def _unresolved_target_warnings(component_id: str, reference: str, target_ids: set[str]) -> tuple[str, ...]:
    if not reference:
        return (f"{component_id}: target binding is missing",)
    if reference not in target_ids:
        return (f"{component_id}: target binding '{reference}' is unresolved",)
    return ()


def _status_for_run(state: str) -> str:
    normalized = state.strip().lower()
    if normalized in {
        "success",
        "failed",
        "blocked",
        "stopped",
        "interrupted",
        "paused",
        "waiting",
        "confirming",
        "starting",
    }:
        return normalized
    if normalized == "running":
        return "running"
    return "ready"


def _status_for_doctor(state: str) -> str:
    normalized = state.strip().lower()
    if normalized in {"compatible", "ok"}:
        return "compatible"
    if normalized in {"compatible_with_warnings", "warning", "warnings"}:
        return "warnings"
    if normalized in {"incompatible", "error", "failed"}:
        return "incompatible"
    if normalized == "running_check":
        return "running_check"
    return "unknown"


def _component_title(component: CanvasComponent) -> str:
    props = component.props_dict()
    explicit = str(props.get("title") or props.get("text") or "").strip()
    if explicit:
        return explicit
    by_type = {
        "category.dock": "Categories",
        "ritual.status": "Ritual status",
        "ritual.controller": "Ritual controls",
        "recent.activity": "Recent activity",
        "doctor.badge": "Doctor",
        "target.status": "Target status",
        "target.card": "Target",
        "clock": "Clock",
    }
    if component.type in by_type:
        return by_type[component.type]
    return str(component.id).replace("_", " ").replace("-", " ").strip().title() or "Canvas item"
