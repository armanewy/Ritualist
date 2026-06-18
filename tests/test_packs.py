from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

import pytest
import yaml

from typer.testing import CliRunner

from ritualist.cli import app
from ritualist.packs import (
    MANIFEST_NAME,
    README_NAME,
    RECIPE_NAME,
    PACK_SCHEMA_V1,
    PackImportError,
    PackValidationError,
    enable_import,
    export_recipe_pack,
    import_pack,
    list_imports,
    validate_pack,
)
from ritualist.recipe_loader import load_recipe


SAFETY = {
    "no_arbitrary_code": True,
    "no_coordinate_clicks": True,
    "no_remote_execution": True,
    "imported_recipes_must_not_run_automatically": True,
}


def test_validate_pack_accepts_v1_manifest_recipe_readme_and_assets(tmp_path):
    path = _write_pack(
        tmp_path,
        manifest=_manifest(),
        recipe=_recipe(),
        extra={
            "README.md": "# Demo\n",
            "assets/icon.txt": "icon",
        },
    )

    pack = validate_pack(path)

    assert pack.manifest.schema == PACK_SCHEMA_V1
    assert pack.manifest.id == "demo_pack"
    assert pack.recipe.id == "demo_recipe"
    assert pack.readme == "# Demo\n"
    assert pack.asset_names == ("assets/icon.txt",)


def test_manifest_variables_supply_recipe_template_defaults(tmp_path):
    path = _write_pack(
        tmp_path,
        manifest=_manifest(variables={"duration": {"default": 0.25}}),
        recipe={
            "version": "0.1",
            "id": "demo_recipe",
            "name": "Demo",
            "steps": [{"action": "wait.seconds", "seconds": "{{ duration }}"}],
        },
    )

    pack = validate_pack(path)

    assert pack.recipe.steps[0].seconds == 0.25


def test_validate_pack_rejects_missing_manifest(tmp_path):
    path = _write_pack(tmp_path, manifest=None, recipe=_recipe())

    with pytest.raises(PackValidationError, match="missing manifest.yaml"):
        validate_pack(path)


def test_validate_pack_rejects_unknown_schema(tmp_path):
    manifest = _manifest(schema="ritualist.pack.v2")
    path = _write_pack(tmp_path, manifest=manifest, recipe=_recipe())

    with pytest.raises(PackValidationError, match="unsupported pack schema"):
        validate_pack(path)


def test_validate_pack_rejects_unknown_actions(tmp_path):
    manifest = _manifest(required_actions=["assert.unknown"])
    path = _write_pack(tmp_path, manifest=manifest, recipe=_recipe())

    with pytest.raises(PackValidationError, match="unknown action"):
        validate_pack(path)


def test_validate_pack_accepts_primitive_only_capability_declarations(tmp_path):
    manifest = _manifest(
        required_actions=["wait.seconds"],
        required_capabilities=[
            "network_connectivity",
            "diagnostics_collect",
        ],
    )
    path = _write_pack(tmp_path, manifest=manifest, recipe=_recipe())

    pack = validate_pack(path)

    assert pack.manifest.required_capabilities == [
        "network_connectivity",
        "diagnostics_collect",
    ]


def test_validate_pack_rejects_primitive_capability_platform_mismatch(tmp_path):
    manifest = _manifest(
        required_actions=["wait.seconds"],
        required_capabilities=["hardware_inventory"],
    )
    path = _write_pack(tmp_path, manifest=manifest, recipe=_recipe())

    with pytest.raises(
        PackValidationError,
        match="supported_os includes OS not supported by hardware_inventory",
    ):
        validate_pack(path)


def test_validate_pack_accepts_windows_only_primitive_capability(tmp_path):
    manifest = _manifest(
        required_actions=["wait.seconds"],
        required_capabilities=["hardware_inventory"],
    )
    manifest["supported_os"] = ["windows"]
    path = _write_pack(tmp_path, manifest=manifest, recipe=_recipe())

    pack = validate_pack(path)

    assert pack.manifest.required_capabilities == ["hardware_inventory"]
    assert pack.manifest.supported_os == ["windows"]


def test_validate_pack_rejects_arbitrary_code_actions(tmp_path):
    manifest = _manifest(required_actions=["shell.run"])
    recipe = {
        "version": "0.1",
        "id": "demo_recipe",
        "name": "Demo",
        "steps": [{"action": "shell.run", "command": "echo unsafe"}],
    }
    path = _write_pack(tmp_path, manifest=manifest, recipe=recipe)

    with pytest.raises(PackValidationError, match="arbitrary code actions"):
        validate_pack(path)


