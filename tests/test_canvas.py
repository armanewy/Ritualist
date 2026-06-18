from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from ritualist.canvas import (
    CANVAS_SCHEMA_VERSION,
    CanvasBackground,
    CanvasBackgroundType,
    CanvasBindingKind,
    CanvasComponent,
    CanvasComponentBinding,
    CanvasComponentRisk,
    CanvasDocument,
    CanvasImportedPolicy,
    canvas_to_home_model,
    create_component_registry,
    create_default_canvases,
    create_mock_canvas,
    list_canvases,
    load_bundled_canvas,
    load_canvas,
    normalize_canvas_bindings,
    recipe_card_component,
    save_canvas,
    validate_canvas,
    validate_canvas_bindings,
    validate_canvas_document,
    validate_canvas_structure,
)
from ritualist.canvas.app import _recent_activity_items, build_canvas_use_payload
from ritualist.cli import app
from ritualist.home.models import HomeCardStatus
from ritualist.run_logs import RunRecord


def _valid_canvas() -> CanvasDocument:
    return CanvasDocument(
        id="test_canvas",
        name="Test Canvas",
        components=(
            CanvasComponent(
                id="title",
                type="text.label",
                x=10,
                y=10,
                width=200,
                height=64,
                props={"text": "Hello"},
            ),
            CanvasComponent(
                id="recipe",
                type="ritual.card",
                x=10,
                y=90,
                width=320,
                height=180,
                props={"title": "Gaming", "recipe_id": "gaming_mode"},
                binding=CanvasComponentBinding(
                    kind=CanvasBindingKind.RECIPE,
                    recipe_id="gaming_mode",
                ),
            ),
        ),
    )


def test_canvas_background_accepts_transparent_and_system_wallpaper() -> None:
    transparent = CanvasBackground(type="transparent", value="")
    system_wallpaper = CanvasBackground(type="system-wallpaper")

    assert {background_type.value for background_type in CanvasBackgroundType} == {
        "solid",
        "gradient",
        "transparent",
        "system_wallpaper",
    }
    assert transparent.type is CanvasBackgroundType.TRANSPARENT
    assert transparent.model_dump(mode="json") == {"type": "transparent", "value": ""}
    assert system_wallpaper.type is CanvasBackgroundType.SYSTEM_WALLPAPER
    assert system_wallpaper.model_dump(mode="json") == {
        "type": "system_wallpaper",
        "value": "",
    }


