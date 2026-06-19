from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from setpiece.errors import SetpieceError

from .canvas.storage import canvas_show_payload, load_bundled_canvas

ROOM_LIST_SCHEMA_VERSION = "setpiece.rooms.v1"
ROOM_SHOW_SCHEMA_VERSION = "setpiece.room.show.v1"


@dataclass(frozen=True)
class RoomTemplate:
    room_id: str
    name: str
    canvas_id: str
    description: str
    category: str

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.room_id,
            "name": self.name,
            "canvas_id": self.canvas_id,
            "description": self.description,
            "category": self.category,
        }


_STARTER_ROOMS: tuple[RoomTemplate, ...] = (
    RoomTemplate(
        "gaming",
        "Gaming Room",
        "gaming_desktop",
        "A gaming setup Room with explicit ritual controls and Diablo IV target preview.",
        "gaming",
    ),
    RoomTemplate(
        "project",
        "Project Room",
        "project_room",
        "A project setup Room with safe plan previews, launch placeholders, and recent runs.",
        "work",
    ),
    RoomTemplate(
        "support_desk",
        "Support Desk",
        "helpdesk_desktop",
        "A support runbook Room with Doctor, diagnostics, status, and recent runs.",
        "support",
    ),
)

_ROOM_ALIASES = {
    "helpdesk": "support_desk",
    "helpdesk_desktop": "support_desk",
}


def list_rooms() -> tuple[RoomTemplate, ...]:
    return _STARTER_ROOMS


def room_by_id(room_id: str) -> RoomTemplate:
    normalized = room_id.strip().casefold()
    normalized = _ROOM_ALIASES.get(normalized, normalized)
    for room in _STARTER_ROOMS:
        if room.room_id == normalized or room.canvas_id == normalized:
            return room
    raise SetpieceError(f"room not found: {room_id}")


def room_list_payload() -> dict[str, Any]:
    return {
        "schema_version": ROOM_LIST_SCHEMA_VERSION,
        "rooms": [room.to_dict() for room in list_rooms()],
    }


def room_show_payload(room_id: str) -> dict[str, Any]:
    room = room_by_id(room_id)
    document = load_bundled_canvas(room.canvas_id)
    canvas_payload = canvas_show_payload(document)
    return {
        "schema_version": ROOM_SHOW_SCHEMA_VERSION,
        "room": room.to_dict(),
        "canvas": canvas_payload["canvas"],
        "validation": canvas_payload["validation"],
    }
