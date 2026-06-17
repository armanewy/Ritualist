from __future__ import annotations

from pathlib import Path

from ritualist.canvas import (
    CanvasBindingKind,
    CanvasComponent,
    CanvasDocument,
    CanvasEditSession,
    CanvasEditUiBridge,
    load_canvas,
)
from ritualist.errors import RitualistError


def _canvas() -> CanvasDocument:
    return CanvasDocument(
        id="edit_ui_canvas",
        name="Edit UI Canvas",
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


def test_edit_ui_bridge_selects_moves_resizes_and_saves(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("ritualist.canvas.edit.canvases_dir", lambda: tmp_path)
    bridge = CanvasEditUiBridge(CanvasEditSession(document=_canvas()))

    bridge.select("title")
    bridge.move_component("title", 31, 47)
    bridge.resize_component("title", 217, 79)
    bridge.edit_property("title", "text", "Updated")
    result = bridge.save()

    assert result.path == tmp_path / "edit_ui_canvas.yaml"
    saved = load_canvas(result.path)
    component = saved.components[0]
    assert component.x == 32
    assert component.y == 48
    assert component.width == 224
    assert component.height == 80
    assert component.props_dict()["text"] == "Updated"


def test_edit_ui_bridge_exposes_selected_property_and_binding_model() -> None:
    bridge = CanvasEditUiBridge(CanvasEditSession(document=_canvas()))

    model = bridge.select("title")
    palette = {entry["type_id"] for entry in model["palette"]}

    assert model["schema_version"] == "ritualist.canvas.edit_ui.v1"
    assert model["selected_component"]["id"] == "title"
    assert {
        "ritual.card",
        "target.card",
        "text.label",
        "image",
        "clock",
        "recent.activity",
        "doctor.badge",
    } <= palette
    assert "app.launcher" not in palette
    assert "window.layout_button" not in palette
    assert [field["name"] for field in model["selected_component"]["property_schema"]] == [
        "text",
        "size",
        "color",
        "align",
    ]
    assert model["selected_component"]["supported_bindings"] == [CanvasBindingKind.STATIC.value]


def test_edit_ui_bridge_rejects_unsafe_or_unsupported_edits() -> None:
    bridge = CanvasEditUiBridge(CanvasEditSession(document=_canvas()))

    for operation, expected in (
        (lambda: bridge.create_component("app.launcher"), "not available in Canvas Edit Mode UI"),
        (lambda: bridge.edit_property("title", "foo", "hidden"), "unknown prop 'foo'"),
        (lambda: bridge.edit_property("title", "size", "big"), "prop 'size' has invalid value"),
        (lambda: bridge.edit_binding("title", "recipe", "gaming_mode"), "does not support recipe bindings"),
        (lambda: bridge.edit_binding("title", "adapter.raw", "x"), "not editable"),
    ):
        try:
            operation()
        except RitualistError as exc:
            assert expected in str(exc)
        else:  # pragma: no cover - assertion clarity
            raise AssertionError("unsafe edit should fail")


def test_canvas_use_qml_contains_edit_mode_controls() -> None:
    qml = Path("ritualist/canvas/qml/CanvasUse.qml").read_text(encoding="utf-8")

    assert "setEditMode" in qml
    assert "Switch to Use Mode before running Canvas actions" in qml or "root.editMode" in qml
    assert "Apply Binding" in qml
    assert "saveCanvas" in qml
    assert "dispatch(componentId, actionId)" in qml


def test_canvas_use_qml_contains_low_spec_performance_controls() -> None:
    qml = Path("ritualist/canvas/qml/CanvasUse.qml").read_text(encoding="utf-8")

    assert "ritualistCanvasPerformance" in qml
    assert "showPerformanceOverlay" in qml
    assert "Canvas performance" in qml
    assert "Behavior on opacity" in qml
    assert "FastBlur" not in qml
    assert "ShaderEffect" not in qml