def test_validate_pack_rejects_coordinate_click_actions(tmp_path):
    manifest = _manifest(required_actions=["desktop.click_coordinates"])
    recipe = {
        "version": "0.1",
        "id": "demo_recipe",
        "name": "Demo",
        "steps": [{"action": "desktop.click_coordinates", "x": 1, "y": 2}],
    }
    path = _write_pack(tmp_path, manifest=manifest, recipe=recipe)

    with pytest.raises(PackValidationError, match="coordinate click actions"):
        validate_pack(path)


def test_validate_pack_rejects_record_replay_actions(tmp_path):
    manifest = _manifest(required_actions=["record.start"])
    recipe = {
        "version": "0.1",
        "id": "demo_recipe",
        "name": "Demo",
        "steps": [{"action": "record.start"}],
    }
    path = _write_pack(tmp_path, manifest=manifest, recipe=recipe)

    with pytest.raises(PackValidationError, match="record/replay actions"):
        validate_pack(path)


def test_validate_pack_accepts_actions_disabled_by_default_for_import_review(tmp_path):
    manifest = _manifest(
        required_actions=["app.launch"],
        required_capabilities=["app_launch"],
    )
    recipe = {
        "version": "0.1",
        "id": "demo_recipe",
        "name": "Demo",
        "steps": [{"action": "app.launch", "command": "demo.exe"}],
    }
    path = _write_pack(tmp_path, manifest=manifest, recipe=recipe)

    pack = validate_pack(path)

    assert pack.recipe.steps[0].action == "app.launch"


def test_validate_pack_rejects_zip_path_traversal(tmp_path):
    path = _write_pack(
        tmp_path,
        manifest=_manifest(),
        recipe=_recipe(),
        extra={"assets/../escape.txt": "unsafe"},
    )

    with pytest.raises(PackValidationError, match="path traversal"):
        validate_pack(path)


def test_validate_pack_requires_manifest_actions_to_cover_recipe(tmp_path):
    path = _write_pack(
        tmp_path,
        manifest=_manifest(required_actions=["confirm.ask"]),
        recipe=_recipe(),
    )

    with pytest.raises(PackValidationError, match="required_actions must include"):
        validate_pack(path)


def test_validate_pack_requires_capabilities_for_actions(tmp_path):
    manifest = _manifest(required_actions=["wait.for_file"], required_capabilities=[])
    recipe = {
        "version": "0.1",
        "id": "demo_recipe",
        "name": "Demo",
        "steps": [{"action": "wait.for_file", "path": "marker.txt"}],
    }
    path = _write_pack(tmp_path, manifest=manifest, recipe=recipe)

    with pytest.raises(PackValidationError, match="required_capabilities"):
        validate_pack(path)


def test_validate_pack_requires_true_safety_declarations(tmp_path):
    manifest = _manifest()
    manifest["safety"] = {**SAFETY, "no_coordinate_clicks": False}
    path = _write_pack(tmp_path, manifest=manifest, recipe=_recipe())

    with pytest.raises(PackValidationError, match="safety declarations"):
        validate_pack(path)


def test_export_recipe_pack_writes_v1_pack_and_readme(tmp_path):
    recipe_path = tmp_path / "demo.yaml"
    recipe_path.write_text(
        """
version: "0.1"
id: demo
name: Demo
variables:
  marker_path: marker.txt
steps:
  - action: wait.for_file
    path: "{{ marker_path }}"
""".lstrip(),
        encoding="utf-8",
    )
    readme_path = tmp_path / "README-source.md"
    readme_path.write_text("# Demo\nReview before enabling.\n", encoding="utf-8")
    out_path = tmp_path / "demo.ritualistpack"

    result = export_recipe_pack(recipe_path, out_path, readme_path=readme_path)

    assert result.recipe_id == "demo"
    assert result.entries == (MANIFEST_NAME, RECIPE_NAME, README_NAME)
    pack = validate_pack(out_path)
    assert pack.manifest.schema == PACK_SCHEMA_V1
    assert pack.manifest.required_actions == ["wait.for_file"]
    assert pack.manifest.required_capabilities == ["file_read"]
    assert pack.manifest.variables == {
        "marker_path": {
            "required": True,
            "type": "string",
            "validation_default": "__REQUIRED_marker_path__",
        }
    }
    assert pack.recipe.variables == {"marker_path": "__REQUIRED_marker_path__"}
    assert pack.readme == "# Demo\nReview before enabling.\n"


