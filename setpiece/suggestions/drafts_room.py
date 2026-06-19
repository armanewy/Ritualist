from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import re
from typing import Any
from urllib.parse import urlparse

from setpiece.canvas import (
    CanvasBackground,
    CanvasBackgroundType,
    CanvasBindingKind,
    CanvasComponent,
    CanvasComponentBinding,
    CanvasDocument,
    CanvasMetadata,
    CanvasValidationResult,
    create_component_registry,
    validate_canvas_structure,
)
from setpiece.errors import SetpieceError
from setpiece.rooms import list_rooms

from .models import Suggestion, SuggestionKind
from .review import require_approval_for_draft


ROOM_DRAFT_SCHEMA_VERSION = "setpiece.suggestion.room_draft.v1"

SAFE_ROOM_DRAFT_COMPONENT_TYPES = frozenset(
    {
        "text.label",
        "ritual.card",
        "ritual.status",
        "ritual.controller",
        "shortcut.folder",
        "shortcut.app",
        "shortcut.url",
    }
)
INTERNAL_ROOM_IDS = frozenset({"minimal", "minimal_desktop"})
PROMOTED_HERO_ROOM_IDS = ("gaming", "project", "support_desk")
PROMOTED_HERO_CANVAS_IDS = ("gaming_desktop", "project_room", "helpdesk_desktop")

_ID_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")
_SAFE_REFERENCE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_MAX_LABEL_LENGTH = 96


class RoomDraftError(SetpieceError):
    """Raised when an approved Room suggestion cannot produce a safe draft."""


class RoomDraftValidationError(RoomDraftError):
    """Raised when the generated Canvas draft does not validate."""


@dataclass(frozen=True)
class RoomDraftBuildResult:
    document: CanvasDocument
    validation: CanvasValidationResult

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": ROOM_DRAFT_SCHEMA_VERSION,
            "canvas": self.document.to_dict(),
            "validation": self.validation.to_dict(),
        }


def build_room_draft(
    suggestion: Suggestion,
    *,
    background: CanvasBackground | Mapping[str, Any] | str | None = None,
) -> CanvasDocument:
    """Return an approved, side-effect-free Room draft Canvas document."""

    return build_room_draft_result(suggestion, background=background).document


def create_approved_room_draft(
    suggestion: Suggestion,
    *,
    background: CanvasBackground | Mapping[str, Any] | str | None = None,
) -> CanvasDocument:
    """Compatibility wrapper for callers that prefer create_* naming."""

    return build_room_draft(suggestion, background=background)


def build_room_draft_result(
    suggestion: Suggestion,
    *,
    background: CanvasBackground | Mapping[str, Any] | str | None = None,
) -> RoomDraftBuildResult:
    approved = require_approval_for_draft(suggestion)
    if approved.kind is not SuggestionKind.ROOM_CANVAS:
        raise RoomDraftError("Room draft creation requires a room_canvas suggestion.")

    room_id = _source_room_id(approved)
    if room_id in INTERNAL_ROOM_IDS:
        raise RoomDraftError(f"Room draft creation is not allowed for internal Room {room_id!r}.")

    room_label = _room_label(approved, room_id)
    document = CanvasDocument(
        id=_draft_canvas_id(approved, room_id),
        name=f"{room_label} Draft",
        description=(
            "Review-only Room draft created from an approved suggestion. "
            "No behavior was executed while creating this Canvas."
        ),
        metadata=CanvasMetadata(
            tags=_metadata_tags(room_id),
            use_mode_label="Use Mode",
            edit_mode_label="Edit Room",
        ),
        background=_passthrough_background(background),
        components=tuple(_draft_components(approved, room_label)),
    )

    validation = _validate_generated_document(document)
    return RoomDraftBuildResult(document=document, validation=validation)


def promoted_hero_room_snapshot() -> tuple[tuple[str, str, str], ...]:
    """Return the promoted Room registry shape without mutating it."""

    return tuple((room.room_id, room.name, room.canvas_id) for room in list_rooms())


def _draft_components(suggestion: Suggestion, room_label: str) -> list[CanvasComponent]:
    components: list[CanvasComponent] = [
        CanvasComponent(
            id="draft_title",
            type="text.label",
            x=48,
            y=32,
            width=720,
            height=72,
            z=0,
            props={
                "text": f"{room_label} draft",
                "size": 28,
                "align": "left",
            },
        ),
    ]
    used_ids = {component.id for component in components}
    ritual_count = 0
    shortcut_count = 0

    for action in suggestion.proposed_actions:
        component_type = _component_type_from_action(action)
        if component_type in {"shortcut.folder", "shortcut.app", "shortcut.url"}:
            shortcut = _shortcut_component(action, component_type, shortcut_count, used_ids)
            if shortcut is not None:
                components.append(shortcut)
                used_ids.add(shortcut.id)
                shortcut_count += 1
            continue
        if _is_ritual_action(action):
            components.extend(_ritual_components(action, ritual_count, used_ids))
            used_ids.update(component.id for component in components)
            ritual_count += 1

    if ritual_count == 0:
        components.append(_placeholder_ritual_card(room_label, used_ids))
        used_ids.add(components[-1].id)
    if shortcut_count == 0:
        for component_type in ("shortcut.folder", "shortcut.app"):
            shortcut = _shortcut_component({}, component_type, shortcut_count, used_ids)
            if shortcut is not None:
                components.append(shortcut)
                used_ids.add(shortcut.id)
                shortcut_count += 1

    return components


