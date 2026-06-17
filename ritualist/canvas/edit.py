from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ritualist.errors import RitualistError
from ritualist.paths import canvases_dir

from .models import (
    CanvasBindingKind,
    CanvasComponent,
    CanvasComponentBinding,
    CanvasComponentPropSchema,
    CanvasComponentProps,
    CanvasComponentType,
    CanvasDocument,
)
from .registry import CanvasComponentRegistry, create_component_registry, validate_canvas_structure
from .storage import CanvasWriteResult, list_canvases, load_canvas, save_canvas
from .storage import _bundled_canvas_paths

CANVAS_EDIT_MODEL_SCHEMA_VERSION = "ritualist.canvas.edit_model.v1"
_HIDDEN_EDIT_PALETTE_TYPES = frozenset({"app.launcher", "window.layout_button"})


class CanvasEditCommandType(StrEnum):
    CREATE_COMPONENT = "create_component"
    DELETE_COMPONENT = "delete_component"
    SELECT_COMPONENT = "select_component"
    MOVE_COMPONENT = "move_component"
    RESIZE_COMPONENT = "resize_component"
    CHANGE_Z = "change_z"
    EDIT_PROPS = "edit_props"
    EDIT_BINDING = "edit_binding"
    DUPLICATE_COMPONENT = "duplicate_component"
    SAVE = "save"
    DISCARD = "discard"
    UNDO = "undo"
    REDO = "redo"


@dataclass(frozen=True)
class CanvasSelection:
    component_id: str | None = None

    @property
    def has_selection(self) -> bool:
        return bool(self.component_id)

    def to_dict(self) -> dict[str, Any]:
        return {"component_id": self.component_id}


@dataclass(frozen=True)
class CanvasPropertyEdit:
    name: str
    label: str
    type: str
    required: bool = False
    default: Any | None = None
    allowed_values: tuple[str, ...] = ()
    editor_hint: str = ""

    @classmethod
    def from_schema(cls, schema: CanvasComponentPropSchema) -> "CanvasPropertyEdit":
        return cls(
            name=schema.name,
            label=_prop_label(schema.name),
            type=schema.type.value,
            required=schema.required,
            default=schema.default,
            allowed_values=tuple(schema.allowed_values),
            editor_hint=schema.editor_hint,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "type": self.type,
            "required": self.required,
            "default": self.default,
            "allowed_values": list(self.allowed_values),
            "editor_hint": self.editor_hint,
        }


@dataclass(frozen=True)
class CanvasComponentPaletteEntry:
    type_id: str
    display_name: str
    category: str
    description: str
    default_width: int
    default_height: int
    property_schema: tuple[CanvasPropertyEdit, ...] = ()
    supported_bindings: tuple[str, ...] = ()

    @classmethod
    def from_component_type(cls, component_type: CanvasComponentType) -> "CanvasComponentPaletteEntry":
        return cls(
            type_id=component_type.type_id,
            display_name=component_type.display_name,
            category=_palette_category(component_type),
            description=component_type.description,
            default_width=component_type.default_width,
            default_height=component_type.default_height,
            property_schema=tuple(
                CanvasPropertyEdit.from_schema(schema) for schema in component_type.prop_schemas
            ),
            supported_bindings=tuple(kind.value for kind in component_type.supported_bindings),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "type_id": self.type_id,
            "display_name": self.display_name,
            "category": self.category,
            "description": self.description,
            "default_width": self.default_width,
            "default_height": self.default_height,
            "property_schema": [field.to_dict() for field in self.property_schema],
            "supported_bindings": list(self.supported_bindings),
        }


@dataclass(frozen=True)
class CanvasEditCommand:
    type: CanvasEditCommandType
    component_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "component_id": self.component_id,
            "payload": self.payload,
        }