def test_pack_export_redacts_variable_values_from_archive(tmp_path):
    recipe_path = tmp_path / "secret.yaml"
    recipe_path.write_text(
        """
version: "0.1"
id: secret_demo
name: Secret Demo
variables:
  marker_path: C:/Users/you/private-marker.txt
  nested:
    token: super-secret-token
steps:
  - action: wait.for_file
    path: "{{ marker_path }}"
  - action: wait.for_file
    path: C:/Users/you/private-literal-marker.txt
""".lstrip(),
        encoding="utf-8",
    )
    out_path = tmp_path / "secret.ritualistpack"

    export_recipe_pack(recipe_path, out_path)

    with ZipFile(out_path) as archive:
        manifest_text = archive.read(MANIFEST_NAME).decode("utf-8")
        recipe_text = archive.read(RECIPE_NAME).decode("utf-8")
        manifest = yaml.safe_load(manifest_text)
        recipe = yaml.safe_load(recipe_text)

    packed_text = manifest_text + recipe_text
    assert "private-marker.txt" not in packed_text
    assert "private-literal-marker.txt" not in packed_text
    assert "super-secret-token" not in packed_text

    assert manifest["variables"]["marker_path"]["validation_default"] == (
        "__REQUIRED_marker_path__"
    )
    assert manifest["variables"]["steps_1_path"]["validation_default"] == (
        "__REQUIRED_steps_1_path__"
    )
    assert manifest["variables"]["nested"]["validation_default"] == {
        "token": "__REQUIRED_token__"
    }
    assert recipe["variables"] == {
        "marker_path": "__REQUIRED_marker_path__",
        "nested": {"token": "__REQUIRED_token__"},
        "steps_1_path": "__REQUIRED_steps_1_path__",
    }
    assert recipe["steps"][1]["path"] == "{{ steps_1_path }}"


def test_pack_export_does_not_leak_local_paths_or_profile_locations(tmp_path):
    recipe_path = tmp_path / "privacy.yaml"
    recipe_path.write_text(
        """
version: "0.1"
id: privacy_demo
name: Privacy Demo
variables:
  battle_net_app: C:\\Users\\aoztu\\AppData\\Local\\Battle.net\\Battle.net Launcher.exe
  install_root: C:\\Program Files\\Vendor\\App.exe
  browser_profile: /home/aoztu/.config/ritualist/browser-profiles/chromium/default
steps:
  - action: app.launch
    command: "{{ battle_net_app }}"
  - action: wait.for_file
    path: /Users/aoztu/private-marker.txt
""".lstrip(),
        encoding="utf-8",
    )
    out_path = tmp_path / "privacy.ritualistpack"

    export_recipe_pack(recipe_path, out_path)

    with ZipFile(out_path) as archive:
        packed_text = archive.read(MANIFEST_NAME).decode("utf-8") + archive.read(RECIPE_NAME).decode(
            "utf-8"
        )

    assert "C:\\Users" not in packed_text
    assert "AppData" not in packed_text
    assert "Program Files" not in packed_text
    assert "/Users/" not in packed_text
    assert "/home/" not in packed_text
    assert "browser-profiles" not in packed_text


def test_gaming_mode_sample_exports_and_validates_as_pack(tmp_path):
    sample_path = (
        Path(__file__).resolve().parents[1]
        / "ritualist"
        / "sample_recipes"
        / "gaming_mode.yaml"
    )
    out_path = tmp_path / "gaming_mode.ritualistpack"

    result = export_recipe_pack(sample_path, out_path)
    pack = validate_pack(out_path)

    assert result.recipe_id == "gaming_mode"
    assert pack.manifest.id == "gaming_mode"
    assert pack.manifest.variables["ambience_url"]["validation_default"].startswith(
        "https://example.invalid/ritualist-required/"
    )
    assert pack.recipe.variables["ambience_url"].startswith(
        "https://example.invalid/ritualist-required/"
    )
    assert "browser.open" in pack.manifest.required_actions
    assert "desktop.click_text" in pack.manifest.required_actions
    assert pack.recipe.id == "gaming_mode"