def _ritual_components(
    action: Mapping[str, Any],
    index: int,
    used_ids: set[str],
) -> list[CanvasComponent]:
    recipe_id = _safe_reference(action.get("recipe_id"))
    title = _action_label(action, default="Review Ritual")
    card_id = _unique_id("ritual", index, used_ids)
    components = [
        CanvasComponent(
            id=card_id,
            type="ritual.card",
            x=48,
            y=128 + index * 336,
            width=520,
            height=240,
            z=10 + index * 10,
            props={
                "title": title,
                "subtitle": "Review recipe binding before use",
                "primary_action": "doctor" if recipe_id else "preview_plan",
                **({"recipe_id": recipe_id} if recipe_id else {}),
            },
            binding=(
                CanvasComponentBinding(kind=CanvasBindingKind.RECIPE, recipe_id=recipe_id)
                if recipe_id
                else None
            ),
        )
    ]
    if not recipe_id:
        return components

    status_id = _unique_id("ritual_status", index, used_ids | {card_id})
    controller_id = _unique_id("ritual_controller", index, used_ids | {card_id, status_id})
    components.extend(
        [
            CanvasComponent(
                id=status_id,
                type="ritual.status",
                x=48,
                y=384 + index * 336,
                width=320,
                height=96,
                z=11 + index * 10,
                props={"title": f"{title} status", "recipe_id": recipe_id},
                binding=CanvasComponentBinding(
                    kind=CanvasBindingKind.RECIPE,
                    recipe_id=recipe_id,
                ),
            ),
            CanvasComponent(
                id=controller_id,
                type="ritual.controller",
                x=384,
                y=384 + index * 336,
                width=320,
                height=96,
                z=12 + index * 10,
                props={
                    "recipe_id": recipe_id,
                    "controls": ("pause", "resume", "stop"),
                },
                binding=CanvasComponentBinding(
                    kind=CanvasBindingKind.RECIPE,
                    recipe_id=recipe_id,
                ),
            ),
        ]
    )
    return components


def _placeholder_ritual_card(room_label: str, used_ids: set[str]) -> CanvasComponent:
    return CanvasComponent(
        id=_unique_id("ritual", 0, used_ids),
        type="ritual.card",
        x=48,
        y=128,
        width=520,
        height=240,
        z=10,
        props={
            "title": f"{room_label} ritual",
            "subtitle": "Bind a reviewed recipe before use",
            "primary_action": "preview_plan",
        },
    )


def _shortcut_component(
    action: Mapping[str, Any],
    component_type: str,
    index: int,
    used_ids: set[str],
) -> CanvasComponent | None:
    title = _action_label(action, default=_default_shortcut_title(component_type))
    props: dict[str, object] = {"title": title}
    binding: CanvasComponentBinding | None = None
    if component_type == "shortcut.url":
        url = _safe_url(action.get("placeholder"))
        if url is None:
            return None
        props["url"] = url
        binding = CanvasComponentBinding(kind=CanvasBindingKind.SHORTCUT_URL, url=url)

    return CanvasComponent(
        id=_unique_id(_component_id_prefix(component_type), index, used_ids),
        type=component_type,
        x=620,
        y=128 + index * 120,
        width=280,
        height=96,
        z=20 + index,
        props=props,
        binding=binding,
    )


def _validate_generated_document(document: CanvasDocument) -> CanvasValidationResult:
    registry = create_component_registry()
    for component in document.components:
        if component.type not in SAFE_ROOM_DRAFT_COMPONENT_TYPES:
            raise RoomDraftError(f"{component.id}: component type is not allowed in Room drafts.")
        if not registry.has(component.type):
            raise RoomDraftError(f"{component.id}: component type is not a built-in Canvas type.")
    validation = validate_canvas_structure(document, registry=registry)
    if not validation.valid:
        details = "; ".join(validation.errors)
        raise RoomDraftValidationError(f"Generated Room draft failed validation: {details}")
    return validation


