from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ritualist.canvas import (
    CanvasBindingKind,
    CanvasComponent,
    CanvasComponentBinding,
    CanvasComponentPerformanceProfile,
    CanvasComponentUpdateRate,
    CanvasDocument,
    CANVAS_PERFORMANCE_SCHEMA_VERSION,
    CanvasPerformanceMode,
    canvas_performance_diagnostics,
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
    assert payload["view_summary"]["theme_id"] == "ritualist_default"
    assert payload["view_summary"]["theme_validation"]["valid"] is True
    budget = payload["view_summary"]["performance_budget"]
    assert budget["schema_version"] == "ritualist.canvas.performance_diagnostics.v1"
    assert budget["component_count"] == 12
    assert budget["estimated_cost"] in {"low", "medium", "high"}
    assert budget["component_profiles"]["by_type"]


def test_static_canvas_has_low_visual_cost() -> None:
    canvas = CanvasDocument(
        id="static_perf",
        name="Static Performance",
        components=(
            CanvasComponent(
                id="label",
                type="text.label",
                width=220,
                height=64,
                props={"text": "Static"},
            ),
            CanvasComponent(id="shape", type="shape", width=120, height=80),
        ),
    )

    diagnostics = canvas_performance_diagnostics(canvas)

    assert diagnostics["estimated_cost"] == "low"
    assert diagnostics["live_widgets"] == 0
    assert diagnostics["warnings"] == []


def test_many_live_widgets_emit_performance_warning() -> None:
    canvas = CanvasDocument(
        id="live_perf",
        name="Live Performance",
        components=tuple(
            CanvasComponent(
                id=f"clock_{index}",
                type="clock",
                width=120,
                height=80,
            )
            for index in range(90)
        ),
    )

    diagnostics = canvas_performance_diagnostics(canvas)

    assert diagnostics["live_widgets"] == 90
    assert diagnostics["estimated_cost"] == "high"
    assert any("live widgets" in warning for warning in diagnostics["warnings"])


def test_component_performance_profile_rejects_unsupported_update_rate() -> None:
    with pytest.raises(ValueError):
        CanvasComponentPerformanceProfile(component_type="bad", update_rate="turbo")


def test_component_performance_profile_rejects_updates_faster_than_policy() -> None:
    with pytest.raises(ValueError, match="faster than declared"):
        CanvasComponentPerformanceProfile(
            component_type="fast",
            update_rate=CanvasComponentUpdateRate.MEDIUM,
            max_update_interval_ms=50,
        )


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
        "tokens[name] !== undefined",
        "\"size\"",
        "\"align\"",
        "\"fit\"",
        "\"fill\"",
        "\"stroke\"",
    ):
        assert snippet in qml


def test_canvas_use_qml_wires_desktop_work_area_exit_affordance() -> None:
    qml = Path("ritualist/canvas/qml/CanvasUse.qml").read_text(encoding="utf-8")

    for snippet in (
        "ritualistCanvasHost",
        'hostSettings.mode === "desktop_work_area"',
        "property bool backgroundPassthrough",
        "hostSettings.background_passthrough === true",
        'color: backgroundPassthrough ? "transparent"',
        "visible: !root.backgroundPassthrough",
        'root.backgroundPassthrough ? "transparent"',
        'text: "Exit Desktop Canvas"',
        'sequence: "Esc"',
    ):
        assert snippet in qml


def test_canvas_use_qml_uses_paper_tokens_and_visible_state_roles() -> None:
    qml = Path("ritualist/canvas/qml/CanvasUse.qml").read_text(encoding="utf-8")

    for snippet in (
        "component PaperButton: Button",
        "QtQuick.Controls.Basic",
        "focusPolicy: Qt.StrongFocus",
        "buttonBorder(control.role, control.enabled, control.activeFocus)",
        "stateIsDanger(status)",
        'status === "interrupted"',
        'status === "confirming"',
        'role: "danger"',
        'role: "warning"',
        'role: "primary"',
        'root.token("background"',
        'root.token("panel"',
        'root.token("success_panel"',
        'root.token("warning_panel"',
        'root.token("danger_panel"',
        'root.token("focus_panel"',
        "root.radiusLg",
        "root.spaceMd",
    ):
        assert snippet in qml
