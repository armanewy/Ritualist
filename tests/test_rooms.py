from __future__ import annotations

import json

from typer.testing import CliRunner

from ritualist.canvas import load_bundled_canvas, validate_canvas_document
from ritualist.canvas.storage import canvas_show_payload
from ritualist.canvas.theme_bridge import validate_canvas_theme_selection
from ritualist.cli import app
from ritualist.rooms import room_list_payload, room_show_payload


EXPECTED_ROOM_IDS = {"gaming", "project", "support_desk"}


def test_room_list_cli_exposes_starter_rooms() -> None:
    result = CliRunner().invoke(app, ["room", "list", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["schema_version"] == "ritualist.rooms.v1"
    assert {room["id"] for room in payload["rooms"]} == EXPECTED_ROOM_IDS
    assert {room["canvas_id"] for room in payload["rooms"]} == {
        "gaming_desktop",
        "project_room",
        "helpdesk_desktop",
    }


def test_room_show_alias_matches_bundled_canvas_payload() -> None:
    for room in room_list_payload()["rooms"]:
        room_payload = room_show_payload(str(room["id"]))
        canvas_payload = canvas_show_payload(load_bundled_canvas(str(room["canvas_id"])))

        assert room_payload["schema_version"] == "ritualist.room.show.v1"
        assert room_payload["room"] == room
        assert room_payload["canvas"] == canvas_payload["canvas"]
        assert room_payload["validation"] == canvas_payload["validation"]


def test_room_show_cli_uses_room_alias_without_executing_bindings() -> None:
    result = CliRunner().invoke(app, ["room", "show", "support_desk", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["room"]["id"] == "support_desk"
    assert payload["room"]["canvas_id"] == "helpdesk_desktop"
    assert payload["canvas"]["name"] == "Support Desk"
    assert payload["validation"]["valid"] is True


def test_legacy_helpdesk_room_alias_remains_compatible() -> None:
    result = CliRunner().invoke(app, ["room", "show", "helpdesk", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["room"]["id"] == "support_desk"


def test_starter_rooms_validate_use_safe_themes_and_safe_bindings() -> None:
    forbidden_prop_markers = ("script", "javascript", "qml", "html", "webview", "code", "onclick", "on_click")

    for room in room_list_payload()["rooms"]:
        document = load_bundled_canvas(str(room["canvas_id"]))
        validation = validate_canvas_document(document)
        theme = validate_canvas_theme_selection(document)

        assert validation.valid, (room["id"], validation.errors)
        assert validation.errors == ()
        assert theme.valid, (room["id"], theme.errors)

        for component in document.components:
            props = component.props_dict()
            assert not any(
                marker in key.casefold()
                for key in props
                for marker in forbidden_prop_markers
            ), (room["id"], component.id, props)
            assert not any(
                isinstance(value, str) and "<script" in value.casefold()
                for value in props.values()
            ), (room["id"], component.id, props)


def test_room_alias_rejects_unknown_room() -> None:
    result = CliRunner().invoke(app, ["room", "show", "unknown", "--json"])

    assert result.exit_code == 1
    assert "room not found" in result.output