@pytest.mark.parametrize(
    "background",
    [
        {"type": "video"},
        {"type": "transparent", "value": "https://example.invalid/wallpaper.mp4"},
        {"type": "system_wallpaper", "value": "assets/wallpaper.js"},
        {"type": "system_wallpaper", "value": "wallpaper.qml"},
    ],
)
def test_canvas_background_rejects_live_remote_or_executable_modes(background: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        CanvasBackground.model_validate(background)


def test_canvas_source_files_are_not_collapsed_into_one_line() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    key_canvas_files = {
        "ritualist/canvas/models.py",
        "ritualist/canvas/registry.py",
        "ritualist/canvas/storage.py",
        "ritualist/canvas/home_adapter.py",
        "ritualist/canvas/runtime.py",
        "ritualist/canvas/controller.py",
        "ritualist/canvas/view_model.py",
        "tests/test_canvas.py",
        "tests/test_canvas_runtime.py",
    }
    source_files = [
        *sorted((repo_root / "ritualist" / "canvas").glob("*.py")),
        *sorted((repo_root / "tests").glob("test_canvas*.py")),
    ]
    readable_files = [
        *source_files,
        *sorted((repo_root / "ritualist" / "sample_canvases").glob("*.yaml")),
        repo_root / "docs" / "canvas.md",
        repo_root / "docs" / "roadmap.md",
    ]

    assert source_files, "Canvas source files should be discovered"

    for path in readable_files:
        relative_path = path.relative_to(repo_root).as_posix()
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        line_count = len(lines)
        longest = max((len(line) for line in lines), default=0)
        file_size = path.stat().st_size

        assert line_count == text.count("\n") + int(bool(text) and not text.endswith("\n")), relative_path
        assert longest <= 1000, f"{relative_path} has an overlong line: {longest}"
        if file_size > 2048:
            assert line_count >= 20, f"{relative_path} appears collapsed into {line_count} lines"
        if relative_path in key_canvas_files:
            assert line_count >= 40, f"{relative_path} has suspiciously few lines: {line_count}"


def test_canvas_document_serializes_with_schema_alias() -> None:
    canvas = _valid_canvas()

    data = canvas.to_dict()

    assert data["schema"] == CANVAS_SCHEMA_VERSION
    assert data["id"] == "test_canvas"
    assert data["components"][0]["props"] == {"text": "Hello"}


def test_invalid_canvas_schema_rejected() -> None:
    with pytest.raises(ValidationError):
        CanvasDocument.model_validate({"schema": "wrong", "id": "x", "name": "X"})


def test_duplicate_component_ids_rejected() -> None:
    with pytest.raises(ValidationError):
        CanvasDocument(
            id="dupe_canvas",
            name="Dupe",
            components=(
                CanvasComponent(id="same", type="clock", width=100, height=64),
                CanvasComponent(id="same", type="clock", width=100, height=64),
            ),
        )


def test_unknown_component_type_rejected_by_validation() -> None:
    canvas = CanvasDocument(
        id="unknown_canvas",
        name="Unknown",
        components=(CanvasComponent(id="bad", type="webview.html", width=100, height=100),),
    )

    result = validate_canvas_document(canvas)

    assert not result.valid
    assert "unknown component type" in result.errors[0]


def test_missing_required_props_rejected() -> None:
    canvas = CanvasDocument(
        id="missing_props",
        name="Missing Props",
        components=(CanvasComponent(id="label", type="text.label", width=200, height=64),),
    )

    result = validate_canvas_document(canvas)

    assert not result.valid
    assert "missing required prop 'text'" in result.errors[0]


def test_invalid_binding_kind_rejected() -> None:
    with pytest.raises(ValidationError):
        CanvasComponentBinding.model_validate({"kind": "script"})


def test_negative_component_sizes_rejected() -> None:
    with pytest.raises(ValidationError):
        CanvasComponent(id="bad_size", type="clock", width=-1, height=64)


def test_unsupported_binding_rejected() -> None:
    canvas = CanvasDocument(
        id="bad_binding",
        name="Bad Binding",
        components=(
            CanvasComponent(
                id="clock",
                type="clock",
                width=180,
                height=80,
                binding=CanvasComponentBinding(kind=CanvasBindingKind.RECIPE, recipe_id="gaming_mode"),
            ),
        ),
    )

    result = validate_canvas_document(canvas)

    assert not result.valid
    assert "does not support recipe bindings" in result.errors[0]


def test_unresolved_recipe_and_target_bindings_are_warnings(monkeypatch) -> None:
    monkeypatch.setattr("ritualist.canvas.registry.discover_recipes", lambda: [])
    canvas = CanvasDocument(
        id="warnings_canvas",
        name="Warnings",
        components=(
            CanvasComponent(
                id="recipe",
                type="ritual.card",
                width=320,
                height=180,
                props={"title": "Missing"},
                binding=CanvasComponentBinding(kind=CanvasBindingKind.RECIPE, recipe_id="missing_recipe"),
            ),
            CanvasComponent(
                id="target",
                type="target.card",
                width=320,
                height=180,
                props={"title": "Missing Target"},
                binding=CanvasComponentBinding(kind=CanvasBindingKind.TARGET_START, target="missing_target"),
            ),
        ),
    )

    result = validate_canvas_document(canvas)

    assert result.valid
    assert any("recipe binding 'missing_recipe' is unresolved" in item for item in result.warnings)
    assert any("target binding 'missing_target' is unresolved" in item for item in result.warnings)


def test_legacy_prop_binding_reports_unresolved_recipe(monkeypatch) -> None:
    monkeypatch.setattr("ritualist.canvas.registry.discover_recipes", lambda: [])
    canvas = CanvasDocument(
        id="legacy_binding",
        name="Legacy Binding",
        components=(
            CanvasComponent(
                id="recipe",
                type="ritual.card",
                width=320,
                height=180,
                props={"title": "Missing", "recipe_id": "missing_recipe"},
            ),
        ),
    )

    result = validate_canvas_document(canvas)

    assert result.valid
    assert "recipe binding 'missing_recipe' is unresolved" in result.warnings[0]


def test_arbitrary_component_code_and_autorun_are_rejected() -> None:
    canvas = CanvasDocument(
        id="unsafe_canvas",
        name="Unsafe",
        components=(
            CanvasComponent(
                id="unsafe",
                type="text.label",
                width=240,
                height=64,
                props={"text": "Hi", "script": "doEvil()", "auto_run": True},
            ),
        ),
    )

    result = validate_canvas_document(canvas)

    assert not result.valid
    assert any("arbitrary component code is not allowed" in item for item in result.errors)
    assert any("auto-run behavior is not allowed" in item for item in result.errors)


def test_canvas_image_relative_asset_path_is_accepted_without_file_existence(tmp_path: Path) -> None:
    canvas_dir = tmp_path / "canvas"
    canvas = CanvasDocument(
        id="image_canvas",
        name="Image Canvas",
        components=(
            CanvasComponent(
                id="image",
                type="image",
                width=320,
                height=180,
                props={"path": "hero.png"},
            ),
        ),
    )

    result = validate_canvas_structure(canvas, canvas_dir=canvas_dir)

    assert result.valid


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("https://example.test/hero.png", "remote image URLs are not allowed"),
        ("../secret.png", "must stay inside the canvas assets folder"),
        ("assets/../secret.png", "must stay inside the canvas assets folder"),
        ("assets/run.exe", "executable or script-like image asset paths are not allowed"),
        ("hero.png:stream", "ambiguous drive-relative or stream-like image paths are not allowed"),
    ],
)
def test_canvas_image_asset_paths_reject_unsafe_values(
    tmp_path: Path,
    path: str,
    expected: str,
) -> None:
    canvas = CanvasDocument(
        id="bad_image_canvas",
        name="Bad Image Canvas",
        components=(
            CanvasComponent(
                id="image",
                type="image",
                width=320,
                height=180,
                props={"path": path},
            ),
        ),
    )

    result = validate_canvas_structure(canvas, canvas_dir=tmp_path / "canvas")

    assert not result.valid
    assert any(expected in item for item in result.errors)


