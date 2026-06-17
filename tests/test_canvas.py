from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from ritualist.canvas import (
    CANVAS_SCHEMA_VERSION,
    CanvasBindingKind,
    CanvasComponent,
    CanvasComponentBinding,
    CanvasDocument,
    CanvasImportedPolicy,
    canvas_to_home_model,
    create_component_registry,
    create_default_canvases,
    create_mock_canvas,
    list_canvases,
    load_canvas,
    recipe_card_component,
    save_canvas,
    validate_canvas,
    validate_canvas_document,
)
from ritualist.cli import app
from ritualist.home.models import HomeCardStatus


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


def test_triggering_components_declare_policy_implications() -> None:
    registry = create_component_registry()
    triggering = [component for component in registry.all() if component.can_trigger_actions]

    assert triggering
    assert all(component.requires_policy_or_doctor_state for component in triggering)
    assert all(component.actions for component in triggering)
    assert all(component.allowed_in_untrusted_packs is False for component in triggering)


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
