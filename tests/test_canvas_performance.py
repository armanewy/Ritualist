from __future__ import annotations

import json

from typer.testing import CliRunner

from ritualist.canvas import (
    CANVAS_PERFORMANCE_SCHEMA_VERSION,
    CanvasPerformanceMode,
    performance_settings_for_mode,
)
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
