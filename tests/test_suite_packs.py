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
    MANIFEST_NAME as VISUAL_MANIFEST_NAME,
    THEME_NAME,
    THEME_PACK_SCHEMA,
    export_canvas_pack,
    export_theme_pack,
)
from setpiece.cli import app
from setpiece.packs import PACK_SCHEMA_V1, export_recipe_pack
from setpiece.paths import imported_packs_path, recipes_path
from setpiece.suite_packs import (
    MANIFEST_NAME,
    README_NAME,
    SUITE_PACK_SCHEMA,
    SuitePackError,
    export_suite_pack,
    import_suite_pack,
    list_suite_imports,
    validate_suite_pack,
)


def _use_app_data(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SETPIECE_E2E", "1")
    monkeypatch.setenv("SETPIECE_E2E_APP_DATA_DIR", str(tmp_path / "app-data"))


def _canvas_pack(tmp_path: Path) -> Path:
    document = CanvasDocument(
        id="project_suite_canvas",
        name="Project Suite Canvas",
        components=(
            CanvasComponent(
                id="title",
                type="text.label",
                width=320,
                height=72,
                props={"text": "Project Suite"},
            ),
        ),
    )
    canvas_path = tmp_path / "project_suite_canvas.yaml"
    canvas_path.write_text(yaml.safe_dump(document.to_dict(), sort_keys=False), encoding="utf-8")
    return export_canvas_pack(canvas_path, tmp_path / "project_suite_canvas.setpiececanvas").output_path


def _theme_pack(tmp_path: Path) -> Path:
    theme = CanvasTheme(id="project_suite_theme", name="Project Suite Theme")
    theme_path = tmp_path / "project_suite_theme.yaml"
    theme_path.write_text(yaml.safe_dump(theme.model_dump(mode="json"), sort_keys=False), encoding="utf-8")
    return export_theme_pack(theme_path, tmp_path / "project_suite_theme.setpiecetheme").output_path


def _ritual_pack(tmp_path: Path, *, recipe_id: str = "project_suite_wait") -> Path:
    recipe_path = tmp_path / f"{recipe_id}.yaml"
    recipe_path.write_text(
        f"""
version: "0.1"
id: {recipe_id}
name: Project Suite Wait
steps:
  - action: wait.seconds
    seconds: 0.1
""".lstrip(),
        encoding="utf-8",
    )
    return export_recipe_pack(recipe_path, tmp_path / f"{recipe_id}.setpiecepack").output_path


def _write_zip(path: Path, entries: dict[str, object]) -> Path:
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            if isinstance(content, bytes):
                archive.writestr(name, content)
            elif isinstance(content, str):
                archive.writestr(name, content)
            else:
                archive.writestr(name, yaml.safe_dump(content, sort_keys=False))
    return path


def _suite_manifest(
    *,
    canvas_entry: str = "packs/canvas/project_suite_canvas.setpiececanvas",
    theme_entry: str | None = None,
    ritual_entries: list[str] | None = None,
) -> dict[str, object]:
    rituals = ritual_entries or []
    contents: dict[str, object] = {
        "canvas": {"path": canvas_entry},
        "rituals": [
            {
                "path": entry,
                "behavior_bearing": True,
                "disabled_on_import": True,
            }
            for entry in rituals
        ],
    }
    if theme_entry is not None:
        contents["theme"] = {"path": theme_entry}
    return {
        "schema": SUITE_PACK_SCHEMA,
        "pack_type": "suite",
        "id": "project_suite",
        "name": "Project Suite",
        "version": "0.1.0",
        "contents": contents,
        "behavior_bearing_contents": rituals,
    }


def _bad_ritual_pack(tmp_path: Path) -> Path:
    path = tmp_path / "bad_shell.setpiecepack"
    return _write_zip(
        path,
        {
            "manifest.yaml": {
                "schema": PACK_SCHEMA_V1,
                "id": "bad_shell",
                "name": "Bad Shell",
                "version": "1.0.0",
                "required_setpiece_version": ">=0",
                "supported_os": ["windows", "linux", "macos"],
                "required_capabilities": [],
                "required_actions": ["shell.run"],
                "variables": {},
                "safety": {
                    "no_arbitrary_code": True,
                    "no_coordinate_clicks": True,
                    "no_remote_execution": True,
                    "imported_recipes_must_not_run_automatically": True,
                },
            },
            "recipe.yaml": {
                "version": "0.1",
                "id": "bad_shell",
                "name": "Bad Shell",
                "steps": [{"action": "shell.run", "command": "echo unsafe"}],
            },
        },
    )


def _bad_canvas_pack(tmp_path: Path) -> Path:
    path = tmp_path / "bad_canvas.setpiececanvas"
    document = CanvasDocument(
        id="project_suite_canvas",
        name="Project Suite Canvas",
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
    return _write_zip(
        path,
        {
            VISUAL_MANIFEST_NAME: {
                "schema": CANVAS_PACK_SCHEMA,
                "pack_type": "canvas",
                "id": "project_suite_canvas",
                "name": "Project Suite Canvas",
                "version": "0.1",
                "canvas_id": "project_suite_canvas",
                "assets": [],
            },
            CANVAS_NAME: document.to_dict(),
        },
    )


def _bad_theme_pack(tmp_path: Path) -> Path:
    path = tmp_path / "bad_theme.setpiecetheme"
    return _write_zip(
        path,
        {
            VISUAL_MANIFEST_NAME: {
                "schema": THEME_PACK_SCHEMA,
                "pack_type": "theme",
                "id": "project_suite_theme",
                "name": "Project Suite Theme",
                "version": "0.1",
                "theme_id": "project_suite_theme",
                "assets": [],
            },
            THEME_NAME: {
                "id": "project_suite_theme",
                "name": "Project Suite Theme",
                "components": [],
            },
        },
    )


def test_suite_pack_export_validate_and_import_quarantines_everything(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_app_data(monkeypatch, tmp_path)
    canvas = _canvas_pack(tmp_path)
    theme = _theme_pack(tmp_path)
    ritual = _ritual_pack(tmp_path)
    readme = tmp_path / "README.md"
    readme.write_text("# Project Suite\n", encoding="utf-8")

    exported = export_suite_pack(
        canvas_pack=canvas,
        theme_pack=theme,
        ritual_packs=(ritual,),
        out=tmp_path / "project_suite.setpiecesuite",
        suite_id="project_suite",
        name="Project Suite",
        readme_path=readme,
    )
    validated = validate_suite_pack(exported.output_path)
    imported = import_suite_pack(exported.output_path)

    assert exported.suite_id == "project_suite"
    assert set(exported.entries) == {
        MANIFEST_NAME,
        README_NAME,
        "packs/canvas/project_suite_canvas.setpiececanvas",
        "packs/theme/project_suite_theme.setpiecetheme",
        "packs/rituals/project_suite_wait.setpiecepack",
    }
    assert [item.pack_type for item in validated.nested_packs] == ["canvas", "theme", "ritual"]
    assert validated.manifest.behavior_bearing_contents == [
        "packs/rituals/project_suite_wait.setpiecepack"
    ]
    assert imported.status == "quarantined"
    assert imported.canvas_import["status"] == "quarantined"
    assert imported.theme_import and imported.theme_import["status"] == "quarantined"
    assert imported.ritual_imports[0]["status"] == "disabled"
    assert imported.to_dict()["auto_run"] is False
    assert imported.to_dict()["auto_enable"] is False
    assert not (recipes_path() / "project_suite_wait.yaml").exists()
    assert list_suite_imports()[0].import_id == "project_suite"


def test_suite_pack_visuals_only_import_skips_behavior_packs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_app_data(monkeypatch, tmp_path)
    suite = export_suite_pack(
        canvas_pack=_canvas_pack(tmp_path),
        ritual_packs=(_ritual_pack(tmp_path),),
        out=tmp_path / "visuals_only.setpiecesuite",
        suite_id="visuals_only_suite",
        name="Visuals Only Suite",
    ).output_path

    imported = import_suite_pack(suite, include_rituals=False)

    assert imported.ritual_imports == ()
    assert imported.skipped_rituals == (
        {
            "entry": "packs/rituals/project_suite_wait.setpiecepack",
            "reason": "visuals_only_import",
            "behavior_bearing": True,
        },
    )
    assert not imported_packs_path().exists()


def test_suite_pack_rejects_undisclosed_behavior_bearing_ritual(tmp_path: Path) -> None:
    canvas = _canvas_pack(tmp_path)
    ritual = _ritual_pack(tmp_path)
    suite = tmp_path / "missing_disclosure.setpiecesuite"
    manifest = _suite_manifest(ritual_entries=[])
    manifest["contents"]["rituals"] = [
        {
            "path": "packs/rituals/project_suite_wait.setpiecepack",
            "behavior_bearing": True,
            "disabled_on_import": True,
        }
    ]

    _write_zip(
        suite,
        {
            MANIFEST_NAME: manifest,
            "packs/canvas/project_suite_canvas.setpiececanvas": canvas.read_bytes(),
            "packs/rituals/project_suite_wait.setpiecepack": ritual.read_bytes(),
        },
    )

    with pytest.raises(SuitePackError, match="disclose every behavior-bearing ritual"):
        validate_suite_pack(suite)


def test_suite_pack_rejects_unsafe_nested_ritual_canvas_and_theme(tmp_path: Path) -> None:
    canvas = _canvas_pack(tmp_path)

    bad_ritual_suite = tmp_path / "bad_ritual.setpiecesuite"
    _write_zip(
        bad_ritual_suite,
        {
            MANIFEST_NAME: _suite_manifest(
                ritual_entries=["packs/rituals/bad_shell.setpiecepack"]
            ),
            "packs/canvas/project_suite_canvas.setpiececanvas": canvas.read_bytes(),
            "packs/rituals/bad_shell.setpiecepack": _bad_ritual_pack(tmp_path).read_bytes(),
        },
    )
    with pytest.raises(SuitePackError, match="arbitrary code actions"):
        validate_suite_pack(bad_ritual_suite)

    bad_canvas_suite = tmp_path / "bad_canvas.setpiecesuite"
    _write_zip(
        bad_canvas_suite,
        {
            MANIFEST_NAME: _suite_manifest(),
            "packs/canvas/project_suite_canvas.setpiececanvas": _bad_canvas_pack(tmp_path).read_bytes(),
        },
    )
    with pytest.raises(SuitePackError, match="blocked in imported canvases"):
        validate_suite_pack(bad_canvas_suite)

    bad_theme_suite = tmp_path / "bad_theme.setpiecesuite"
    _write_zip(
        bad_theme_suite,
        {
            MANIFEST_NAME: _suite_manifest(
                theme_entry="packs/theme/bad_theme.setpiecetheme"
            ),
            "packs/canvas/project_suite_canvas.setpiececanvas": canvas.read_bytes(),
            "packs/theme/bad_theme.setpiecetheme": _bad_theme_pack(tmp_path).read_bytes(),
        },
    )
    with pytest.raises(SuitePackError, match="invalid nested theme pack"):
        validate_suite_pack(bad_theme_suite)


def test_suite_pack_rejects_unexpected_nested_assets_and_path_traversal(tmp_path: Path) -> None:
    canvas = _canvas_pack(tmp_path)
    suite = tmp_path / "unexpected.setpiecesuite"

    _write_zip(
        suite,
        {
            MANIFEST_NAME: _suite_manifest(),
            "packs/canvas/project_suite_canvas.setpiececanvas": canvas.read_bytes(),
            "assets/payload.exe": b"MZ",
        },
    )
    with pytest.raises(SuitePackError, match="unexpected suite pack entry"):
        validate_suite_pack(suite)

    traversal = tmp_path / "traversal.setpiecesuite"
    with ZipFile(traversal, "w", ZIP_DEFLATED) as archive:
        archive.writestr(MANIFEST_NAME, yaml.safe_dump(_suite_manifest()))
        archive.writestr("packs/canvas/../escape.setpiececanvas", b"unsafe")
    with pytest.raises(SuitePackError, match="unsafe suite pack entry path"):
        validate_suite_pack(traversal)


def test_suite_pack_cli_validate_import_and_list_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_app_data(monkeypatch, tmp_path)
    suite = export_suite_pack(
        canvas_pack=_canvas_pack(tmp_path),
        out=tmp_path / "cli_suite.setpiecesuite",
        suite_id="cli_suite",
        name="CLI Suite",
    ).output_path
    runner = CliRunner()

    validate_result = runner.invoke(app, ["suite", "validate", str(suite), "--json"])
    import_result = runner.invoke(app, ["suite", "import", str(suite), "--json"])
    list_result = runner.invoke(app, ["suite", "list-imports", "--json"])

    assert validate_result.exit_code == 0, validate_result.output
    assert json.loads(validate_result.output)["validation"]["auto_run"] is False
    assert import_result.exit_code == 0, import_result.output
    imported = json.loads(import_result.output)
    assert imported["status"] == "quarantined"
    assert imported["auto_enable"] is False
    assert list_result.exit_code == 0, list_result.output
    assert json.loads(list_result.output)[0]["suite_id"] == "cli_suite"
