from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ritualist.errors import RitualistError
from ritualist.home.actions import HomeActionService
from ritualist.runtime_control import RuntimeControl
from ritualist.shortcuts import ShortcutService, shortcut_kind_for_component, shortcut_request_from_component
from ritualist.target_resolution import (
    build_target_plan_summary,
    compile_target_start_plan,
    resolve_target,
    target_plan_payload,
)
from ritualist.intent_planner import build_plan_doctor_report

from .models import CanvasBindingKind, CanvasComponent, CanvasDocument
from .registry import create_component_registry, normalize_canvas_bindings
from .runtime import CanvasComponentActionResult, CanvasRuntimeContext
from .storage import load_canvas


@dataclass
class CanvasRuntimeController:
    action_service: HomeActionService = field(default_factory=HomeActionService)
    shortcut_service: ShortcutService = field(default_factory=ShortcutService)
    context: CanvasRuntimeContext = field(default_factory=CanvasRuntimeContext)
    runtime_controls: dict[str, RuntimeControl] = field(default_factory=dict)

    def dispatch(
        self,
        document: CanvasDocument,
        component_id: str,
        action_id: str,
        *,
        dry_run: bool = False,
        params: dict[str, Any] | None = None,
        runtime_event_callback: Callable[[Any], None] | None = None,
        status_callback: Callable[[Any], None] | None = None,
        confirmer: Callable[[Any], bool] | None = None,
        control: RuntimeControl | None = None,
    ) -> CanvasComponentActionResult:
        normalized = normalize_canvas_bindings(document)
        component = _find_component(normalized, component_id)
        action = str(action_id).strip()
        _validate_action(component, action)
        if dry_run:
            return CanvasComponentActionResult(
                component.id,
                action,
                "dry-run",
                f"would dispatch canvas action {action}",
                dry_run=True,
                data={"component_type": component.type, "params": params or {}},
            )
        if component.type in {"ritual.card", "doctor.badge"}:
            return self._dispatch_recipe_action(
                component,
                action,
                runtime_event_callback=runtime_event_callback,
                status_callback=status_callback,
                confirmer=confirmer,
                control=control,
            )
        if component.type == "ritual.controller":
            return self._dispatch_controller_action(component, action)
        if component.type in {"target.card", "target.status"}:
            return self._dispatch_target_action(component, action)
        if shortcut_kind_for_component(component.type) is not None:
            return self._dispatch_shortcut_action(component, action)
        if component.type == "recent.activity" and action == "open_logs":
            path = self.action_service.resolve_runs_path()
            return _success(component, action, f"run logs path resolved: {path}", {"path": str(path)})
        raise RitualistError(f"{component.id}: unsupported canvas action '{action}'")

    def _dispatch_recipe_action(
        self,
        component: CanvasComponent,
        action: str,
        *,
        runtime_event_callback: Callable[[Any], None] | None = None,
        status_callback: Callable[[Any], None] | None = None,
        confirmer: Callable[[Any], bool] | None = None,
        control: RuntimeControl | None = None,
    ) -> CanvasComponentActionResult:
        recipe_ref = _recipe_reference(component)
        if not recipe_ref:
            raise RitualistError(f"{component.id}: recipe binding is required for {action}")
        if self.context.recipe_ids is not None and recipe_ref not in self.context.recipe_ids:
            raise RitualistError(f"{component.id}: recipe binding '{recipe_ref}' is unresolved")
        if action == "run":
            result = self.action_service.run_recipe(
                recipe_ref,
                dry_run=False,
                runtime_event_callback=runtime_event_callback,
                status_callback=status_callback,
                confirmer=confirmer,
                control=control,
            )
            return _success(component, action, f"run dispatched for {recipe_ref}", _result_data(result))
        if action == "dry_run":
            result = self.action_service.run_recipe(
                recipe_ref,
                dry_run=True,
                runtime_event_callback=runtime_event_callback,
                status_callback=status_callback,
                confirmer=confirmer,
                control=control,
            )
            return _success(component, action, f"dry-run dispatched for {recipe_ref}", _result_data(result))
        if action == "doctor":
            result = self.action_service.doctor_recipe(recipe_ref)
            return _success(component, action, f"doctor completed for {recipe_ref}", _result_data(result))
        if action == "edit_recipe":
            path = self.action_service.resolve_recipe_path(recipe_ref)
            return _success(component, action, f"recipe path resolved: {path}", {"path": str(path)})
        if action in {"open_logs", "open_run_log"}:
            path = self.action_service.resolve_runs_path()
            return _success(component, action, f"run logs path resolved: {path}", {"path": str(path)})
        raise RitualistError(f"{component.id}: unsupported recipe canvas action '{action}'")

    def _dispatch_controller_action(
        self,
        component: CanvasComponent,
        action: str,
    ) -> CanvasComponentActionResult:
        reference = _binding_reference(component)
        control = self.runtime_controls.get(reference)
        if action == "open_run_log":
            path = self.action_service.resolve_runs_path()
            return _success(component, action, f"run logs path resolved: {path}", {"path": str(path)})
        if control is None:
            raise RitualistError(f"{component.id}: no active runtime control is available")
        if action == "pause":
            control.pause()
        elif action == "resume":
            control.resume()
        elif action == "stop":
            control.stop()
        else:
            raise RitualistError(f"{component.id}: unsupported controller action '{action}'")
        return _success(component, action, f"{action} dispatched")

    def _dispatch_target_action(
        self,
        component: CanvasComponent,
        action: str,
    ) -> CanvasComponentActionResult:
        if action != "preview_plan":
            raise RitualistError(f"{component.id}: target start execution is not implemented; use preview_plan")
        target = _target_reference(component)
        if not target:
            raise RitualistError(f"{component.id}: target binding is required for preview_plan")
        resolution = (self.context.target_resolver or resolve_target)(target)
        plan = compile_target_start_plan(target, resolution=resolution)
        doctor = build_plan_doctor_report(plan)
        summary = build_target_plan_summary(resolution, plan, doctor)
        return _success(
            component,
            action,
            f"target plan preview completed for {target}",
            {
                "target_summary": summary.to_dict(),
                "target_plan": target_plan_payload(resolution, plan, doctor),
            },
        )

    def _dispatch_shortcut_action(
        self,
        component: CanvasComponent,
        action: str,
    ) -> CanvasComponentActionResult:
        request = shortcut_request_from_component(component)
        if action != request.action_id:
            raise RitualistError(f"{component.id}: unsupported shortcut action '{action}'")
        result = self.shortcut_service.open(request)
        return CanvasComponentActionResult(
            component.id,
            action,
            result.status,
            result.message,
            data={"shortcut": result.to_dict()},
        )