@dataclass
class CanvasEditHistory:
    undo_stack: list[CanvasDocument] = field(default_factory=list)
    redo_stack: list[CanvasDocument] = field(default_factory=list)
    commands: list[CanvasEditCommand] = field(default_factory=list)

    @property
    def can_undo(self) -> bool:
        return bool(self.undo_stack)

    @property
    def can_redo(self) -> bool:
        return bool(self.redo_stack)

    def snapshot(self, document: CanvasDocument, command: CanvasEditCommand) -> None:
        self.undo_stack.append(document.model_copy(deep=True))
        self.redo_stack.clear()
        self.commands.append(command)

    def undo(self, current: CanvasDocument) -> CanvasDocument:
        if not self.undo_stack:
            return current
        self.redo_stack.append(current.model_copy(deep=True))
        return self.undo_stack.pop()

    def redo(self, current: CanvasDocument) -> CanvasDocument:
        if not self.redo_stack:
            return current
        self.undo_stack.append(current.model_copy(deep=True))
        return self.redo_stack.pop()

    def to_dict(self) -> dict[str, Any]:
        return {
            "can_undo": self.can_undo,
            "can_redo": self.can_redo,
            "command_count": len(self.commands),
            "commands": [command.to_dict() for command in self.commands],
        }


@dataclass
class CanvasEditSession:
    document: CanvasDocument
    source_path: Path | None = None
    source: str = "user"
    registry: CanvasComponentRegistry = field(default_factory=create_component_registry)
    original: CanvasDocument | None = None
    selection: CanvasSelection = field(default_factory=CanvasSelection)
    history: CanvasEditHistory = field(default_factory=CanvasEditHistory)
    dirty: bool = False

    def __post_init__(self) -> None:
        if self.original is None:
            self.original = self.document.model_copy(deep=True)

    def create_component(
        self,
        type_id: str,
        *,
        component_id: str | None = None,
        x: float = 0,
        y: float = 0,
        width: float | None = None,
        height: float | None = None,
        props: dict[str, Any] | None = None,
        binding: CanvasComponentBinding | None = None,
    ) -> CanvasComponent:
        spec = self._component_type(type_id)
        if binding is not None:
            _validate_edit_binding_kind(binding.kind)
        resolved_id = self._unique_component_id(component_id or type_id.replace(".", "_").replace("/", "_"))
        component = CanvasComponent(
            id=resolved_id,
            type=type_id,
            x=x,
            y=y,
            width=width or spec.default_width,
            height=height or spec.default_height,
            z=_next_z(self.document),
            props=_default_props(spec, props or {}),
            binding=binding,
        )
        self._validate_component(component)
        self._mutate(
            CanvasEditCommand(
                CanvasEditCommandType.CREATE_COMPONENT,
                component.id,
                {"type_id": type_id},
            ),
            components=(*self.document.components, component),
            select=component.id,
        )
        return component

    def delete_component(self, component_id: str) -> None:
        self._require_component(component_id)
        components = tuple(component for component in self.document.components if component.id != component_id)
        self._mutate(
            CanvasEditCommand(CanvasEditCommandType.DELETE_COMPONENT, component_id),
            components=components,
            select=None if self.selection.component_id == component_id else self.selection.component_id,
        )

    def select_component(self, component_id: str | None) -> None:
        if component_id is not None:
            self._require_component(component_id)
        self.selection = CanvasSelection(component_id)
        self.history.commands.append(CanvasEditCommand(CanvasEditCommandType.SELECT_COMPONENT, component_id))

    def move_component(self, component_id: str, *, x: float, y: float) -> None:
        component = self._require_component(component_id)
        self._replace_component(
            component.model_copy(update={"x": x, "y": y}),
            CanvasEditCommand(CanvasEditCommandType.MOVE_COMPONENT, component_id, {"x": x, "y": y}),
        )

    def resize_component(self, component_id: str, *, width: float, height: float) -> None:
        component = self._require_component(component_id)
        updated = component.model_copy(update={"width": width, "height": height})
        self._validate_component(updated)
        self._replace_component(
            updated,
            CanvasEditCommand(
                CanvasEditCommandType.RESIZE_COMPONENT,
                component_id,
                {"width": width, "height": height},
            ),
        )

    def change_z(self, component_id: str, *, z: int) -> None:
        component = self._require_component(component_id)
        self._replace_component(
            component.model_copy(update={"z": z}),
            CanvasEditCommand(CanvasEditCommandType.CHANGE_Z, component_id, {"z": z}),
        )

    def edit_props(self, component_id: str, props: dict[str, Any], *, replace: bool = False) -> None:
        component = self._require_component(component_id)
        updated_props = props if replace else {**component.props_dict(), **props}
        updated = component.model_copy(update={"props": CanvasComponentProps.model_validate(updated_props)})
        self._validate_component(updated)
        self._replace_component(
            updated,
            CanvasEditCommand(CanvasEditCommandType.EDIT_PROPS, component_id, {"props": props}),
        )

    def edit_binding(self, component_id: str, binding: CanvasComponentBinding | None) -> None:
        component = self._require_component(component_id)
        if binding is not None:
            _validate_edit_binding_kind(binding.kind)
        updated = component.model_copy(update={"binding": binding})
        self._validate_component(updated)
        self._replace_component(
            updated,
            CanvasEditCommand(
                CanvasEditCommandType.EDIT_BINDING,
                component_id,
                {"binding": binding.to_dict() if binding is not None else None},
            ),
        )

    def duplicate_component(self, component_id: str, *, new_id: str | None = None) -> CanvasComponent:
        component = self._require_component(component_id)
        duplicated = component.model_copy(
            update={
                "id": self._unique_component_id(new_id or f"{component.id}_copy"),
                "x": component.x + 24,
                "y": component.y + 24,
                "z": _next_z(self.document),
            },
            deep=True,
        )
        self._validate_component(duplicated)
        self._mutate(
            CanvasEditCommand(
                CanvasEditCommandType.DUPLICATE_COMPONENT,
                component_id,
                {"new_id": duplicated.id},
            ),
            components=(*self.document.components, duplicated),
            select=duplicated.id,
        )
        return duplicated

    def undo(self) -> None:
        if not self.history.can_undo:
            return
        self.document = self.history.undo(self.document)
        self.dirty = _document_changed(self.document, self.original)
        if self.selection.component_id and self._find_component(self.selection.component_id) is None:
            self.selection = CanvasSelection()
        self.history.commands.append(CanvasEditCommand(CanvasEditCommandType.UNDO))

    def redo(self) -> None:
        if not self.history.can_redo:
            return
        self.document = self.history.redo(self.document)
        self.dirty = _document_changed(self.document, self.original)
        self.history.commands.append(CanvasEditCommand(CanvasEditCommandType.REDO))

    def discard(self) -> None:
        if self.original is None:
            return
        self.document = self.original.model_copy(deep=True)
        self.selection = CanvasSelection()
        self.history = CanvasEditHistory()
        self.dirty = False

    def save(self, *, destination: Path | None = None) -> CanvasWriteResult:
        result = validate_canvas_structure(self.document, registry=self.registry)
        if not result.valid:
            raise RitualistError("canvas cannot be saved until validation errors are fixed: " + "; ".join(result.errors))
        target = destination or self.default_save_path()
        if destination is not None and _is_bundled_canvas_path(target):
            raise RitualistError("bundled canvas templates must be saved as a user copy")
        write = save_canvas(self.document, target, overwrite=True)
        self.source_path = write.path
        self.source = "user"
        self.original = self.document.model_copy(deep=True)
        self.dirty = False
        self.history.commands.append(CanvasEditCommand(CanvasEditCommandType.SAVE))
        return write

    def default_save_path(self) -> Path:
        return canvases_dir() / f"{self.document.id}.yaml"

    def palette(self) -> tuple[CanvasComponentPaletteEntry, ...]:
        return tuple(
            CanvasComponentPaletteEntry.from_component_type(spec)
            for spec in self.registry.all()
            if _component_type_is_editable(spec)
        )

    def property_schema(self, type_id: str) -> tuple[CanvasPropertyEdit, ...]:
        spec = self._component_type(type_id)
        return tuple(CanvasPropertyEdit.from_schema(schema) for schema in spec.prop_schemas)

    def to_dict(self) -> dict[str, Any]:
        validation = validate_canvas_structure(self.document, registry=self.registry)
        return {
            "schema_version": CANVAS_EDIT_MODEL_SCHEMA_VERSION,
            "canvas": self.document.to_dict(),
            "source": self.source,
            "source_path": str(self.source_path) if self.source_path is not None else "",
            "save_path": str(self.default_save_path()),
            "dirty": self.dirty,
            "selection": self.selection.to_dict(),
            "history": self.history.to_dict(),
            "palette": [entry.to_dict() for entry in self.palette()],
            "binding_kinds": list(editable_binding_kinds()),
            "validation": validation.to_dict(),
        }

    def _mutate(
        self,
        command: CanvasEditCommand,
        *,
        components: tuple[CanvasComponent, ...],
        select: str | None,
    ) -> None:
        self.history.snapshot(self.document, command)
        self.document = self.document.model_copy(update={"components": components}, deep=True)
        self.selection = CanvasSelection(select)
        self.dirty = True

    def _replace_component(self, component: CanvasComponent, command: CanvasEditCommand) -> None:
        self._validate_component(component)
        components = tuple(
            component if existing.id == component.id else existing
            for existing in self.document.components
        )
        self._mutate(command, components=components, select=component.id)

    def _require_component(self, component_id: str) -> CanvasComponent:
        component = self._find_component(component_id)
        if component is None:
            raise RitualistError(f"canvas component not found: {component_id}")
        return component

    def _find_component(self, component_id: str) -> CanvasComponent | None:
        return next((component for component in self.document.components if component.id == component_id), None)

    def _component_type(self, type_id: str) -> CanvasComponentType:
        try:
            return self.registry.get(type_id)
        except KeyError as exc:
            raise RitualistError(f"unknown canvas component type: {type_id}") from exc

    def _validate_component(self, component: CanvasComponent) -> None:
        try:
            component = CanvasComponent.model_validate(component.to_dict())
        except ValidationError as exc:
            raise RitualistError(str(exc)) from exc
        spec = self._component_type(component.type)
        _validate_props_for_edit(component, spec)
        existing_ids = {row.id for row in self.document.components}
        if component.id in existing_ids:
            components = tuple(
                component if existing.id == component.id else existing
                for existing in self.document.components
            )
        else:
            components = (*self.document.components, component)
        candidate = self.document.model_copy(update={"components": components}, deep=True)
        result = validate_canvas_structure(candidate, registry=self.registry)
        component_errors = [error for error in result.errors if error.startswith(f"{component.id}:")]
        if component_errors:
            raise RitualistError("; ".join(component_errors))

    def _unique_component_id(self, base: str) -> str:
        used = {component.id for component in self.document.components}
        candidate = _safe_component_id(base)
        if candidate not in used:
            return candidate
        counter = 2
        while f"{candidate}_{counter}" in used:
            counter += 1
        return f"{candidate}_{counter}"


