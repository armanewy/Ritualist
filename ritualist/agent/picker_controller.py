from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from ritualist.agent.picker_model import PickerModel


class PickerIntentKind(StrEnum):
    SELECT_RITUAL = "select_ritual"
    OPEN_PREFLIGHT = "open_preflight"
    BROWSE_ALL = "browse_all"
    OPEN_BUILDER = "open_builder"
    CHANGE_ROOM = "change_room"
    RETURN_TO_ACTIVE = "return_to_active"


_SAFE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass(frozen=True, slots=True)
class PickerIntent:
    kind: PickerIntentKind
    recipe_id: str = ""
    room_id: str = ""

    def __post_init__(self) -> None:
        kind = PickerIntentKind(self.kind)
        object.__setattr__(self, "kind", kind)
        recipe_id = self.recipe_id.strip()
        room_id = self.room_id.strip()
        _validate_intent(kind, recipe_id=recipe_id, room_id=room_id)
        object.__setattr__(self, "recipe_id", recipe_id)
        object.__setattr__(self, "room_id", room_id)

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind.value,
            "recipe_id": self.recipe_id,
            "room_id": self.room_id,
        }


class PickerController:
    def __init__(self, model: PickerModel) -> None:
        self._model = model
        self._events: list[PickerIntent] = []

    @property
    def events(self) -> tuple[PickerIntent, ...]:
        return tuple(self._events)

    def select_ritual(self, recipe_id: str) -> PickerIntent:
        self._require_recipe(recipe_id)
        return self._emit(PickerIntent(PickerIntentKind.SELECT_RITUAL, recipe_id=recipe_id))

    def open_preflight(self, recipe_id: str | None = None) -> PickerIntent:
        resolved = recipe_id or (
            self._model.selected_ritual.recipe_id if self._model.selected_ritual else ""
        )
        self._require_recipe(resolved)
        return self._emit(PickerIntent(PickerIntentKind.OPEN_PREFLIGHT, recipe_id=resolved))

    def browse_all(self) -> PickerIntent:
        return self._emit(PickerIntent(PickerIntentKind.BROWSE_ALL))

    def open_builder(self) -> PickerIntent:
        return self._emit(PickerIntent(PickerIntentKind.OPEN_BUILDER))

    def change_room(self, room_id: str) -> PickerIntent:
        self._require_room(room_id)
        return self._emit(PickerIntent(PickerIntentKind.CHANGE_ROOM, room_id=room_id))

    def return_to_active(self) -> PickerIntent:
        active = self._model.active_ritual
        if active is None:
            raise ValueError("no active ritual to return to")
        self._require_recipe(active.recipe_id)
        return self._emit(
            PickerIntent(PickerIntentKind.RETURN_TO_ACTIVE, recipe_id=active.recipe_id)
        )

    def _emit(self, event: PickerIntent) -> PickerIntent:
        self._events.append(event)
        return event

    def _require_recipe(self, recipe_id: str) -> None:
        text = recipe_id.strip()
        if not text or not _SAFE_TOKEN_RE.fullmatch(text):
            raise ValueError("recipe id must be a safe catalog token")
        known = {ritual.recipe_id for ritual in self._model.matching_rituals}
        known.update(ritual.recipe_id for ritual in self._model.recent_rituals)
        if self._model.selected_ritual is not None:
            known.add(self._model.selected_ritual.recipe_id)
        if self._model.active_ritual is not None:
            known.add(self._model.active_ritual.recipe_id)
        if text not in known:
            raise ValueError(f"unknown picker ritual: {text}")

    def _require_room(self, room_id: str) -> None:
        text = room_id.strip()
        if not text or not _SAFE_TOKEN_RE.fullmatch(text):
            raise ValueError("room id must be a safe catalog token")
        if text not in {room.room_id for room in self._model.rooms}:
            raise ValueError(f"unknown picker room: {text}")


def _validate_intent(kind: PickerIntentKind, *, recipe_id: str, room_id: str) -> None:
    if recipe_id and not _SAFE_TOKEN_RE.fullmatch(recipe_id):
        raise ValueError("recipe id must be a safe catalog token")
    if room_id and not _SAFE_TOKEN_RE.fullmatch(room_id):
        raise ValueError("room id must be a safe catalog token")
    if kind in {
        PickerIntentKind.SELECT_RITUAL,
        PickerIntentKind.OPEN_PREFLIGHT,
        PickerIntentKind.RETURN_TO_ACTIVE,
    } and not recipe_id:
        raise ValueError(f"{kind.value} requires a recipe id")
    if kind is PickerIntentKind.CHANGE_ROOM and not room_id:
        raise ValueError("change_room requires a room id")
    if kind is not PickerIntentKind.CHANGE_ROOM and room_id:
        raise ValueError(f"{kind.value} cannot carry a room id")
    if kind not in {
        PickerIntentKind.SELECT_RITUAL,
        PickerIntentKind.OPEN_PREFLIGHT,
        PickerIntentKind.RETURN_TO_ACTIVE,
    } and recipe_id:
        raise ValueError(f"{kind.value} cannot carry a recipe id")


__all__ = [
    "PickerController",
    "PickerIntent",
    "PickerIntentKind",
]
