from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ritualist.errors import RitualistError

from .edit import CanvasEditSession
from .models import CanvasBindingKind, CanvasComponent, CanvasComponentBinding
from .storage import CanvasWriteResult

CANVAS_EDIT_UI_SCHEMA_VERSION = "ritualist.canvas.edit_ui.v1"
EDIT_UI_PALETTE_TYPES = frozenset(
    {
        "ritual.card",
        "target.card",
        "text.label",
        "image",
        "clock",
        "recent.activity",
        "doctor.badge",
        "shortcut.folder",
        "shortcut.app",
        "shortcut.url",
    }
)


@dataclass
class CanvasEditUiBridge:
    """Side-effect-free edit operations exposed to the Canvas UI."""

    session: CanvasEditSession

    @property
    def document(self):
        return self.session.document

    def model(self) -> dict[str, Any]:
        payload = self.session.to_dict()
        selected = self._selected_component()
        payload.update(
            {
                "schema_version": CANVAS_EDIT_UI_SCHEMA_VERSION,
                "palette": [
                    entry
                    for entry in payload.get("palette", [])
                    if entry.get("type_id") in EDIT_UI_PALETTE_TYPES
                ],
                "selected_component": _component_edit_payload(selected, self.session)
                if selected is not None
                else {},
            }
        )
        return payload

    def select(self, component_id: str | None) -> dict[str, Any]:
        self.session.select_component(component_id or None)
        return self.model()

    def create_component(self, type_id: str) -> dict[str, Any]:
        if type_id not in EDIT_UI_PALETTE_TYPES:
            raise RitualistError(f"component type is not available in Canvas Edit Mode UI: {type_id}")
        self.session.create_component(type_id, x=64, y=64)
        return self.model()

    def delete_selected(self) -> dict[str, Any]:
        component_id = self.session.selection.component_id
        if component_id:
            self.session.delete_component(component_id)
        return self.model()

    def duplicate_selected(self) -> dict[str, Any]:
        component_id = self.session.selection.component_id
        if component_id:
            self.session.duplicate_component(component_id)
        return self.model()

    def move_component(self, component_id: str, x: float, y: float) -> dict[str, Any]:
        self.session.move_component(component_id, x=self._snap(x), y=self._snap(y))
        return self.model()

    def resize_component(self, component_id: str, width: float, height: float) -> dict[str, Any]:
        self.session.resize_component(
            component_id,
            width=max(16, self._snap(width)),
            height=max(16, self._snap(height)),
        )
        return self.model()

    def edit_property(self, component_id: str, name: str, value: object) -> dict[str, Any]:
        try:
            coerced = _coerce_property_value(name, value, self.session, component_id)
        except ValueError as exc:
            raise RitualistError(f"{component_id}: prop '{name}' has invalid value: {value}") from exc
        self.session.edit_props(component_id, {name: coerced})
        return self.model()

    def edit_binding(self, component_id: str, kind: str, reference: str = "") -> dict[str, Any]:
        binding = _binding_for_edit(kind, reference)
        self.session.edit_binding(component_id, binding)
        return self.model()

    def undo(self) -> dict[str, Any]:
        self.session.undo()
        return self.model()

    def redo(self) -> dict[str, Any]:
        self.session.redo()
        return self.model()

    def discard(self) -> dict[str, Any]:
        self.session.discard()
        return self.model()

    def save(self, *, destination: Path | None = None) -> CanvasWriteResult:
        return self.session.save(destination=destination)

    def _selected_component(self) -> CanvasComponent | None:
        component_id = self.session.selection.component_id
        if not component_id:
            return None
        return next((component for component in self.session.document.components if component.id == component_id), None)

    def _snap(self, value: float) -> float:
        grid = self.session.document.grid
        if not grid.enabled:
            return float(value)
        size = max(1, int(grid.size))
        return float(round(float(value) / size) * size)


def _component_edit_payload(component: CanvasComponent, session: CanvasEditSession) -> dict[str, Any]:
    spec = session.registry.get(component.type)
    return {
        "id": component.id,
        "type": component.type,
        "x": component.x,
        "y": component.y,
        "width": component.width,
        "height": component.height,
        "z": component.z,
        "props": component.props_dict(),
        "binding": component.binding.to_dict() if component.binding is not None else {},
        "supported_bindings": [kind.value for kind in spec.supported_bindings],
        "property_schema": [field.to_dict() for field in session.property_schema(component.type)],
    }


def _coerce_property_value(
    name: str,
    value: object,
    session: CanvasEditSession,
    component_id: str,
) -> object:
    component = next(component for component in session.document.components if component.id == component_id)
    schemas = {schema.name: schema for schema in session.registry.get(component.type).prop_schemas}
    schema = schemas.get(name)
    if schema is None:
        return value
    if schema.type.value == "bool":
        if isinstance(value, bool):
            return value
        return str(value).strip().casefold() in {"1", "true", "yes", "on"}
    if schema.type.value == "int":
        return int(str(value).strip())
    if schema.type.value == "float":
        return float(str(value).strip())
    return "" if value is None else str(value)


def _binding_for_edit(kind: str, reference: str = "") -> CanvasComponentBinding | None:
    try:
        binding_kind = CanvasBindingKind(str(kind))
    except ValueError as exc:
        raise RitualistError(f"binding kind is not editable in Canvas Edit Mode: {kind}") from exc
    text = str(reference or "").strip()
    if binding_kind is CanvasBindingKind.STATIC:
        return None
    if binding_kind is CanvasBindingKind.RECIPE:
        return CanvasComponentBinding(kind=binding_kind, recipe_id=text)
    if binding_kind is CanvasBindingKind.TARGET_START:
        return CanvasComponentBinding(kind=binding_kind, target=text)
    if binding_kind is CanvasBindingKind.INTENT:
        return CanvasComponentBinding(kind=binding_kind, intent_id=text)
    if binding_kind is CanvasBindingKind.DOCTOR_STATUS:
        return CanvasComponentBinding(kind=binding_kind, id=text)
    if binding_kind is CanvasBindingKind.RECENT_RUNS:
        return CanvasComponentBinding(kind=binding_kind, id=text)
    raise RitualistError(f"binding kind is not editable in Canvas Edit Mode: {kind}")