def create_edit_session(canvas: str | Path | CanvasDocument) -> CanvasEditSession:
    if isinstance(canvas, CanvasDocument):
        return CanvasEditSession(document=canvas, source="memory")
    path_or_id = str(canvas)
    reference = _find_canvas_reference(path_or_id)
    if reference is not None:
        return CanvasEditSession(
            document=load_canvas(reference.path),
            source_path=reference.path,
            source=reference.source,
        )
    path = Path(path_or_id)
    return CanvasEditSession(document=load_canvas(path), source_path=path, source="path")


def editable_binding_kinds() -> tuple[str, ...]:
    return (
        CanvasBindingKind.RECIPE.value,
        CanvasBindingKind.TARGET_START.value,
        CanvasBindingKind.INTENT.value,
        CanvasBindingKind.STATIC.value,
        CanvasBindingKind.DOCTOR_STATUS.value,
        CanvasBindingKind.RECENT_RUNS.value,
    )


def _validate_edit_binding_kind(kind: CanvasBindingKind) -> None:
    if kind.value not in editable_binding_kinds():
        raise RitualistError(f"binding kind is not editable in Canvas Edit Mode: {kind.value}")


def _component_type_is_editable(component_type: CanvasComponentType) -> bool:
    return component_type.type_id not in _HIDDEN_EDIT_PALETTE_TYPES


