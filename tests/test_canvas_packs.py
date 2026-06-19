from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
import yaml
from typer.testing import CliRunner

from setpiece.canvas.models import CanvasComponent, CanvasDocument, CanvasTheme
from setpiece.canvas_packs import (
    CANVAS_NAME,
    CANVAS_PACK_SCHEMA,
    MANIFEST_NAME,
    THEME_NAME,
    THEME_PACK_SCHEMA,
    VisualPackError,
    export_canvas_pack,
    export_theme_pack,
    import_canvas_pack,
    import_theme_pack,
)
from setpiece.cli import app


def _visual_canvas(tmp_path: Path) -> Path:
    assets = tmp_path / "assets"
    assets.mkdir()
    image = assets / "hero.png"
    image.write_bytes(b"not really a png")
    document = CanvasDocument(
        id="visual_canvas",
        name="Visual Canvas",
        components=(
            CanvasComponent(
                id="title",
                type="text.label",
                width=320,
                height=80,
                props={"text": "Visual only"},
            ),
            CanvasComponent(
                id="image",
                type="image",
                width=320,
                height=180,
                props={"path": "assets/hero.png"},
            ),
        ),
    )
    path = tmp_path / "visual_canvas.yaml"
    path.write_text(yaml.safe_dump(document.to_dict(), sort_keys=False), encoding="utf-8")
    return path


def _theme_path(tmp_path: Path) -> Path:
    theme = CanvasTheme(id="minimal_theme", name="Minimal Theme")
    path = tmp_path / "minimal_theme.yaml"
    path.write_text(yaml.safe_dump(theme.model_dump(mode="json"), sort_keys=False), encoding="utf-8")
    return path


def _write_pack(path: Path, entries: dict[str, object]) -> None:
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            if isinstance(content, bytes):
                archive.writestr(name, content)
            else:
                archive.writestr(name, yaml.safe_dump(content, sort_keys=False))


def _canvas_manifest(*, canvas_id: str = "visual_canvas", assets: list[str] | None = None) -> dict[str, object]:
    return {
        "schema": CANVAS_PACK_SCHEMA,
        "pack_type": "canvas",
        "id": "visual_canvas",
        "name": "Visual Canvas",
        "version": "0.1",
        "canvas_id": canvas_id,
        "assets": assets or [],
    }


def _theme_manifest(*, theme_id: str = "minimal_theme", assets: list[str] | None = None) -> dict[str, object]:
    return {
        "schema": THEME_PACK_SCHEMA,
        "pack_type": "theme",
        "id": "minimal_theme",
        "name": "Minimal Theme",
        "version": "0.1",
        "theme_id": theme_id,
        "assets": assets or [],
    }