def dispatch_canvas_action(
    canvas_id: str | Path,
    component_id: str,
    action_id: str,
    *,
    dry_run: bool = False,
    params: dict[str, Any] | None = None,
    controller: CanvasRuntimeController | None = None,
    runtime_event_callback: Callable[[Any], None] | None = None,
    status_callback: Callable[[Any], None] | None = None,
    confirmer: Callable[[Any], bool] | None = None,
    control: RuntimeControl | None = None,
) -> CanvasComponentActionResult:
    document = load_canvas(canvas_id)
    resolved_controller = controller or CanvasRuntimeController()
    return resolved_controller.dispatch(
        document,
        component_id,
        action_id,
        dry_run=dry_run,
        params=params,
        runtime_event_callback=runtime_event_callback,
        status_callback=status_callback,
        confirmer=confirmer,
        control=control,
    )


def _find_component(document: CanvasDocument, component_id: str) -> CanvasComponent:
    for component in document.components:
        if component.id == component_id:
            return component
    raise RitualistError(f"canvas component not found: {component_id}")


def _validate_action(component: CanvasComponent, action: str) -> None:
    registry = create_component_registry()
    try:
        spec = registry.get(component.type)
    except KeyError as exc:
        raise RitualistError(f"{component.id}: unknown component type '{component.type}'") from exc
    if action not in spec.actions:
        raise RitualistError(f"{component.id}: unsupported canvas action '{action}'")
    if not action or any(marker in action.casefold() for marker in ("script", "shell", "powershell", "js")):
        raise RitualistError(f"{component.id}: arbitrary canvas actions are not allowed")


def _recipe_reference(component: CanvasComponent) -> str:
    binding = component.binding
    if binding is not None and binding.kind is CanvasBindingKind.RECIPE:
        return binding.reference
    return str(component.props_dict().get("recipe_id") or "").strip()


def _target_reference(component: CanvasComponent) -> str:
    binding = component.binding
    if binding is not None and binding.kind is CanvasBindingKind.TARGET_START:
        return binding.reference
    props = component.props_dict()
    return str(props.get("target") or props.get("target_id") or "").strip()


def _binding_reference(component: CanvasComponent) -> str:
    binding = component.binding
    if binding is not None:
        return binding.reference
    return _recipe_reference(component) or _target_reference(component)


def _success(
    component: CanvasComponent,
    action: str,
    message: str,
    data: dict[str, Any] | None = None,
) -> CanvasComponentActionResult:
    return CanvasComponentActionResult(component.id, action, "success", message, data=data or {})


def _result_data(result: Any) -> dict[str, Any]:
    if result is None:
        return {}
    if hasattr(result, "results") and hasattr(result, "recipe_id"):
        return {
            "recipe_id": str(getattr(result, "recipe_id", "") or ""),
            "recipe_name": str(getattr(result, "recipe_name", "") or ""),
            "success": bool(getattr(result, "success", False)),
            "status": "success" if bool(getattr(result, "success", False)) else "failed",
            "run_dir": str(getattr(result, "run_dir", "") or ""),
            "results": [_step_result_data(item) for item in getattr(result, "results", [])],
        }
    if hasattr(result, "to_dict"):
        converted = result.to_dict()
        if isinstance(converted, dict):
            return converted
    if isinstance(result, dict):
        return dict(result)
    return {"result": str(result)}


def _step_result_data(result: Any) -> dict[str, Any]:
    return {
        "index": getattr(result, "index", None),
        "step_name": str(getattr(result, "step_name", "") or ""),
        "action": str(getattr(result, "action", "") or ""),
        "status": str(getattr(result, "status", "") or ""),
        "message": str(getattr(result, "message", "") or ""),
        "phase": str(getattr(result, "phase", "") or ""),
        "dry_run": bool(getattr(result, "dry_run", False)),
    }