def _document_changed(document: CanvasDocument, original: CanvasDocument | None) -> bool:
    if original is None:
        return True
    return document.to_dict() != original.to_dict()


def _validate_props_for_edit(component: CanvasComponent, spec: CanvasComponentType) -> None:
    props = component.props_dict()
    errors: list[str] = []
    allowed_props = _allowed_prop_names(spec)
    for name in sorted(set(props) - allowed_props):
        errors.append(f"{component.id}: unknown prop '{name}' is not editable for {spec.type_id}")
    for schema in spec.prop_schemas:
        value = props.get(schema.name)
        if schema.required and _blank(value):
            errors.append(f"{component.id}: missing required prop '{schema.name}'")
            continue
        if _blank(value):
            continue
        if schema.type.value == "bool" and not isinstance(value, bool):
            errors.append(f"{component.id}: prop '{schema.name}' must be a boolean")
        elif schema.type.value == "int" and (not isinstance(value, int) or isinstance(value, bool)):
            errors.append(f"{component.id}: prop '{schema.name}' must be an integer")
        elif schema.type.value == "float" and (
            not isinstance(value, (int, float)) or isinstance(value, bool)
        ):
            errors.append(f"{component.id}: prop '{schema.name}' must be a number")
        elif schema.type.value == "enum" and str(value) not in set(schema.allowed_values):
            allowed = ", ".join(schema.allowed_values)
            errors.append(f"{component.id}: prop '{schema.name}' must be one of: {allowed}")
        elif schema.type.value not in {"bool", "int", "float", "enum"} and not isinstance(value, str):
            errors.append(f"{component.id}: prop '{schema.name}' must be text")
    if errors:
        raise RitualistError("; ".join(errors))