def test_canvas_image_absolute_path_outside_assets_rejected(tmp_path: Path) -> None:
    outside = tmp_path / "outside" / "hero.png"
    canvas = CanvasDocument(
        id="absolute_image_canvas",
        name="Absolute Image Canvas",
        components=(
            CanvasComponent(
                id="image",
                type="image",
                width=320,
                height=180,
                props={"path": str(outside)},
            ),
        ),
    )

    result = validate_canvas_structure(canvas, canvas_dir=tmp_path / "canvas")

    assert not result.valid
    assert any("must stay inside the canvas assets folder" in item for item in result.errors)


def test_component_registry_registers_initial_types() -> None:
    registry = create_component_registry()
    required = {
        "ritual.card",
        "ritual.status",
        "ritual.controller",
        "target.card",
        "target.status",
        "category.dock",
        "app.launcher",
        "window.layout_button",
        "doctor.badge",
        "recent.activity",
        "clock",
        "text.label",
        "image",
        "shape",
        "spacer/divider",
    }

    assert required.issubset({component.type_id for component in registry.all()})
    assert all(component.imported_canvas_policy for component in registry.all())
    assert all(component.performance_class for component in registry.all())


def test_canvas_risk_taxonomy_aligns_with_primitive_risks() -> None:
    assert CanvasComponentRisk.READ_ONLY.value == "read_only"
    assert CanvasComponentRisk.LAUNCHES_APP.value == "launches_app"
    assert CanvasComponentRisk.CONTROLS_UI.value == "controls_ui"
    assert CanvasComponentRisk.MODIFIES_FILES.value == "modifies_files"
    assert CanvasComponentRisk.RISKY.value == "risky"


