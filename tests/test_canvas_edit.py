from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from ritualist.canvas import (
    CanvasBindingKind,
    CanvasComponent,
    CanvasComponentBinding,
    CanvasDocument,
    CanvasEditSession,
    create_edit_session,
    editable_binding_kinds,
    load_canvas,
    save_canvas,
    validate_canvas_structure,
)
from ritualist.canvas.storage import CanvasReference
from ritualist.cli import app
from ritualist.errors import RitualistError


def _canvas() -> CanvasDocument:
    return CanvasDocument(
        id="editable_canvas",
        name="Editable Canvas",
        components=(
            CanvasComponent(
                id="title",
                type="text.label",
                x=10,
                y=20,
                width=200,
                height=64,
                props={"text": "Hello"},
            ),
        ),
    )


def test_edit_session_create_move_resize_delete_component() -> None:
    session = CanvasEditSession(document=_canvas())

    created = session.create_component("clock", component_id="clock", x=50, y=60)
    session.move_component("clock", x=80, y=96)
    session.resize_component("clock", width=220, height=120)
    session.change_z("clock", z=42)
    edited = next(component for component in session.document.components if component.id == "clock")

    assert created.id == "clock"
    assert edited.x == 80
    assert edited.y == 96
    assert edited.width == 220
    assert edited.height == 120
    assert edited.z == 42
    assert session.dirty is True

    session.delete_component("clock")

    assert [component.id for component in session.document.components] == ["title"]


def test_change_z_validates_component_model() -> None:
    session = CanvasEditSession(document=_canvas())

    try:
        session.change_z("title", z=1_000_000)
    except RitualistError as exc:
        assert "z must be between" in str(exc)
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("invalid z should fail validation")


def test_edit_session_prop_validation() -> None:
    session = CanvasEditSession(document=_canvas())

    session.edit_props("title", {"text": "Updated"})

    assert session.document.components[0].props_dict()["text"] == "Updated"

    try:
        session.edit_props("title", {}, replace=True)
    except RitualistError as exc:
        assert "missing required prop 'text'" in str(exc)
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("invalid props should fail validation")

    for props, expected in (
        ({"align": "diagonal"}, "must be one of"),
        ({"size": "large"}, "must be an integer"),
        ({"foo": "bar"}, "unknown prop 'foo'"),
    ):
        try:
            session.edit_props("title", props)
        except RitualistError as exc:
            assert expected in str(exc)
        else:  # pragma: no cover - assertion clarity
            raise AssertionError(f"invalid props should fail validation: {props!r}")


def test_edit_session_allows_declared_optional_props_without_schema() -> None:
    session = CanvasEditSession(document=_canvas())
    dock = session.create_component(
        "category.dock",
        component_id="dock",
        props={"categories": ["Gaming", "Media"]},
    )

    session.edit_props("dock", {"orientation": "vertical"})

    edited = next(component for component in session.document.components if component.id == dock.id)
    assert edited.props_dict()["orientation"] == "vertical"


def test_edit_session_prop_type_validation() -> None:
    session = CanvasEditSession(document=_canvas())

    try:
        session.edit_props("title", {"align": "sideways"})
    except RitualistError as exc:
        assert "must be one of" in str(exc)
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("invalid enum prop should fail validation")

    activity = session.create_component("recent.activity", component_id="activity")
    assert activity.id == "activity"

    try:
        session.edit_props("activity", {"limit": "many"})
    except RitualistError as exc:
        assert "must be an integer" in str(exc)
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("invalid integer prop should fail validation")


def test_edit_session_binding_validation() -> None:
    session = CanvasEditSession(document=_canvas())

    assert CanvasBindingKind.RECIPE.value in editable_binding_kinds()
    assert CanvasBindingKind.STATIC.value in editable_binding_kinds()

    try:
        session.edit_binding(
            "title",
            CanvasComponentBinding(kind=CanvasBindingKind.APP_LAUNCHER, id="launcher"),
        )
    except RitualistError as exc:
        assert "not editable" in str(exc)
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("unsafe binding kind should be rejected")


def test_create_component_rejects_non_editable_binding() -> None:
    session = CanvasEditSession(document=_canvas())

    try:
        session.create_component(
            "ritual.card",
            binding=CanvasComponentBinding(kind=CanvasBindingKind.APP_LAUNCHER, id="launcher"),
        )
    except RitualistError as exc:
        assert "not editable" in str(exc)
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("create_component should reject non-editable bindings")


def test_edit_session_duplicate_undo_redo() -> None:
    session = CanvasEditSession(document=_canvas())

    duplicated = session.duplicate_component("title")

    assert duplicated.id == "title_copy"
    assert [component.id for component in session.document.components] == ["title", "title_copy"]

    session.undo()
    assert [component.id for component in session.document.components] == ["title"]

    session.redo()
    assert [component.id for component in session.document.components] == ["title", "title_copy"]


def test_duplicate_component_validates_copied_component() -> None:
    canvas = CanvasDocument(
        id="max_z_canvas",
        name="Max Z Canvas",
        components=(
            CanvasComponent(
                id="title",
                type="text.label",
                x=10,
                y=20,
                width=200,
                height=64,
                z=10000,
                props={"text": "Hello"},
            ),
        ),
    )
    session = CanvasEditSession(document=canvas)

    try:
        session.duplicate_component("title")
    except RitualistError as exc:
        assert "z must be between" in str(exc)
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("invalid duplicate z should fail validation")


def test_undo_redo_dirty_state_tracks_original_document() -> None:
    session = CanvasEditSession(document=_canvas())

    session.undo()
    session.redo()
    assert session.dirty is False
    assert session.history.commands == []

    session.edit_props("title", {"text": "Changed"})
    assert session.dirty is True

    session.undo()
    assert session.dirty is False
    assert session.document.to_dict() == _canvas().to_dict()

    session.redo()
    assert session.dirty is True
    assert session.document.components[0].props_dict()["text"] == "Changed"