def test_export_import_canvas_pack_quarantines_visual_canvas(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("setpiece.canvas_packs.imported_canvas_packs_dir", lambda: tmp_path / "imports")
    canvas = _visual_canvas(tmp_path)
    out = tmp_path / "visual_canvas.setpiececanvas"

    export_result = export_canvas_pack(canvas, out)
    import_record = import_canvas_pack(export_result.output_path)

    assert export_result.pack_type == "canvas"
    assert CANVAS_NAME in export_result.entries
    assert "assets/hero_" in "\n".join(export_result.entries)
    assert import_record.status == "quarantined"
    assert import_record.document_path == CANVAS_NAME
    imported_yaml = import_record.root / CANVAS_NAME
    assert imported_yaml.exists()
    assert "steps:" not in imported_yaml.read_text(encoding="utf-8")


def test_export_import_theme_pack_is_visual_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("setpiece.canvas_packs.imported_theme_packs_dir", lambda: tmp_path / "themes")
    theme = _theme_path(tmp_path)
    out = tmp_path / "minimal_theme.setpiecetheme"

    export_result = export_theme_pack(theme, out)
    import_record = import_theme_pack(export_result.output_path)

    assert export_result.pack_type == "theme"
    assert import_record.status == "quarantined"
    theme_text = (import_record.root / THEME_NAME).read_text(encoding="utf-8")
    assert "steps:" not in theme_text
    assert "components:" not in theme_text


def test_canvas_pack_rejects_arbitrary_component_code(tmp_path: Path) -> None:
    document = CanvasDocument(
        id="visual_canvas",
        name="Visual Canvas",
        components=(
            CanvasComponent(
                id="bad",
                type="text.label",
                width=220,
                height=80,
                props={"text": "<script>alert(1)</script>"},
            ),
        ),
    )
    pack = tmp_path / "bad.setpiececanvas"
    _write_pack(pack, {MANIFEST_NAME: _canvas_manifest(), CANVAS_NAME: document.to_dict()})

    with pytest.raises(VisualPackError, match="script-like component content"):
        import_canvas_pack(pack)


def test_imported_canvas_pack_rejects_triggering_components(tmp_path: Path) -> None:
    document = CanvasDocument(
        id="visual_canvas",
        name="Visual Canvas",
        components=(
            CanvasComponent(
                id="runner",
                type="ritual.card",
                width=320,
                height=180,
                props={"title": "Run", "recipe_id": "gaming_mode"},
            ),
        ),
    )
    pack = tmp_path / "runner.setpiececanvas"
    _write_pack(pack, {MANIFEST_NAME: _canvas_manifest(), CANVAS_NAME: document.to_dict()})

    with pytest.raises(VisualPackError, match="blocked in imported canvases"):
        import_canvas_pack(pack)


def test_canvas_pack_rejects_undeclared_and_executable_assets(tmp_path: Path) -> None:
    document = CanvasDocument(id="visual_canvas", name="Visual Canvas")
    undeclared = tmp_path / "undeclared.setpiececanvas"
    _write_pack(
        undeclared,
        {
            MANIFEST_NAME: _canvas_manifest(),
            CANVAS_NAME: document.to_dict(),
            "assets/hero.png": b"png",
        },
    )
    with pytest.raises(VisualPackError, match="undeclared assets"):
        import_canvas_pack(undeclared)

    executable = tmp_path / "executable.setpiececanvas"
    _write_pack(
        executable,
        {
            MANIFEST_NAME: _canvas_manifest(assets=["assets/run.exe"]),
            CANVAS_NAME: document.to_dict(),
            "assets/run.exe": b"MZ",
        },
    )
    with pytest.raises(VisualPackError, match="raster image files"):
        import_canvas_pack(executable)


def test_canvas_pack_rejects_non_raster_and_script_like_assets(tmp_path: Path) -> None:
    document = CanvasDocument(
        id="visual_canvas",
        name="Visual Canvas",
        components=(
            CanvasComponent(
                id="image",
                type="image",
                width=220,
                height=120,
                props={"path": "assets/payload.png"},
            ),
        ),
    )

    html_pack = tmp_path / "html.setpiececanvas"
    _write_pack(
        html_pack,
        {
            MANIFEST_NAME: _canvas_manifest(assets=["assets/payload.html"]),
            CANVAS_NAME: document.to_dict(),
            "assets/payload.html": b"<html></html>",
        },
    )
    with pytest.raises(VisualPackError, match="raster image files"):
        import_canvas_pack(html_pack)

    svg_pack = tmp_path / "svg.setpiececanvas"
    _write_pack(
        svg_pack,
        {
            MANIFEST_NAME: _canvas_manifest(assets=["assets/payload.svg"]),
            CANVAS_NAME: document.to_dict(),
            "assets/payload.svg": b"<svg><script /></svg>",
        },
    )
    with pytest.raises(VisualPackError, match="raster image files"):
        import_canvas_pack(svg_pack)

    disguised = tmp_path / "disguised.setpiececanvas"
    _write_pack(
        disguised,
        {
            MANIFEST_NAME: _canvas_manifest(assets=["assets/payload.png"]),
            CANVAS_NAME: document.to_dict(),
            "assets/payload.png": b"<script>alert(1)</script>",
        },
    )
    with pytest.raises(VisualPackError, match="script-like"):
        import_canvas_pack(disguised)


def test_canvas_pack_requires_exact_referenced_assets(tmp_path: Path) -> None:
    document = CanvasDocument(
        id="visual_canvas",
        name="Visual Canvas",
        components=(
            CanvasComponent(
                id="image",
                type="image",
                width=220,
                height=120,
                props={"path": "assets/missing.png"},
            ),
        ),
    )

    missing = tmp_path / "missing.setpiececanvas"
    _write_pack(missing, {MANIFEST_NAME: _canvas_manifest(), CANVAS_NAME: document.to_dict()})
    with pytest.raises(VisualPackError, match="references missing assets"):
        import_canvas_pack(missing)

    unused = tmp_path / "unused.setpiececanvas"
    _write_pack(
        unused,
        {
            MANIFEST_NAME: _canvas_manifest(assets=["assets/unused.png"]),
            CANVAS_NAME: CanvasDocument(id="visual_canvas", name="Visual Canvas").to_dict(),
            "assets/unused.png": b"png",
        },
    )
    with pytest.raises(VisualPackError, match="declares unused assets"):
        import_canvas_pack(unused)


def test_canvas_pack_export_rejects_missing_local_asset_reference(tmp_path: Path) -> None:
    path = tmp_path / "missing_export.yaml"
    document = CanvasDocument(
        id="visual_canvas",
        name="Visual Canvas",
        components=(
            CanvasComponent(
                id="image",
                type="image",
                width=220,
                height=120,
                props={"path": "assets/missing.png"},
            ),
        ),
    )
    path.write_text(yaml.safe_dump(document.to_dict(), sort_keys=False), encoding="utf-8")

    with pytest.raises(VisualPackError, match="references missing assets"):
        export_canvas_pack(path, tmp_path / "missing_export.setpiececanvas")


def test_visual_packs_reject_cross_domain_documents(tmp_path: Path) -> None:
    canvas_pack = tmp_path / "with_theme.setpiececanvas"
    _write_pack(
        canvas_pack,
        {
            MANIFEST_NAME: _canvas_manifest(),
            CANVAS_NAME: CanvasDocument(id="visual_canvas", name="Visual Canvas").to_dict(),
            THEME_NAME: CanvasTheme(id="minimal_theme", name="Minimal Theme").model_dump(mode="json"),
        },
    )
    with pytest.raises(VisualPackError, match="unexpected visual pack entry"):
        import_canvas_pack(canvas_pack)

    theme_pack = tmp_path / "with_canvas.setpiecetheme"
    _write_pack(
        theme_pack,
        {
            MANIFEST_NAME: _theme_manifest(),
            THEME_NAME: CanvasTheme(id="minimal_theme", name="Minimal Theme").model_dump(mode="json"),
            CANVAS_NAME: CanvasDocument(id="visual_canvas", name="Visual Canvas").to_dict(),
        },
    )
    with pytest.raises(VisualPackError, match="unexpected visual pack entry"):
        import_theme_pack(theme_pack)


def test_visual_packs_reject_duplicate_asset_entries(tmp_path: Path) -> None:
    document = CanvasDocument(
        id="visual_canvas",
        name="Visual Canvas",
        components=(
            CanvasComponent(
                id="image",
                type="image",
                width=220,
                height=120,
                props={"path": "assets/a.png"},
            ),
        ),
    )
    pack = tmp_path / "duplicate.setpiececanvas"
    with ZipFile(pack, "w", ZIP_DEFLATED) as archive:
        archive.writestr(MANIFEST_NAME, yaml.safe_dump(_canvas_manifest(assets=["assets/a.png"])))
        archive.writestr(CANVAS_NAME, yaml.safe_dump(document.to_dict()))
        archive.writestr("assets/a.png", b"<script>alert(1)</script>")
        with pytest.warns(UserWarning, match="Duplicate name"):
            archive.writestr("assets/a.png", b"png")

    with pytest.raises(VisualPackError, match="duplicate visual pack entry"):
        import_canvas_pack(pack)


def test_visual_pack_manifest_rejects_case_colliding_assets(tmp_path: Path) -> None:
    document = CanvasDocument(
        id="visual_canvas",
        name="Visual Canvas",
        components=(
            CanvasComponent(
                id="image",
                type="image",
                width=220,
                height=120,
                props={"path": "assets/a.png"},
            ),
        ),
    )
    pack = tmp_path / "case_collision.setpiececanvas"
    _write_pack(
        pack,
        {
            MANIFEST_NAME: _canvas_manifest(assets=["assets/a.png", "assets/A.PNG"]),
            CANVAS_NAME: document.to_dict(),
            "assets/a.png": b"png",
        },
    )

    with pytest.raises(VisualPackError, match="duplicate visual pack assets"):
        import_canvas_pack(pack)


def test_theme_pack_rejects_assets_until_theme_asset_refs_exist(tmp_path: Path) -> None:
    pack = tmp_path / "theme_asset.setpiecetheme"
    _write_pack(
        pack,
        {
            MANIFEST_NAME: _theme_manifest(assets=["assets/theme.png"]),
            THEME_NAME: CanvasTheme(id="minimal_theme", name="Minimal Theme").model_dump(mode="json"),
            "assets/theme.png": b"png",
        },
    )

    with pytest.raises(VisualPackError, match="declares unused assets"):
        import_theme_pack(pack)


def test_theme_pack_rejects_recipes_actions_and_components(tmp_path: Path) -> None:
    pack = tmp_path / "bad_theme.setpiecetheme"
    _write_pack(
        pack,
        {
            MANIFEST_NAME: _theme_manifest(),
            THEME_NAME: {
                "id": "minimal_theme",
                "name": "Minimal Theme",
                "components": [],
            },
        },
    )

    with pytest.raises(VisualPackError, match="invalid theme.yaml"):
        import_theme_pack(pack)


def test_canvas_pack_cli_export_import_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("setpiece.canvas_packs.imported_canvas_packs_dir", lambda: tmp_path / "imports")
    canvas = _visual_canvas(tmp_path)
    out = tmp_path / "cli_canvas.setpiececanvas"
    runner = CliRunner()

    export_result = runner.invoke(app, ["canvas", "pack", "export", str(canvas), "--out", str(out), "--json"])
    import_result = runner.invoke(app, ["canvas", "pack", "import", str(out), "--json"])

    assert export_result.exit_code == 0, export_result.output
    assert import_result.exit_code == 0, import_result.output
    assert json.loads(export_result.output)["pack_type"] == "canvas"
    assert json.loads(import_result.output)["status"] == "quarantined"