def test_canvas_theme_tokens_include_visual_polish_contract() -> None:
    canvas = CanvasDocument(id="theme_contract", name="Theme Contract")
    payload = canvas.to_dict()
    tokens = payload["theme"]["tokens"]

    for key in (
        "background",
        "foreground",
        "accent",
        "success",
        "muted",
        "panel",
        "success_panel",
        "warning_panel",
        "danger_panel",
        "focus_panel",
        "border",
        "focus_ring",
        "font_family",
        "font_size_body",
        "font_size_title",
        "radius_md",
        "spacing_md",
        "shadow",
        "motion_fast_ms",
        "motion_normal_ms",
    ):
        assert key in tokens


def test_core_components_expose_prop_schemas() -> None:
    registry = create_component_registry()
    expected_names = {
        "ritual.card": {"title", "recipe_id", "primary_action", "image"},
        "target.card": {"title", "target", "target_id", "primary_action"},
        "text.label": {"text", "size", "color", "align"},
        "image": {"path", "fit", "alt"},
        "clock": {"format", "timezone"},
        "recent.activity": {"title", "limit"},
    }

    for type_id, names in expected_names.items():
        prop_schemas = registry.get(type_id).prop_schemas
        assert prop_schemas, type_id
        assert names.issubset({schema.name for schema in prop_schemas})


def test_normalize_canvas_bindings_copies_legacy_recipe_and_target_props() -> None:
    canvas = CanvasDocument(
        id="legacy_normalize",
        name="Legacy Normalize",
        components=(
            CanvasComponent(
                id="recipe",
                type="ritual.card",
                width=320,
                height=180,
                props={"title": "Gaming", "recipe_id": "gaming_mode"},
            ),
            CanvasComponent(
                id="target",
                type="target.card",
                width=320,
                height=180,
                props={"title": "Diablo IV", "target": "diablo_iv"},
            ),
        ),
    )

    normalized = normalize_canvas_bindings(canvas)

    assert canvas.components[0].binding is None
    assert normalized.components[0].binding is not None
    assert normalized.components[0].binding.kind is CanvasBindingKind.RECIPE
    assert normalized.components[0].binding.recipe_id == "gaming_mode"
    assert normalized.components[1].binding is not None
    assert normalized.components[1].binding.kind is CanvasBindingKind.TARGET_START
    assert normalized.components[1].binding.target == "diablo_iv"


def test_triggering_components_declare_policy_implications() -> None:
    registry = create_component_registry()
    triggering = [component for component in registry.all() if component.can_trigger_actions]

    assert triggering
    assert all(component.requires_policy_or_doctor_state for component in triggering)
    assert all(component.actions for component in triggering)
    assert all(
        component.allowed_in_untrusted_packs is False or component.type_id.startswith("shortcut.")
        for component in triggering
    )


def test_imported_canvas_policy_blocks_triggering_components() -> None:
    canvas = CanvasDocument(
        id="imported_canvas",
        name="Imported",
        components=(
            CanvasComponent(
                id="launcher",
                type="app.launcher",
                width=220,
                height=96,
                props={"title": "Launch"},
                binding=CanvasComponentBinding(kind=CanvasBindingKind.APP_LAUNCHER, id="local"),
            ),
        ),
    )

    result = validate_canvas_document(canvas, imported=True)

    assert not result.valid
    assert "blocked in imported canvases" in result.errors[0]


def test_sample_canvases_validate() -> None:
    for reference in list_canvases(include_bundled=True):
        if reference.source != "bundled":
            continue
        result = validate_canvas(reference.path)
        assert result.valid, (reference.canvas_id, result.errors)


def test_gaming_desktop_includes_recent_activity_for_release_acceptance() -> None:
    canvas = load_bundled_canvas("gaming_desktop")
    components = {component.id: component for component in canvas.components}

    assert components["recent_activity"].type == "recent.activity"


