from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable
from zipfile import ZIP_DEFLATED, ZipFile

import yaml

from setpiece.canvas.models import CanvasComponent, CanvasDocument, CanvasTheme
from setpiece.brand_assets import (
    TRAY_STATES,
    TRAY_VARIANTS,
    brand_asset_path,
    load_design_tokens,
    tray_icon_asset,
)
from setpiece.canvas_packs import (
    export_canvas_pack,
    export_theme_pack,
    import_canvas_pack,
    import_theme_pack,
)
from setpiece.packs import export_recipe_pack, import_pack, validate_pack
from setpiece.paths import migrate_legacy_data
from setpiece.suite_packs import export_suite_pack, import_suite_pack, validate_suite_pack

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_setpiece_brand_assets_resolve_for_runtime_states() -> None:
    tokens = load_design_tokens()

    assert tokens["name"] == "Setpiece"
    assert tokens["colors"]["ink"] == "#22272B"
    assert tokens["colors"]["paper"] == "#F7F4EE"
    with brand_asset_path("app/setpiece_app_icon.ico") as app_icon:
        assert app_icon.is_file()
    for variant in sorted(TRAY_VARIANTS):
        for state in sorted(TRAY_STATES):
            asset = tray_icon_asset(state, variant=variant)
            with brand_asset_path(asset.relative_path) as path:
                assert path.is_file(), asset


def test_legacy_data_migration_copies_missing_without_overwrite(tmp_path: Path) -> None:
    legacy_data = tmp_path / "Ritualist"
    setpiece_data = tmp_path / "Setpiece"
    legacy_logs = tmp_path / "RitualistLogs"
    setpiece_logs = tmp_path / "SetpieceLogs"
    (legacy_data / "runs" / "old").mkdir(parents=True)
    (legacy_data / "runs" / "old" / "run.json").write_text('{"status":"running"}', encoding="utf-8")
    (legacy_data / "config").mkdir()
    (legacy_data / "config" / "config.yaml").write_text("legacy: true\n", encoding="utf-8")
    (setpiece_data / "config").mkdir(parents=True)
    (setpiece_data / "config" / "config.yaml").write_text("setpiece: true\n", encoding="utf-8")
    legacy_logs.mkdir()
    (legacy_logs / "ritualist.log").write_text("legacy log\n", encoding="utf-8")

    dry_run = migrate_legacy_data(
        dry_run=True,
        legacy_data_root=legacy_data,
        setpiece_data_root=setpiece_data,
        legacy_log_root=legacy_logs,
        setpiece_log_root=setpiece_logs,
    )
    assert dry_run["status"] == "would_migrate"
    assert not (setpiece_data / "runs" / "old" / "run.json").exists()

    report = migrate_legacy_data(
        legacy_data_root=legacy_data,
        setpiece_data_root=setpiece_data,
        legacy_log_root=legacy_logs,
        setpiece_log_root=setpiece_logs,
    )
    assert report["status"] == "migrated"
    assert (setpiece_data / "runs" / "old" / "run.json").read_text(encoding="utf-8")
    assert (setpiece_logs / "ritualist.log").read_text(encoding="utf-8") == "legacy log\n"
    assert (setpiece_data / "config" / "config.yaml").read_text(encoding="utf-8") == "setpiece: true\n"
    marker = json.loads((setpiece_data / ".setpiece-legacy-migration.json").read_text(encoding="utf-8"))
    assert marker["schema_version"] == "setpiece.legacy_data_migration.v1"