def test_pack_export_includes_nested_flow_actions_and_condition_capabilities(tmp_path):
    recipe_path = tmp_path / "flow.yaml"
    recipe_path.write_text(
        """
version: "0.1"
id: flow_demo
name: Flow Demo
steps:
  - action: flow.if
    condition:
      type: window.text_visible
      window_title_contains: Battle.net
      text: Play
    then:
      - action: notify.toast
        title: Ready
        message: Play is visible.
    else:
      - action: wait.for_file
        path: marker.txt
""".lstrip(),
        encoding="utf-8",
    )
    out_path = tmp_path / "flow.ritualistpack"

    pack = validate_pack(export_recipe_pack(recipe_path, out_path).output_path)

    assert pack.manifest.required_actions == ["flow.if", "notify.toast", "wait.for_file"]
    assert "windows_uia" in pack.manifest.required_capabilities
    assert "file_read" in pack.manifest.required_capabilities
    assert pack.manifest.supported_os == ["windows"]


def test_validate_pack_requires_capabilities_for_nested_conditions(tmp_path):
    manifest = _manifest(
        required_actions=["flow.if", "notify.toast"],
        required_capabilities=[],
    )
    recipe = {
        "version": "0.1",
        "id": "demo_recipe",
        "name": "Demo",
        "steps": [
            {
                "action": "flow.if",
                "condition": {"type": "path.exists", "path": "marker.txt"},
                "then": [{"action": "notify.toast", "title": "Ready", "message": "Ready"}],
            }
        ],
    }
    pack_path = _write_pack(tmp_path, manifest=manifest, recipe=recipe)

    with pytest.raises(PackValidationError, match="condition capabilities: file_read"):
        validate_pack(pack_path)


def test_validate_pack_rejects_nested_coordinate_click_actions(tmp_path):
    manifest = _manifest(
        required_actions=["flow.if", "desktop.click_coordinates"],
        required_capabilities=[],
    )
    recipe = {
        "version": "0.1",
        "id": "demo_recipe",
        "name": "Demo",
        "steps": [
            {
                "action": "flow.if",
                "condition": {"type": "path.exists", "path": "marker.txt"},
                "then": [{"action": "desktop.click_coordinates", "x": 1, "y": 2}],
            }
        ],
    }
    pack_path = _write_pack(tmp_path, manifest=manifest, recipe=recipe)

    with pytest.raises(PackValidationError, match="coordinate click actions"):
        validate_pack(pack_path)


def test_pack_import_quarantines_disabled_and_enable_copies_recipe(tmp_path, monkeypatch):
    imported_root = tmp_path / "imported-packs"
    recipes_root = tmp_path / "recipes"
    monkeypatch.setattr("ritualist.packs.imported_packs_path", lambda: imported_root)
    monkeypatch.setattr(
        "ritualist.packs.imported_packs_dir",
        lambda: imported_root.mkdir(parents=True, exist_ok=True) or imported_root,
    )
    monkeypatch.setattr(
        "ritualist.packs.recipes_dir",
        lambda: recipes_root.mkdir(parents=True, exist_ok=True) or recipes_root,
    )
    pack_path = _write_pack(tmp_path, manifest=_manifest(), recipe=_recipe())

    record = import_pack(pack_path)

    assert record.status == "disabled"
    assert record.import_id == "demo_pack"
    assert (record.root / "import.json").exists()
    assert (record.root / RECIPE_NAME).exists()
    assert not (recipes_root / "demo_recipe.yaml").exists()
    assert [item.import_id for item in list_imports()] == ["demo_pack"]

    enabled = enable_import("demo_pack")

    assert enabled.status == "enabled"
    assert (recipes_root / "demo_recipe.yaml").exists()


def test_enable_import_allows_launch_actions_under_primitive_policy(tmp_path, monkeypatch):
    imported_root = tmp_path / "imported-packs"
    recipes_root = tmp_path / "recipes"
    monkeypatch.setattr("ritualist.packs.imported_packs_path", lambda: imported_root)
    monkeypatch.setattr(
        "ritualist.packs.imported_packs_dir",
        lambda: imported_root.mkdir(parents=True, exist_ok=True) or imported_root,
    )
    monkeypatch.setattr(
        "ritualist.packs.recipes_dir",
        lambda: recipes_root.mkdir(parents=True, exist_ok=True) or recipes_root,
    )
    pack_path = _write_pack(
        tmp_path,
        manifest=_manifest(
            required_actions=["app.launch"],
            required_capabilities=["app_launch"],
        ),
        recipe={
            "version": "0.1",
            "id": "demo_recipe",
            "name": "Demo",
            "steps": [{"action": "app.launch", "command": "demo.exe"}],
        },
    )

    record = import_pack(pack_path)

    enabled = enable_import(record.import_id)

    assert record.status == "disabled"
    assert enabled.status == "enabled"
    assert (recipes_root / "demo_recipe.yaml").exists()