def test_bundled_template_saves_as_user_copy(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "bundled" / "gaming_desktop.yaml"
    save_canvas(_canvas(), source)
    output = tmp_path / "user"
    monkeypatch.setattr("ritualist.canvas.edit.canvases_dir", lambda: output)
    monkeypatch.setattr(
        "ritualist.canvas.edit.list_canvases",
        lambda include_bundled=True: [
            CanvasReference("gaming_desktop", "Gaming Desktop", source, "bundled")
        ],
    )
    session = create_edit_session("gaming_desktop")

    assert session.source == "bundled"

    session.edit_props("title", {"text": "Edited locally"})
    result = session.save()

    assert result.path == output / "editable_canvas.yaml"
    assert result.changed is True
    assert load_canvas(result.path).components[0].props_dict()["text"] == "Edited locally"


def test_bundled_template_cannot_save_over_source_path(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "bundled" / "gaming_desktop.yaml"
    other_source = tmp_path / "bundled" / "media_desktop.yaml"
    save_canvas(_canvas(), source)
    save_canvas(
        CanvasDocument(
            id="media_canvas",
            name="Media Canvas",
            components=(
                CanvasComponent(
                    id="media",
                    type="text.label",
                    width=200,
                    height=64,
                    props={"text": "Media"},
                ),
            ),
        ),
        other_source,
    )
    monkeypatch.setattr(
        "ritualist.canvas.edit.list_canvases",
        lambda include_bundled=True: [
            CanvasReference("gaming_desktop", "Gaming Desktop", source, "bundled"),
            CanvasReference("media_desktop", "Media Desktop", other_source, "bundled"),
        ],
    )
    monkeypatch.setattr("ritualist.canvas.edit._bundled_canvas_paths", lambda: [source, other_source])
    session = create_edit_session("gaming_desktop")
    session.edit_props("title", {"text": "Edited locally"})

    try:
        session.save(destination=source)
    except RitualistError as exc:
        assert "bundled canvas templates" in str(exc)
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("bundled source overwrite should be rejected")

    assert load_canvas(source).components[0].props_dict()["text"] == "Hello"

    try:
        session.save(destination=other_source)
    except RitualistError as exc:
        assert "bundled canvas templates" in str(exc)
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("other bundled template overwrite should be rejected")

    assert load_canvas(other_source).components[0].props_dict()["text"] == "Media"


def test_bundled_overwrite_guard_survives_user_canvas_shadow(tmp_path: Path, monkeypatch) -> None:
    bundled = tmp_path / "bundled" / "same.yaml"
    user = tmp_path / "user" / "same.yaml"
    save_canvas(_canvas(), bundled)
    save_canvas(
        CanvasDocument(
            id="same",
            name="User Same",
            components=(
                CanvasComponent(
                    id="user_label",
                    type="text.label",
                    width=200,
                    height=64,
                    props={"text": "User"},
                ),
            ),
        ),
        user,
    )
    monkeypatch.setattr(
        "ritualist.canvas.edit.list_canvases",
        lambda include_bundled=True: [CanvasReference("same", "User Same", user, "user")],
    )
    monkeypatch.setattr("ritualist.canvas.edit._bundled_canvas_paths", lambda: [bundled])
    session = CanvasEditSession(document=_canvas(), source_path=bundled, source="bundled")
    session.edit_props("title", {"text": "Changed"})

    try:
        session.save(destination=bundled)
    except RitualistError as exc:
        assert "bundled canvas templates" in str(exc)
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("shadowed bundled template overwrite should be rejected")

    assert load_canvas(bundled).components[0].props_dict()["text"] == "Hello"


def test_invalid_canvas_cannot_save(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("ritualist.canvas.edit.canvases_dir", lambda: tmp_path)
    invalid = CanvasDocument(
        id="invalid_edit",
        name="Invalid Edit",
        components=(CanvasComponent(id="label", type="text.label", width=200, height=64),),
    )
    session = CanvasEditSession(document=invalid)

    try:
        session.save()
    except RitualistError as exc:
        assert "validation errors" in str(exc)
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("invalid canvas should not save")


def test_edit_model_operations_do_not_execute_runtime(monkeypatch) -> None:
    def fail_runtime(*_args, **_kwargs):
        raise AssertionError("edit model must not execute runtime")

    monkeypatch.setattr("ritualist.cli.WorkflowExecutor", fail_runtime)
    session = CanvasEditSession(document=_canvas())

    session.create_component("clock")
    session.edit_props("title", {"text": "Still local"})
    result = validate_canvas_structure(session.document)

    assert result.valid


def test_palette_exposes_property_editor_schema() -> None:
    session = CanvasEditSession(document=_canvas())

    entry = next(item for item in session.palette() if item.type_id == "text.label")
    palette_ids = {item.type_id for item in session.palette()}

    assert entry.category == "Display"
    assert [field.name for field in entry.property_schema] == ["text", "size", "color", "align"]
    assert entry.property_schema[0].label == "Text"
    assert entry.property_schema[0].required is True
    assert "app.launcher" not in palette_ids
    assert "window.layout_button" not in palette_ids


def test_canvas_edit_model_cli_json() -> None:
    result = CliRunner().invoke(app, ["canvas", "edit-model", "gaming_desktop", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["schema_version"] == "ritualist.canvas.edit_model.v1"
    assert data["source"] in {"bundled", "user"}
    assert data["dirty"] is False
    assert data["palette"]
    assert "recipe" in data["binding_kinds"]