def test_legacy_data_migration_cli_json_dry_run(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SETPIECE_E2E", "1")
    monkeypatch.setenv("SETPIECE_E2E_APP_DATA_DIR", str(tmp_path / "appdata"))
    result = subprocess.run(
        [sys.executable, "-m", "setpiece", "migrate-legacy-data", "--dry-run", "--json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "setpiece.legacy_data_migration.v1"
    assert payload["dry_run"] is True


def test_legacy_recipe_pack_extension_imports_but_new_export_is_canonical(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("SETPIECE_E2E", "1")
    monkeypatch.setenv("SETPIECE_E2E_APP_DATA_DIR", str(tmp_path / "appdata"))
    recipe = REPO_ROOT / "setpiece" / "sample_recipes" / "gaming_mode.yaml"
    exported = export_recipe_pack(recipe, tmp_path / "gaming.setpiecepack")
    legacy_path = tmp_path / "gaming.ritualistpack"
    shutil.copy2(exported.output_path, legacy_path)

    assert exported.output_path.suffix == ".setpiecepack"
    assert validate_pack(legacy_path).path == legacy_path
    record = import_pack(legacy_path)
    assert record.status == "disabled"


def test_legacy_recipe_pack_manifest_is_readable(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SETPIECE_E2E", "1")
    monkeypatch.setenv("SETPIECE_E2E_APP_DATA_DIR", str(tmp_path / "appdata"))
    recipe = REPO_ROOT / "setpiece" / "sample_recipes" / "gaming_mode.yaml"
    exported = export_recipe_pack(recipe, tmp_path / "gaming.setpiecepack").output_path
    legacy_path = _legacy_pack_manifest(
        exported,
        tmp_path / "gaming.ritualistpack",
        legacy_schema="ritualist.pack.v1",
    )

    validated = validate_pack(legacy_path)
    assert validated.manifest.schema == "ritualist.pack.v1"
    assert validated.manifest.required_setpiece_version.startswith(">=")
    record = import_pack(legacy_path)
    assert record.status == "disabled"


def test_legacy_visual_and_suite_extensions_are_input_only(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SETPIECE_E2E", "1")
    monkeypatch.setenv("SETPIECE_E2E_APP_DATA_DIR", str(tmp_path / "appdata"))
    canvas = _visual_canvas(tmp_path)
    theme = _theme_path(tmp_path)
    recipe = REPO_ROOT / "setpiece" / "sample_recipes" / "gaming_mode.yaml"

    canvas_pack = export_canvas_pack(canvas, tmp_path / "minimal.setpiececanvas").output_path
    theme_pack = export_theme_pack(theme, tmp_path / "paper.setpiecetheme").output_path
    ritual_pack = export_recipe_pack(recipe, tmp_path / "gaming.setpiecepack").output_path
    legacy_canvas = tmp_path / "minimal.ritualistcanvas"
    legacy_suite = tmp_path / "room.ritualistsuite"
    shutil.copy2(canvas_pack, legacy_canvas)
    imported_canvas = import_canvas_pack(legacy_canvas)
    assert imported_canvas.status == "quarantined"

    suite = export_suite_pack(
        canvas_pack=canvas_pack,
        theme_pack=theme_pack,
        ritual_packs=[ritual_pack],
        out=tmp_path / "room.setpiecesuite",
        suite_id="minimal_suite",
        name="Minimal Suite",
    )
    shutil.copy2(suite.output_path, legacy_suite)
    assert suite.output_path.suffix == ".setpiecesuite"
    assert validate_suite_pack(legacy_suite).manifest.id == "minimal_suite"


def test_legacy_visual_and_suite_manifests_are_readable(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SETPIECE_E2E", "1")
    monkeypatch.setenv("SETPIECE_E2E_APP_DATA_DIR", str(tmp_path / "appdata"))
    canvas = _visual_canvas(tmp_path)
    theme = _theme_path(tmp_path)
    recipe = REPO_ROOT / "setpiece" / "sample_recipes" / "gaming_mode.yaml"

    legacy_canvas = _legacy_pack_manifest(
        export_canvas_pack(canvas, tmp_path / "minimal.setpiececanvas").output_path,
        tmp_path / "minimal.ritualistcanvas",
        legacy_schema="ritualist.canvas_pack.v1",
    )
    legacy_theme = _legacy_pack_manifest(
        export_theme_pack(theme, tmp_path / "paper.setpiecetheme").output_path,
        tmp_path / "paper.ritualisttheme",
        legacy_schema="ritualist.theme_pack.v1",
    )
    legacy_ritual = _legacy_pack_manifest(
        export_recipe_pack(recipe, tmp_path / "gaming.setpiecepack").output_path,
        tmp_path / "gaming.ritualistpack",
        legacy_schema="ritualist.pack.v1",
    )

    canvas_record = import_canvas_pack(legacy_canvas)
    theme_record = import_theme_pack(legacy_theme)
    assert canvas_record.status == "quarantined"
    assert theme_record.status == "quarantined"

    legacy_suite = tmp_path / "room.ritualistsuite"
    _write_legacy_suite_pack(
        legacy_suite,
        canvas_pack=legacy_canvas,
        theme_pack=legacy_theme,
        ritual_pack=legacy_ritual,
    )
    validated_suite = validate_suite_pack(legacy_suite)
    assert validated_suite.manifest.schema == "ritualist.suite_pack.v1"
    suite_record = import_suite_pack(legacy_suite)
    assert suite_record.status == "quarantined"
    assert suite_record.canvas_import["status"] == "quarantined"
    assert suite_record.theme_import and suite_record.theme_import["status"] == "quarantined"
    assert suite_record.ritual_imports[0]["status"] == "disabled"


def test_setpiece_rebrand_stale_reference_scan_passes() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_setpiece_rebrand.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def _visual_canvas(tmp_path: Path) -> Path:
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


def _legacy_pack_manifest(source: Path, destination: Path, *, legacy_schema: str) -> Path:
    def update_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
        manifest["schema"] = legacy_schema
        manifest["required_ritualist_version"] = manifest.pop(
            "required_setpiece_version",
            ">=0.2.0-alpha.1",
        )
        return manifest

    return _rewrite_zip_manifest(source, destination, update_manifest)


def _rewrite_zip_manifest(
    source: Path,
    destination: Path,
    update_manifest: Callable[[dict[str, Any]], dict[str, Any]],
) -> Path:
    with ZipFile(source) as archive:
        entries = {info.filename: archive.read(info) for info in archive.infolist() if not info.is_dir()}
    manifest = yaml.safe_load(entries["manifest.yaml"].decode("utf-8"))
    entries["manifest.yaml"] = yaml.safe_dump(
        update_manifest(manifest),
        sort_keys=False,
        allow_unicode=True,
    ).encode("utf-8")
    with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return destination


def _write_legacy_suite_pack(
    destination: Path,
    *,
    canvas_pack: Path,
    theme_pack: Path,
    ritual_pack: Path,
) -> Path:
    canvas_entry = f"packs/canvas/{canvas_pack.name}"
    theme_entry = f"packs/theme/{theme_pack.name}"
    ritual_entry = f"packs/rituals/{ritual_pack.name}"
    manifest = {
        "schema": "ritualist.suite_pack.v1",
        "pack_type": "suite",
        "id": "legacy_suite",
        "name": "Legacy Suite",
        "version": "0.1.0",
        "description": "Old-format suite fixture",
        "required_ritualist_version": ">=0.2.0-alpha.1",
        "contents": {
            "canvas": {
                "path": canvas_entry,
                "behavior_bearing": False,
                "disabled_on_import": True,
            },
            "theme": {
                "path": theme_entry,
                "behavior_bearing": False,
                "disabled_on_import": True,
            },
            "rituals": [
                {
                    "path": ritual_entry,
                    "behavior_bearing": True,
                    "disabled_on_import": True,
                }
            ],
        },
        "behavior_bearing_contents": [ritual_entry],
        "safety": {
            "no_arbitrary_code": True,
            "no_executable_assets": True,
            "no_auto_run": True,
            "no_auto_enable": True,
            "no_remote_execution": True,
            "no_remembered_approvals": True,
            "imports_enter_quarantine": True,
            "rituals_disabled_until_enabled": True,
            "marketplace_out_of_scope": True,
        },
    }
    with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
        archive.writestr("manifest.yaml", yaml.safe_dump(manifest, sort_keys=False))
        archive.writestr(canvas_entry, canvas_pack.read_bytes())
        archive.writestr(theme_entry, theme_pack.read_bytes())
        archive.writestr(ritual_entry, ritual_pack.read_bytes())
    return destination