def test_enable_import_rejects_browser_click_actions_blocked_by_import_policy(
    tmp_path,
    monkeypatch,
):
    imported_root = tmp_path / "imported-packs"
    recipes_root = tmp_path / "recipes"
    monkeypatch.setattr("ritualist.packs.imported_packs_path", lambda: imported_root)
    monkeypatch.setattr(
        "ritualist.packs.imported_packs_dir",
        lambda: imported_root.mkdir(parents=True, exist_ok=True) or imported_root,
    )
    monkeypatch.setattr(
        "ritualist.packs.recipes_dir",
        lambda: recipes_root.mkdir(parents=True, exist_ok=True) or recipes_root,
    )
    pack_path = _write_pack(
        tmp_path,
        manifest=_manifest(
            required_actions=["browser.click_text"],
            required_capabilities=["playwright", "browser_control"],
        ),
        recipe={
            "version": "0.1",
            "id": "demo_recipe",
            "name": "Demo",
            "steps": [{"action": "browser.click_text", "text": "Continue"}],
        },
    )

    record = import_pack(pack_path)

    with pytest.raises(PackImportError, match="blocked by primitive policy.*browser.interact.click_text"):
        enable_import(record.import_id)

    assert record.status == "disabled"
    assert not (recipes_root / "demo_recipe.yaml").exists()


def test_enable_import_rejects_nested_branch_actions_blocked_by_import_policy(
    tmp_path,
    monkeypatch,
):
    imported_root = tmp_path / "imported-packs"
    recipes_root = tmp_path / "recipes"
    monkeypatch.setattr("ritualist.packs.imported_packs_path", lambda: imported_root)
    monkeypatch.setattr(
        "ritualist.packs.imported_packs_dir",
        lambda: imported_root.mkdir(parents=True, exist_ok=True) or imported_root,
    )
    monkeypatch.setattr(
        "ritualist.packs.recipes_dir",
        lambda: recipes_root.mkdir(parents=True, exist_ok=True) or recipes_root,
    )
    pack_path = _write_pack(
        tmp_path,
        manifest=_manifest(
            required_actions=["flow.if", "browser.click_text"],
            required_capabilities=["file_read", "playwright", "browser_control"],
        ),
        recipe={
            "version": "0.1",
            "id": "demo_recipe",
            "name": "Demo",
            "steps": [
                {
                    "action": "flow.if",
                    "condition": {"type": "path.exists", "path": "marker.txt"},
                    "then": [{"action": "browser.click_text", "text": "Continue"}],
                }
            ],
        },
    )

    record = import_pack(pack_path)

    with pytest.raises(PackImportError, match="blocked by primitive policy.*browser.interact.click_text"):
        enable_import(record.import_id)

    assert record.status == "disabled"
    assert not (recipes_root / "demo_recipe.yaml").exists()


def test_enable_import_allows_read_only_browser_wait_actions(tmp_path, monkeypatch):
    imported_root = tmp_path / "imported-packs"
    recipes_root = tmp_path / "recipes"
    monkeypatch.setattr("ritualist.packs.imported_packs_path", lambda: imported_root)
    monkeypatch.setattr(
        "ritualist.packs.imported_packs_dir",
        lambda: imported_root.mkdir(parents=True, exist_ok=True) or imported_root,
    )
    monkeypatch.setattr(
        "ritualist.packs.recipes_dir",
        lambda: recipes_root.mkdir(parents=True, exist_ok=True) or recipes_root,
    )
    pack_path = _write_pack(
        tmp_path,
        manifest=_manifest(
            required_actions=["browser.wait_text"],
            required_capabilities=["playwright", "browser_control"],
        ),
        recipe={
            "version": "0.1",
            "id": "demo_recipe",
            "name": "Demo",
            "steps": [{"action": "browser.wait_text", "text": "Ready"}],
        },
    )

    record = import_pack(pack_path)
    enabled = enable_import(record.import_id)

    assert enabled.status == "enabled"
    assert (recipes_root / "demo_recipe.yaml").exists()