def test_recent_activity_e2e_snapshot_extracts_run_ids() -> None:
    payload = {
        "components": [
            {
                "id": "recent_activity",
                "type": "recent.activity",
                "data": {
                    "items": [
                        {
                            "run_id": "run-123",
                            "recipe_id": "gaming_mode",
                            "status": "stopped",
                            "message": "Confirmation declined",
                            "stopped_reason": "stopped_user_declined_confirmation",
                        }
                    ]
                },
            }
        ]
    }

    assert _recent_activity_items(payload) == [
        {
            "component_id": "recent_activity",
            "run_id": "run-123",
            "recipe_id": "gaming_mode",
            "status": "stopped",
            "message": "Confirmation declined",
            "stopped_reason": "stopped_user_declined_confirmation",
        }
    ]


def test_canvas_use_payload_loads_recent_runs_only_when_requested(monkeypatch, tmp_path: Path) -> None:
    canvas = CanvasDocument(
        id="recent_canvas",
        name="Recent Canvas",
        components=(
            CanvasComponent(id="activity", type="recent.activity", width=320, height=160),
        ),
    )
    record = RunRecord(
        run_id="run-123",
        path=tmp_path / "run-123",
        metadata={
            "recipe_id": "gaming_mode",
            "final_state": "stopped",
            "final_message": "Confirmation declined",
        },
        steps=[],
    )
    monkeypatch.setattr("ritualist.canvas.runtime.list_recent_runs", lambda *, limit: [record])

    default_payload = build_canvas_use_payload(canvas, recipe_ids=set(), target_ids=set())
    live_payload = build_canvas_use_payload(
        canvas,
        recipe_ids=set(),
        target_ids=set(),
        load_recent_runs=True,
    )

    assert default_payload["components"][0]["data"]["items"] == []
    assert live_payload["components"][0]["data"]["items"][0]["run_id"] == "run-123"


