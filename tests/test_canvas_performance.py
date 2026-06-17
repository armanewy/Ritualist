from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from ritualist.canvas import (
    CanvasBindingKind,
    CanvasComponent,
    CanvasComponentBinding,
    CanvasDocument,
    CANVAS_PERFORMANCE_SCHEMA_VERSION,
    CanvasPerformanceMode,
    performance_settings_for_mode,
)
from ritualist.canvas.app import build_canvas_use_payload
from ritualist.cli import app


def test_canvas_performance_modes_are_stable() -> None:
    low = performance_settings_for_mode("low")
    balanced = performance_settings_for_mode("balanced")
    high = performance_settings_for_mode("high", show_performance_overlay=True)

    assert low.mode is CanvasPerformanceMode.LOW
    assert low.animations is False
    assert low.shadows == "none"
    assert low.image_resolution_cap < balanced.image_resolution_cap < high.image_resolution_cap
    assert low.live_update_rate_hz < balanced.live_update_rate_hz < high.live_update_rate_hz
    assert high.show_performance_overlay is True
    assert high.to_dict()["schema_version"] == CANVAS_PERFORMANCE_SCHEMA_VERSION


def test_perf_canvas_use_command_still_works() -> None:
    result = CliRunner().invoke(app, ["perf", "canvas-use", "--mock-components", "12", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["operation"] == "perf.canvas-use"
    assert payload["counts"]["components"] == 12
    assert payload["view_summary"]["component_count"] == 12


def test_canvas_use_payload_does_not_discover_recipes_or_targets(monkeypatch) -> None:
    def fail_discovery(*_args, **_kwargs):
        raise AssertionError("Canvas Use payload must use precomputed binding ids")

    monkeypatch.setattr("ritualist.canvas.runtime.discover_recipes", fail_discovery)
    monkeypatch.setattr("ritualist.canvas.runtime.builtin_target_catalog", fail_discovery)
    canvas = CanvasDocument(
        id="use_payload",
        name="Use Payload",
        components=(
            CanvasComponent(
                id="recipe",
                type="ritual.card",
                width=320,
                height=180,
                binding=CanvasComponentBinding(kind=CanvasBindingKind.RECIPE, recipe_id="gaming_mode"),
                props={"title": "Gaming"},
            ),
            CanvasComponent(
                id="target",
                type="target.card",
                width=320,
                height=180,
                binding=CanvasComponentBinding(kind=CanvasBindingKind.TARGET_START, target="diablo_iv"),
                props={"title": "Diablo"},
            ),
        ),
    )

    payload = build_canvas_use_payload(
        canvas,
        recipe_ids={"gaming_mode"},
        target_ids={"diablo_iv"},
    )
    components = {component["id"]: component for component in payload["components"]}

    assert components["recipe"]["enabled_actions"]
    assert components["target"]["enabled_actions"] == ["preview_plan"]
    assert payload["runtime"]["unresolved_binding_warnings"] == []


def test_canvas_use_payload_keeps_missing_bindings_disabled_without_discovery(monkeypatch) -> None:
    def fail_discovery(*_args, **_kwargs):
        raise AssertionError("Canvas Use payload must not discover from the payload getter")

    monkeypatch.setattr("ritualist.canvas.runtime.discover_recipes", fail_discovery)
    monkeypatch.setattr("ritualist.canvas.runtime.builtin_target_catalog", fail_discovery)
    canvas = CanvasDocument(
        id="missing_payload",
        name="Missing Payload",
        components=(
            CanvasComponent(
                id="missing_recipe",
                type="ritual.card",
                width=320,
                height=180,
                binding=CanvasComponentBinding(
                    kind=CanvasBindingKind.RECIPE,
                    recipe_id="definitely_missing_recipe",
                ),
                props={"title": "Missing"},
            ),
        ),
    )

    payload = build_canvas_use_payload(canvas, recipe_ids={"gaming_mode"}, target_ids={"diablo_iv"})
    component = payload["components"][0]

    assert component["enabled_actions"] == []
    assert "definitely_missing_recipe" in component["warnings"][0]


def test_canvas_use_qml_wires_performance_and_typed_delegates() -> None:
    qml = Path("ritualist/canvas/qml/CanvasUse.qml").read_text(encoding="utf-8")

    for snippet in (
        "payloadDrainTimer",
        "liveUpdateIntervalMs",
        "maxAnimatedComponents",
        "imageResolutionCap",
        "sourceSize.width",
        "measuredFps",
        "measuredPayloadUpdates",
        "lastPayloadUpdateMs",
        "componentShadow",
        "cardDelegate",
        "statusDelegate",
        "activityDelegate",
        "dockDelegate",
        "imageDelegate",
        "clockDelegate",
        "textDelegate",
        "shapeDelegate",
        "\"size\"",
        "\"align\"",
        "\"fit\"",
        "\"fill\"",
        "\"stroke\"",
    ):
        assert snippet in qml