def test_enable_import_allows_read_only_browser_wait_when_playwright_missing(
    tmp_path,
    monkeypatch,
):
    imported_root = tmp_path / "imported-packs"
    recipes_root = tmp_path / "recipes"
    monkeypatch.setattr("ritualist.packs.imported_packs_path", lambda: imported_root)
    monkeypatch.setattr(
        "ritualist.packs.imported_packs_dir",
        lambda: imported_root.mkdir(parents=True, exist_ok=True) or imported_root,
    )
    monkeypatch.setattr(
        "ritualist.packs.recipes_dir",
        lambda: recipes_root.mkdir(parents=True, exist_ok=True) or recipes_root,
    )
    monkeypatch.setattr(
        "ritualist.doctor._module_available",
        lambda name: False if name == "playwright.sync_api" else True,
    )
    pack_path = _write_pack(
        tmp_path,
        manifest=_manifest(
            required_actions=["browser.wait_text"],
            required_capabilities=["playwright", "browser_control"],
        ),
        recipe={
            "version": "0.1",
            "id": "demo_recipe",
            "name": "Demo",
            "steps": [{"action": "browser.wait_text", "text": "Ready"}],
        },
    )

    record = import_pack(pack_path)
    enabled = enable_import(record.import_id)

    assert enabled.status == "enabled"
    assert (recipes_root / "demo_recipe.yaml").exists()


def test_enable_import_still_blocks_windows_only_doctor_errors(tmp_path, monkeypatch):
    imported_root = tmp_path / "imported-packs"
    recipes_root = tmp_path / "recipes"
    monkeypatch.setattr("ritualist.packs.imported_packs_path", lambda: imported_root)
    monkeypatch.setattr(
        "ritualist.packs.imported_packs_dir",
        lambda: imported_root.mkdir(parents=True, exist_ok=True) or imported_root,
    )
    monkeypatch.setattr(
        "ritualist.packs.recipes_dir",
        lambda: recipes_root.mkdir(parents=True, exist_ok=True) or recipes_root,
    )
    monkeypatch.setattr("ritualist.doctor.sys.platform", "linux")
    manifest = _manifest(
        required_actions=["assert.window_exists"],
        required_capabilities=["windows_uia", "window_management"],
    )
    manifest["supported_os"] = ["windows"]
    pack_path = _write_pack(
        tmp_path,
        manifest=manifest,
        recipe={
            "version": "0.1",
            "id": "demo_recipe",
            "name": "Demo",
            "steps": [
                {
                    "action": "assert.window_exists",
                    "title_contains": "Battle.net",
                }
            ],
        },
    )

    record = import_pack(pack_path)

    with pytest.raises(PackImportError, match="doctor validation failed"):
        enable_import(record.import_id)

    assert not (recipes_root / "demo_recipe.yaml").exists()


def test_enable_import_materializes_manifest_defaults_for_installed_recipe(
    tmp_path,
    monkeypatch,
):
    imported_root = tmp_path / "imported-packs"
    recipes_root = tmp_path / "recipes"
    monkeypatch.setattr("ritualist.packs.imported_packs_path", lambda: imported_root)
    monkeypatch.setattr(
        "ritualist.packs.imported_packs_dir",
        lambda: imported_root.mkdir(parents=True, exist_ok=True) or imported_root,
    )
    monkeypatch.setattr(
        "ritualist.packs.recipes_dir",
        lambda: recipes_root.mkdir(parents=True, exist_ok=True) or recipes_root,
    )
    pack_path = _write_pack(
        tmp_path,
        manifest=_manifest(variables={"duration": {"default": 0.25}}),
        recipe={
            "version": "0.1",
            "id": "demo_recipe",
            "name": "Demo",
            "steps": [{"action": "wait.seconds", "seconds": "{{ duration }}"}],
        },
    )

    record = import_pack(pack_path)
    enabled = enable_import(record.import_id)
    installed_recipe = load_recipe(recipes_root / "demo_recipe.yaml")

    assert enabled.status == "enabled"
    assert installed_recipe.steps[0].seconds == 0.25


