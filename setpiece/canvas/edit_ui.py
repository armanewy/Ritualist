from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from setpiece.errors import SetpieceError
from setpiece.suggestions.models import Suggestion, SuggestionKind
from setpiece.suggestions.review import approve_suggestion, dismiss_suggestion, review_snapshot
from setpiece.suggestions.service import (
    SuggestionsServiceError,
    delete_all_suggestions_payload,
    list_suggestions_payload,
    scan_suggestions_payload,
)
from setpiece.suggestions.storage import SuggestionStore

from .edit import CanvasEditSession
from .models import CanvasBindingKind, CanvasComponent, CanvasComponentBinding
from .storage import CanvasWriteResult

CANVAS_EDIT_UI_SCHEMA_VERSION = "setpiece.canvas.edit_ui.v1"
CANVAS_SUGGESTIONS_REVIEW_UI_SCHEMA_VERSION = "setpiece.canvas.suggestions_review_ui.v1"
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
SUGGESTION_FILTERS = (
    {"id": "all", "label": "All"},
    {"id": "shortcut", "label": "Shortcut"},
    {"id": "ritual", "label": "Ritual"},
    {"id": "room", "label": "Room"},
)
_FILTER_KIND = {
    "shortcut": SuggestionKind.SHORTCUT_COMPONENT,
    "ritual": SuggestionKind.RITUAL_RECIPE,
    "room": SuggestionKind.ROOM_CANVAS,
}


@dataclass
class CanvasSuggestionsReviewBridge:
    """Review-gated, data-only Suggestions surface for Canvas Edit Mode."""

    store: SuggestionStore = field(default_factory=SuggestionStore)
    config_path: Path | None = None
    filter_kind: str = "all"
    selected_suggestion_id: str = ""
    last_message: str = "Suggestions ready"
    last_error: str = ""
    last_draft: dict[str, Any] = field(default_factory=dict)
    editing_before_create: bool = False

    def model(self) -> dict[str, Any]:
        suggestions: list[Suggestion] = []
        error = self.last_error
        try:
            payload = list_suggestions_payload(store=self.store, config_path=self.config_path)
            suggestions = [
                suggestion
                for suggestion in (
                    Suggestion.from_mapping(item)
                    for item in payload.get("suggestions", [])
                    if isinstance(item, dict)
                )
                if self._matches_filter(suggestion)
            ]
        except (SuggestionsServiceError, ValueError) as exc:
            error = str(exc)

        selected = next(
            (suggestion for suggestion in suggestions if suggestion.id == self.selected_suggestion_id),
            None,
        )
        return {
            "schema_version": CANVAS_SUGGESTIONS_REVIEW_UI_SCHEMA_VERSION,
            "filters": [dict(item) for item in SUGGESTION_FILTERS],
            "filter": self.filter_kind,
            "count": len(suggestions),
            "suggestions": [_suggestion_review_row(suggestion) for suggestion in suggestions],
            "selected_suggestion_id": self.selected_suggestion_id if selected is not None else "",
            "selected_suggestion": _suggestion_review_row(selected) if selected is not None else {},
            "editing_before_create": self.editing_before_create and selected is not None,
            "last_draft": dict(self.last_draft),
            "last_message": self.last_message,
            "error": error,
            "review_required": True,
            "auto_create": False,
            "auto_run": False,
        }

    def set_filter(self, filter_kind: str) -> dict[str, Any]:
        self.filter_kind = _normalized_filter(filter_kind)
        return self.model()

    def find_suggestions(self) -> dict[str, Any]:
        self.last_error = ""
        try:
            payload = scan_suggestions_payload(store=self.store, config_path=self.config_path)
        except SuggestionsServiceError as exc:
            self.last_error = str(exc)
            self.last_message = "Suggestions scan needs Local Learning consent"
            return self.model()
        self.last_message = (
            f"Found {int(payload.get('suggestion_count') or 0)} Suggestions; "
            "nothing was created or run."
        )
        return self.model()

    def review_suggestion(self, suggestion_id: str) -> dict[str, Any]:
        self.last_error = ""
        self.last_draft = {}
        try:
            approved = approve_suggestion(
                self.store,
                suggestion_id,
                reviewed_by="canvas_builder",
            )
        except Exception as exc:  # noqa: BLE001 - review failures are user-facing policy errors.
            self.last_error = str(exc)
            self.last_message = "Suggestion review failed"
            return self.model()
        self.selected_suggestion_id = approved.id
        self.editing_before_create = False
        self.last_message = "Suggestion reviewed; draft creation is now available."
        return self.model()

    def edit_before_creating(self, suggestion_id: str) -> dict[str, Any]:
        self.selected_suggestion_id = str(suggestion_id or "").strip()
        self.editing_before_create = bool(self.selected_suggestion_id)
        self.last_draft = {}
        self.last_error = ""
        self.last_message = "Review fields before creating a disabled draft."
        return self.model()

    def create_draft(self, suggestion_id: str) -> dict[str, Any]:
        self.last_error = ""
        suggestion = self.store.get(suggestion_id)
        if suggestion is None:
            self.last_error = f"suggestion not found: {suggestion_id}"
            self.last_message = "Draft creation failed"
            return self.model()
        try:
            draft = _build_suggestion_draft_preview(suggestion)
        except Exception as exc:  # noqa: BLE001 - draft builders raise several user-facing errors.
            self.last_error = str(exc)
            self.last_message = "Draft creation failed"
            return self.model()
        self.selected_suggestion_id = suggestion.id
        self.editing_before_create = False
        self.last_draft = {
            "suggestion_id": suggestion.id,
            "kind": suggestion.kind.value,
            "created_artifact": False,
            "wrote_files": False,
            "ran": False,
            "draft": draft,
        }
        self.last_message = "Disabled draft preview created; no files were written."
        return self.model()

    def dismiss_suggestion(self, suggestion_id: str) -> dict[str, Any]:
        self.last_error = ""
        try:
            dismissed = dismiss_suggestion(
                self.store,
                suggestion_id,
                reviewed_by="canvas_builder",
            )
        except Exception as exc:  # noqa: BLE001 - dismissal failures belong in UI status.
            self.last_error = str(exc)
            self.last_message = "Suggestion dismiss failed"
            return self.model()
        if self.selected_suggestion_id == dismissed.id:
            self.selected_suggestion_id = ""
            self.editing_before_create = False
            self.last_draft = {}
        self.last_message = "Suggestion dismissed."
        return self.model()

    def delete_all(self) -> dict[str, Any]:
        self.last_error = ""
        try:
            payload = delete_all_suggestions_payload(store=self.store, config_path=self.config_path)
        except SuggestionsServiceError as exc:
            self.last_error = str(exc)
            self.last_message = "Delete all Suggestions failed"
            return self.model()
        self.selected_suggestion_id = ""
        self.editing_before_create = False
        self.last_draft = {}
        self.last_message = f"Deleted {int(payload.get('deleted_count') or 0)} Suggestions."
        return self.model()

    def _matches_filter(self, suggestion: Suggestion) -> bool:
        kind = _FILTER_KIND.get(self.filter_kind)
        return kind is None or suggestion.kind is kind


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
            raise SetpieceError(f"component type is not available in Canvas Edit Mode UI: {type_id}")
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
            raise SetpieceError(f"{component_id}: prop '{name}' has invalid value: {value}") from exc
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
        raise SetpieceError(f"binding kind is not editable in Canvas Edit Mode: {kind}") from exc
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
    raise SetpieceError(f"binding kind is not editable in Canvas Edit Mode: {kind}")


