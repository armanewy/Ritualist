from __future__ import annotations

from pathlib import Path

import pytest

from setpiece.canvas import (
    CanvasDocument,
    CanvasEditSession,
    CanvasEditUiBridge,
    build_canvas_runtime_model,
    load_canvas,
    validate_canvas_structure,
)
from setpiece.errors import SetpieceError
from setpiece.shortcuts import ShortcutService


def _empty_room() -> CanvasDocument:
    return CanvasDocument(id="builder_shortcuts", name="Builder Shortcuts")


def _component_by_type(session: CanvasEditSession, type_id: str):
    return next(component for component in session.document.components if component.type == type_id)


def test_room_builder_palette_exposes_typed_shortcuts() -> None:
    bridge = CanvasEditUiBridge(CanvasEditSession(document=_empty_room()))
    model = bridge.model()
    palette = {entry["type_id"]: entry for entry in model["palette"]}

    assert {"shortcut.folder", "shortcut.app", "shortcut.url"} <= set(palette)
    assert palette["shortcut.folder"]["category"] == "Shortcuts"
    assert palette["shortcut.app"]["category"] == "Shortcuts"
    assert palette["shortcut.url"]["category"] == "Shortcuts"
    assert "app.launcher" not in palette


def test_room_builder_adds_edits_saves_and_reopens_shortcuts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("setpiece.canvas.edit.canvases_dir", lambda: tmp_path)
    folder = tmp_path / "project"
    folder.mkdir()
    app = tmp_path / "editor.exe"
    app.write_text("fake executable placeholder", encoding="utf-8")
    bridge = CanvasEditUiBridge(CanvasEditSession(document=_empty_room()))

    folder_model = bridge.create_component("shortcut.folder")
    folder_component = _component_by_type(bridge.session, "shortcut.folder")
    assert any("shortcut target is not configured" in item for item in folder_model["validation"]["warnings"])

    bridge.edit_property(folder_component.id, "title", "Project Folder")
    bridge.edit_property(folder_component.id, "path", str(folder))
    app_model = bridge.create_component("shortcut.app")
    app_component = _component_by_type(bridge.session, "shortcut.app")
    assert any("shortcut target is not configured" in item for item in app_model["validation"]["warnings"])

    bridge.edit_property(app_component.id, "title", "Editor")
    bridge.edit_property(app_component.id, "path", str(app))
    bridge.create_component("shortcut.url")
    url_component = _component_by_type(bridge.session, "shortcut.url")
    bridge.edit_property(url_component.id, "title", "Docs")
    final_model = bridge.edit_property(url_component.id, "url", "https://example.com/docs")

    assert final_model["validation"]["valid"] is True
    assert final_model["validation"]["warnings"] == []

    result = bridge.save()
    reopened = load_canvas(result.path)
    components = {component.type: component for component in reopened.components}

    assert result.path == tmp_path / "builder_shortcuts.yaml"
    assert components["shortcut.folder"].props_dict()["path"] == str(folder)
    assert components["shortcut.app"].props_dict()["path"] == str(app)
    assert components["shortcut.url"].props_dict()["url"] == "https://example.com/docs"
    assert validate_canvas_structure(reopened).valid is True


def test_room_builder_shortcut_undo_redo_preserves_typed_properties(tmp_path: Path) -> None:
    app = tmp_path / "editor.exe"
    app.write_text("fake executable placeholder", encoding="utf-8")
    bridge = CanvasEditUiBridge(CanvasEditSession(document=_empty_room()))

    bridge.create_component("shortcut.app")
    app_component = _component_by_type(bridge.session, "shortcut.app")
    bridge.edit_property(app_component.id, "path", str(app))

    bridge.undo()
    assert "path" not in _component_by_type(bridge.session, "shortcut.app").props_dict()

    bridge.redo()
    assert _component_by_type(bridge.session, "shortcut.app").props_dict()["path"] == str(app)


def test_room_builder_rejects_arbitrary_shortcut_commands_and_scripts(tmp_path: Path) -> None:
    script = tmp_path / "setup.ps1"
    script.write_text("Write-Host unsafe", encoding="utf-8")
    bridge = CanvasEditUiBridge(CanvasEditSession(document=_empty_room()))

    bridge.create_component("shortcut.app")
    app_component = _component_by_type(bridge.session, "shortcut.app")
    with pytest.raises(SetpieceError, match="not a shell command"):
        bridge.edit_property(app_component.id, "path", "cmd /c calc.exe")
    with pytest.raises(SetpieceError, match="must not be a script"):
        bridge.edit_property(app_component.id, "path", str(script))
    with pytest.raises(SetpieceError, match="unknown prop 'command_line'"):
        bridge.edit_property(app_component.id, "command_line", "python unsafe.py")

    bridge.create_component("shortcut.folder")
    folder_component = _component_by_type(bridge.session, "shortcut.folder")
    with pytest.raises(SetpieceError, match="not an executable or script"):
        bridge.edit_property(folder_component.id, "path", str(script))

    bridge.create_component("shortcut.url")
    url_component = _component_by_type(bridge.session, "shortcut.url")
    with pytest.raises(SetpieceError, match="http or https"):
        bridge.edit_property(url_component.id, "url", "javascript:alert(1)")


def test_room_builder_never_executes_shortcuts_in_edit_mode(tmp_path: Path, monkeypatch) -> None:
    def fail_open(self: ShortcutService, request: object) -> object:  # pragma: no cover - should never be called.
        raise AssertionError(f"Edit Mode must not execute shortcut {request!r}")

    monkeypatch.setattr(ShortcutService, "open", fail_open)
    folder = tmp_path / "project"
    folder.mkdir()
    app = tmp_path / "editor.exe"
    app.write_text("fake executable placeholder", encoding="utf-8")
    bridge = CanvasEditUiBridge(CanvasEditSession(document=_empty_room()))

    bridge.create_component("shortcut.folder")
    folder_component = _component_by_type(bridge.session, "shortcut.folder")
    bridge.edit_property(folder_component.id, "path", str(folder))
    bridge.create_component("shortcut.app")
    app_component = _component_by_type(bridge.session, "shortcut.app")
    bridge.edit_property(app_component.id, "path", str(app))
    bridge.create_component("shortcut.url")
    url_component = _component_by_type(bridge.session, "shortcut.url")
    bridge.edit_property(url_component.id, "url", "https://example.com/docs")
    bridge.undo()
    bridge.redo()

    model = build_canvas_runtime_model(bridge.session.document)

    assert {state.state for state in model.component_states} == {"ready"}