def test_rejected_pack_is_not_imported(tmp_path, monkeypatch):
    imported_root = tmp_path / "imported-packs"
    monkeypatch.setattr("ritualist.packs.imported_packs_path", lambda: imported_root)
    monkeypatch.setattr(
        "ritualist.packs.imported_packs_dir",
        lambda: imported_root.mkdir(parents=True, exist_ok=True) or imported_root,
    )
    pack_path = _write_pack(
        tmp_path,
        manifest=_manifest(required_actions=["desktop.click_coordinates"]),
        recipe={
            "version": "0.1",
            "id": "demo_recipe",
            "name": "Demo",
            "steps": [{"action": "desktop.click_coordinates", "x": 1, "y": 2}],
        },
    )

    with pytest.raises(PackValidationError, match="coordinate click actions"):
        import_pack(pack_path)

    assert not imported_root.exists() or list(imported_root.iterdir()) == []


def test_pack_cli_export_import_and_list(tmp_path, monkeypatch):
    imported_root = tmp_path / "imported-packs"
    monkeypatch.setattr("ritualist.packs.imported_packs_path", lambda: imported_root)
    monkeypatch.setattr(
        "ritualist.packs.imported_packs_dir",
        lambda: imported_root.mkdir(parents=True, exist_ok=True) or imported_root,
    )
    recipe_path = _write_recipe_file(tmp_path, "cli_demo")
    out_path = tmp_path / "cli_demo.ritualistpack"

    export_result = CliRunner().invoke(
        app,
        ["pack", "export", str(recipe_path), "--out", str(out_path)],
    )
    import_result = CliRunner().invoke(app, ["pack", "import", str(out_path)])
    list_result = CliRunner().invoke(app, ["pack", "list-imports"])

    assert export_result.exit_code == 0, export_result.output
    assert "Exported pack" in export_result.output
    assert import_result.exit_code == 0, import_result.output
    assert "disabled" in import_result.output
    assert list_result.exit_code == 0, list_result.output
    assert "cli_demo" in list_result.output


def test_pack_cli_list_imports_reports_corrupt_records(monkeypatch):
    def raise_import_error():
        raise PackImportError("bad import record")

    monkeypatch.setattr("ritualist.cli.list_pack_imports", raise_import_error)

    result = CliRunner().invoke(app, ["pack", "list-imports"])

    assert result.exit_code == 1
    assert "bad import record" in result.output
    assert "Traceback" not in result.output


def test_pack_cli_help_works():
    result = CliRunner().invoke(app, ["pack", "--help"])

    assert result.exit_code == 0
    assert "export" in result.output
    assert "import" in result.output


def _manifest(
    *,
    schema: str = PACK_SCHEMA_V1,
    required_actions: list[str] | None = None,
    required_capabilities: list[str] | None = None,
    variables: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "schema": schema,
        "id": "demo_pack",
        "name": "Demo Pack",
        "version": "1.0.0",
        "required_ritualist_version": ">=0.1.0-alpha.1",
        "supported_os": ["windows", "macos", "linux"],
        "required_capabilities": required_capabilities or [],
        "required_actions": required_actions or ["wait.seconds"],
        "variables": variables or {},
        "safety": dict(SAFETY),
    }


def _recipe() -> dict[str, object]:
    return {
        "version": "0.1",
        "id": "demo_recipe",
        "name": "Demo",
        "steps": [{"action": "wait.seconds", "seconds": 0.1}],
    }


def _write_pack(
    tmp_path: Path,
    *,
    manifest: dict[str, object] | None,
    recipe: dict[str, object] | None,
    extra: dict[str, str] | None = None,
) -> Path:
    path = tmp_path / "demo.ritualistpack"
    with ZipFile(path, "w") as archive:
        if manifest is not None:
            archive.writestr("manifest.yaml", yaml.safe_dump(manifest, sort_keys=False))
        if recipe is not None:
            archive.writestr("recipe.yaml", yaml.safe_dump(recipe, sort_keys=False))
        for name, content in (extra or {}).items():
            archive.writestr(name, content)
    return path


def _write_recipe_file(tmp_path: Path, recipe_id: str) -> Path:
    path = tmp_path / f"{recipe_id}.yaml"
    path.write_text(
        f"""
version: "0.1"
id: {recipe_id}
name: {recipe_id}
steps:
  - action: wait.seconds
    seconds: 0.1
""".lstrip(),
        encoding="utf-8",
    )
    return path