def _allowed_prop_names(spec: CanvasComponentType) -> set[str]:
    return {
        *(schema.name for schema in spec.prop_schemas),
        *spec.required_props,
        *spec.optional_props,
    }


def _blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _find_canvas_reference(path_or_id: str):
    for reference in list_canvases(include_bundled=True):
        if path_or_id in {reference.canvas_id, str(reference.path)}:
            return reference
    return None


def _is_bundled_canvas_path(path: Path) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    for bundled_path in _bundled_canvas_paths():
        try:
            candidate = bundled_path.resolve()
        except OSError:
            candidate = bundled_path
        if resolved == candidate:
            return True
    return False


def _default_props(spec: CanvasComponentType, overrides: dict[str, Any]) -> CanvasComponentProps:
    props: dict[str, Any] = {
        schema.name: schema.default
        for schema in spec.prop_schemas
        if schema.default is not None
    }
    for schema in spec.prop_schemas:
        if schema.required and schema.name not in props and schema.name not in overrides:
            props[schema.name] = _placeholder_value(schema)
    props.update(overrides)
    return CanvasComponentProps.model_validate(props)


def _placeholder_value(schema: CanvasComponentPropSchema) -> Any:
    if schema.type.value in {"int", "float"}:
        return 0
    if schema.type.value == "bool":
        return False
    if schema.allowed_values:
        return schema.allowed_values[0]
    return schema.name.replace("_", " ").title()


def _next_z(document: CanvasDocument) -> int:
    if not document.components:
        return 0
    return max(component.z for component in document.components) + 1


def _safe_component_id(value: str) -> str:
    cleaned = "".join(character if character.isalnum() or character in {"_", "-"} else "_" for character in value)
    cleaned = cleaned.strip("_-") or "component"
    if not cleaned[0].isalnum():
        cleaned = f"component_{cleaned}"
    return cleaned[:64]


def _prop_label(name: str) -> str:
    return name.replace("_", " ").title()


def _palette_category(component_type: CanvasComponentType) -> str:
    raw = component_type.category.casefold()
    if raw in {"ritual"}:
        return "Ritual"
    if raw in {"target"}:
        return "Target"
    if raw in {"runtime", "diagnostics"}:
        return "Status"
    if raw in {"navigation", "launcher", "window"}:
        return "Controls"
    if raw in {"layout"}:
        return "Layout"
    return "Display"