def _passthrough_background(
    background: CanvasBackground | Mapping[str, Any] | str | None,
) -> CanvasBackground:
    if background is None:
        resolved = CanvasBackground(type=CanvasBackgroundType.SYSTEM_WALLPAPER)
    elif isinstance(background, CanvasBackground):
        resolved = background
    elif isinstance(background, str):
        alias = background.strip().casefold().replace("-", "_")
        if alias in {"wallpaper", "system", "system_background", "system_wallpaper"}:
            resolved = CanvasBackground(type=CanvasBackgroundType.SYSTEM_WALLPAPER)
        elif alias in {"transparent", "passthrough"}:
            resolved = CanvasBackground(type=CanvasBackgroundType.TRANSPARENT, value="")
        else:
            resolved = CanvasBackground(type=background)
    else:
        resolved = CanvasBackground.model_validate(background)

    if resolved.type not in {
        CanvasBackgroundType.SYSTEM_WALLPAPER,
        CanvasBackgroundType.TRANSPARENT,
    }:
        raise RoomDraftError("Room draft backgrounds must use wallpaper passthrough.")
    return resolved


def _source_room_id(suggestion: Suggestion) -> str:
    for action in suggestion.proposed_actions:
        room_id = _safe_identifier(action.get("room_id"), default="")
        if room_id:
            return room_id
    return _safe_identifier(suggestion.id, default="room")


def _room_label(suggestion: Suggestion, room_id: str) -> str:
    for action in suggestion.proposed_actions:
        label = _safe_label(action.get("label") or action.get("title"))
        if label:
            return label
    title = _safe_label(suggestion.title)
    if title.casefold().startswith("review ") and title.casefold().endswith(" canvas"):
        title = title[7:-7].strip()
    return title or room_id.replace("_", " ").title()


def _component_type_from_action(action: Mapping[str, Any]) -> str:
    for key in ("component_type", "type", "kind"):
        value = _normalized_kind(action.get(key))
        if value in {"shortcut.folder", "shortcut.app", "shortcut.url"}:
            return value
    return ""


def _is_ritual_action(action: Mapping[str, Any]) -> bool:
    if _safe_reference(action.get("recipe_id")):
        return True
    for key in ("kind", "type", "component_type"):
        if _normalized_kind(action.get(key)) == "ritual_recipe":
            return True
    return False


def _normalized_kind(value: object) -> str:
    text = str(value or "").strip().casefold()
    return text.replace("_", ".") if text.startswith("shortcut_") else text


def _action_label(action: Mapping[str, Any], *, default: str) -> str:
    return _safe_label(action.get("label") or action.get("title") or default) or default


def _default_shortcut_title(component_type: str) -> str:
    return {
        "shortcut.folder": "Review Folder Shortcut",
        "shortcut.app": "Review App Shortcut",
        "shortcut.url": "Review URL Shortcut",
    }[component_type]


def _component_id_prefix(component_type: str) -> str:
    return component_type.split(".", maxsplit=1)[1]


def _safe_url(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    parsed = urlparse(text)
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.netloc:
        return None
    if parsed.username or parsed.password:
        return None
    return text


def _safe_reference(value: object) -> str:
    text = str(value or "").strip()
    if not text or not _SAFE_REFERENCE_RE.fullmatch(text):
        return ""
    return text


def _safe_label(value: object) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    text = " ".join(text.split())
    if not text or text == "[redacted]":
        return ""
    return text[:_MAX_LABEL_LENGTH]


def _safe_identifier(value: object, *, default: str) -> str:
    words = _ID_TOKEN_RE.findall(str(value or ""))
    text = "_".join(words).casefold()
    if not text:
        text = default
    text = text.strip("_") or default
    return text[:64].rstrip("_") or default


def _unique_id(prefix: str, index: int, used_ids: set[str]) -> str:
    candidate = _safe_identifier(f"{prefix}_{index + 1}", default=prefix)
    if candidate not in used_ids:
        return candidate
    offset = index + 2
    while True:
        candidate = _safe_identifier(f"{prefix}_{offset}", default=prefix)
        if candidate not in used_ids:
            return candidate
        offset += 1


def _draft_canvas_id(suggestion: Suggestion, room_id: str) -> str:
    return _safe_identifier(f"{room_id}_{suggestion.id}_draft", default="room_draft")


def _metadata_tags(room_id: str) -> tuple[str, ...]:
    tags = ["suggestion_draft", "room_canvas", "review_required"]
    if room_id:
        tags.append(f"source_{room_id}")
    return tuple(tags)


__all__ = [
    "INTERNAL_ROOM_IDS",
    "PROMOTED_HERO_CANVAS_IDS",
    "PROMOTED_HERO_ROOM_IDS",
    "ROOM_DRAFT_SCHEMA_VERSION",
    "SAFE_ROOM_DRAFT_COMPONENT_TYPES",
    "RoomDraftBuildResult",
    "RoomDraftError",
    "RoomDraftValidationError",
    "build_room_draft",
    "build_room_draft_result",
    "create_approved_room_draft",
    "promoted_hero_room_snapshot",
]