def _suggestion_review_row(suggestion: Suggestion | None) -> dict[str, Any]:
    if suggestion is None:
        return {}
    snapshot = review_snapshot(suggestion)
    return {
        **suggestion.to_dict(),
        "kind_label": _kind_label(suggestion.kind),
        "confidence_badge": f"Confidence {round(suggestion.confidence * 100)}%",
        "evidence_badge": f"Evidence {suggestion.evidence_count}",
        "privacy_badge": f"Privacy {suggestion.privacy_level.value}",
        "review_token": snapshot.review_token,
        "proposed_artifact_summary": snapshot.proposed_artifact_summary,
        "approval_current": snapshot.approval_current,
        "can_create_draft": snapshot.can_create_draft,
    }


def _build_suggestion_draft_preview(suggestion: Suggestion) -> dict[str, Any]:
    if suggestion.kind is SuggestionKind.SHORTCUT_COMPONENT:
        from setpiece.suggestions.drafts_shortcut import build_shortcut_draft

        return build_shortcut_draft(suggestion)
    if suggestion.kind is SuggestionKind.RITUAL_RECIPE:
        from setpiece.suggestions.drafts_recipe import build_draft_recipe

        return build_draft_recipe(suggestion)
    if suggestion.kind is SuggestionKind.ROOM_CANVAS:
        from setpiece.suggestions.drafts_room import build_room_draft_result

        return build_room_draft_result(suggestion).to_dict()
    raise SetpieceError("Only shortcut, ritual, and room Suggestions can create drafts in Room Builder.")


def _normalized_filter(filter_kind: str) -> str:
    text = str(filter_kind or "all").strip().casefold()
    return text if text in {"all", *tuple(_FILTER_KIND)} else "all"


def _kind_label(kind: SuggestionKind) -> str:
    return {
        SuggestionKind.SHORTCUT_COMPONENT: "Shortcut",
        SuggestionKind.RITUAL_RECIPE: "Ritual",
        SuggestionKind.ROOM_CANVAS: "Room",
        SuggestionKind.CLEANUP_HINT: "Cleanup",
    }[kind]
