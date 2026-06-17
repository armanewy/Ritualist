from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import CanvasComponent, CanvasDocument
from .runtime import CanvasRuntimeContext, CanvasRuntimeModel, build_canvas_runtime_model

CANVAS_VIEW_MODEL_SCHEMA_VERSION = "ritualist.canvas.view_model.v1"


@dataclass(frozen=True)
class CanvasUseComponentView:
    id: str
    type: str
    x: float
    y: float
    width: float
    height: float
    z: int = 0
    visible: bool = True
    title: str = ""
    subtitle: str = ""
    message: str = ""
    state: str = "idle"
    status: str = "ready"
    binding: dict[str, str] = field(default_factory=dict)
    props: dict[str, Any] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)
    enabled_actions: tuple[str, ...] = ()
    disabled_actions: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "z": self.z,
            "visible": self.visible,
            "title": self.title,
            "subtitle": self.subtitle,
            "message": self.message,
            "state": self.state,
            "status": self.status,
            "binding": self.binding,
            "props": self.props,
            "data": self.data,
            "enabled_actions": list(self.enabled_actions),
            "disabled_actions": list(self.disabled_actions),
            "warnings": list(self.warnings),
            "display_only": not self.enabled_actions,
        }


@dataclass(frozen=True)
class CanvasViewModel:
    canvas: CanvasDocument
    runtime: CanvasRuntimeModel
    components: tuple[CanvasUseComponentView, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": CANVAS_VIEW_MODEL_SCHEMA_VERSION,
            "canvas": {
                "id": self.canvas.id,
                "name": self.canvas.name,
                "description": self.canvas.description,
                "mode": self.canvas.mode.value,
                "resolution_policy": self.canvas.resolution_policy.value,
                "background": self.canvas.background.model_dump(mode="json"),
                "grid": self.canvas.grid.model_dump(mode="json"),
                "theme": self.runtime.theme,
            },
            "components": [component.to_dict() for component in self.components],
            "runtime": self.runtime.to_dict(),
        }


def build_canvas_view_model(
    document: CanvasDocument,
    *,
    context: CanvasRuntimeContext | None = None,
) -> CanvasViewModel:
    runtime = build_canvas_runtime_model(document, context=context)
    states = {state.component_id: state for state in runtime.component_states}
    components = tuple(
        _component_view(component, states.get(component.id))
        for component in sorted(document.components, key=lambda item: (item.z, item.id))
    )
    return CanvasViewModel(canvas=document, runtime=runtime, components=components)


def _component_view(component: CanvasComponent, state: Any | None) -> CanvasUseComponentView:
    props = component.props_dict()
    return CanvasUseComponentView(
        id=component.id,
        type=component.type,
        x=component.x,
        y=component.y,
        width=component.width,
        height=component.height,
        z=component.z,
        visible=component.visible,
        title=str(getattr(state, "title", "") or props.get("title") or props.get("text") or component.id),
        subtitle=str(getattr(state, "subtitle", "") or props.get("subtitle") or ""),
        message=str(getattr(state, "message", "") or ""),
        state=str(getattr(state, "state", "") or "idle"),
        status=str(getattr(state, "status", "") or "ready"),
        binding=dict(getattr(state, "to_dict", lambda: {"binding": {}})().get("binding", {}))
        if state is not None
        else {},
        props=props,
        data=dict(getattr(state, "data", {}) or {}),
        enabled_actions=tuple(getattr(state, "enabled_actions", ()) or ()),
        disabled_actions=tuple(getattr(state, "disabled_actions", ()) or ()),
        warnings=tuple(getattr(state, "warnings", ()) or ()),
    )