def test_canvas_storage_default_creation_and_no_overwrite(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("ritualist.canvas.storage.canvases_path", lambda: tmp_path)
    monkeypatch.setattr("ritualist.canvas.storage.canvases_dir", lambda: tmp_path)

    first = create_default_canvases()
    second = create_default_canvases()

    assert first
    assert any(result.changed for result in first)
    assert second
    assert all(not result.changed for result in second)
    assert (tmp_path / "gaming_desktop.yaml").exists()


def test_canvas_load_save_roundtrip(tmp_path: Path) -> None:
    canvas = _valid_canvas()
    output = tmp_path / "canvas.yaml"

    result = save_canvas(canvas, output)
    loaded = load_canvas(output)

    assert result.changed is True
    assert loaded.to_dict() == canvas.to_dict()


def test_canvas_cli_list_show_validate_and_init(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("ritualist.canvas.storage.canvases_path", lambda: tmp_path)
    monkeypatch.setattr("ritualist.canvas.storage.canvases_dir", lambda: tmp_path)

    runner = CliRunner()
    init_result = runner.invoke(app, ["canvas", "init"])
    list_result = runner.invoke(app, ["canvas", "list", "--json"])
    show_result = runner.invoke(app, ["canvas", "show", "gaming_desktop", "--json"])
    validate_result = runner.invoke(app, ["canvas", "validate", "gaming_desktop"])

    assert init_result.exit_code == 0
    assert list_result.exit_code == 0
    assert show_result.exit_code == 0
    assert validate_result.exit_code == 0
    data = json.loads(show_result.output)
    assert data["schema_version"] == "ritualist.canvas.show.v1"
    assert data["canvas"]["id"] == "gaming_desktop"


def test_canvas_cli_create_default(tmp_path: Path) -> None:
    output = tmp_path / "default.yaml"

    result = CliRunner().invoke(app, ["canvas", "create-default", "--out", str(output)])

    assert result.exit_code == 0
    assert output.exists()
    assert load_canvas(output).id == "gaming_desktop"


def test_canvas_perf_model_100_and_300_json() -> None:
    runner = CliRunner()
    for count in (100, 300):
        result = runner.invoke(app, ["perf", "canvas-model", "--mock-components", str(count), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["operation"] == "perf.canvas-model"
        assert data["counts"]["components"] == count
        assert data["side_effects"] == "none"


def test_canvas_validation_does_not_execute_runtime(monkeypatch) -> None:
    def fail_discover_recipes():
        return []

    def fail_runtime(*_args, **_kwargs):
        raise AssertionError("canvas validation must not execute runtime")

    monkeypatch.setattr("ritualist.canvas.registry.discover_recipes", fail_discover_recipes)
    monkeypatch.setattr("ritualist.cli.WorkflowExecutor", fail_runtime)

    result = validate_canvas_document(_valid_canvas())

    assert result.valid


def test_canvas_structure_validation_does_not_discover_recipes_or_targets(monkeypatch) -> None:
    def fail_discover_recipes():
        raise AssertionError("structural validation must not discover recipes")

    def fail_target_catalog():
        raise AssertionError("structural validation must not read target catalog")

    monkeypatch.setattr("ritualist.canvas.registry.discover_recipes", fail_discover_recipes)
    monkeypatch.setattr("ritualist.canvas.registry.builtin_target_catalog", fail_target_catalog)

    result = validate_canvas_structure(_valid_canvas())

    assert result.valid


def test_canvas_live_binding_validation_reports_unresolved_bindings(monkeypatch) -> None:
    monkeypatch.setattr("ritualist.canvas.registry.discover_recipes", lambda: [])
    monkeypatch.setattr(
        "ritualist.canvas.registry.builtin_target_catalog",
        lambda: type("Catalog", (), {"targets": ()})(),
    )
    canvas = CanvasDocument(
        id="live_bindings",
        name="Live Bindings",
        components=(
            CanvasComponent(
                id="recipe",
                type="ritual.card",
                width=320,
                height=180,
                props={"title": "Missing"},
                binding=CanvasComponentBinding(kind=CanvasBindingKind.RECIPE, recipe_id="missing_recipe"),
            ),
            CanvasComponent(
                id="target",
                type="target.card",
                width=320,
                height=180,
                props={"title": "Missing Target"},
                binding=CanvasComponentBinding(kind=CanvasBindingKind.TARGET_START, target="missing_target"),
            ),
        ),
    )

    result = validate_canvas_bindings(canvas)

    assert result.valid
    assert any("recipe binding 'missing_recipe' is unresolved" in item for item in result.warnings)
    assert any("target binding 'missing_target' is unresolved" in item for item in result.warnings)


def test_canvas_to_home_model_converts_recipe_and_target_cards() -> None:
    canvas = CanvasDocument(
        id="home_canvas",
        name="Home Canvas",
        components=(
            recipe_card_component("gaming_mode", title="Gaming Mode"),
            CanvasComponent(
                id="diablo_target",
                type="target.card",
                width=320,
                height=180,
                props={"title": "Diablo IV"},
                binding=CanvasComponentBinding(kind=CanvasBindingKind.TARGET_START, target="diablo_iv"),
            ),
        ),
    )

    model = canvas_to_home_model(
        canvas,
        runtime_state={"gaming_mode": {"status": "running", "last_run_status": "running"}},
    )

    assert [card.id for card in model.cards] == ["gaming_mode", "diablo_target"]
    assert model.get_card("gaming_mode").status is HomeCardStatus.RUNNING
    assert model.get_card("diablo_target").category == "Targets"


def test_canvas_packs_do_not_carry_local_approvals() -> None:
    with pytest.raises(ValidationError):
        CanvasDocument.model_validate(
            {
                "schema": CANVAS_SCHEMA_VERSION,
                "id": "bad_pack",
                "name": "Bad Pack",
                "pack": {"remembered_approvals": ["run-gaming-mode"]},
            }
        )


def test_mock_canvas_generation_validates_without_binding_checks() -> None:
    canvas = create_mock_canvas(300)
    result = validate_canvas_document(canvas, check_bindings=False)

    assert len(canvas.components) == 300
    assert result.valid
