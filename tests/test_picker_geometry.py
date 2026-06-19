from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "picker" / "placement_contract.json"


def _load_contract() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _right(rect: dict[str, int]) -> int:
    return rect["x"] + rect["width"]


def _bottom(rect: dict[str, int]) -> int:
    return rect["y"] + rect["height"]


def _center(rect: dict[str, int]) -> tuple[int, int]:
    return rect["x"] + rect["width"] // 2, rect["y"] + rect["height"] // 2


def _contains_point(rect: dict[str, int], point: tuple[int, int]) -> bool:
    x, y = point
    return rect["x"] <= x < _right(rect) and rect["y"] <= y < _bottom(rect)


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(value, maximum))


def _scaled(value: int, scale: float) -> int:
    return int(round(value * scale))


def _taskbar_edge(monitor: dict[str, int], work_area: dict[str, int]) -> str | None:
    insets = {
        "left": max(0, work_area["x"] - monitor["x"]),
        "top": max(0, work_area["y"] - monitor["y"]),
        "right": max(0, _right(monitor) - _right(work_area)),
        "bottom": max(0, _bottom(monitor) - _bottom(work_area)),
    }
    edge, size = max(insets.items(), key=lambda item: item[1])
    return edge if size else None


def _primary_monitor(monitors: list[dict[str, Any]]) -> dict[str, Any]:
    for monitor in monitors:
        if monitor["primary"]:
            return monitor
    return monitors[0]


def _selected_monitor(scenario: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    anchor = scenario["anchor"]
    monitors = scenario["monitors"]
    if anchor["source"] == "tray":
        point = _center(anchor["rect"])
        for monitor in monitors:
            if _contains_point(monitor["monitor_rect"], point):
                return monitor, False
        return _primary_monitor(monitors), True

    point = (anchor["point"]["x"], anchor["point"]["y"])
    for monitor in monitors:
        if _contains_point(monitor["monitor_rect"], point):
            return monitor, True
    return _primary_monitor(monitors), True


def _anchor_rect(scenario: dict[str, Any]) -> dict[str, int]:
    anchor = scenario["anchor"]
    if anchor["source"] == "tray":
        return anchor["rect"]
    point = anchor["point"]
    return {"x": point["x"], "y": point["y"], "width": 1, "height": 1}


def _place_picker(contract: dict[str, Any], scenario: dict[str, Any]) -> tuple[dict[str, int], str, bool]:
    monitor, fallback_used = _selected_monitor(scenario)
    work_area = monitor["work_area"]
    anchor = _anchor_rect(scenario)
    scale = scenario["scale"]
    width = _scaled(contract["picker"]["logical_width"], scale)
    height = _scaled(contract["picker"]["logical_height"], scale)
    margin = _scaled(contract["picker"]["logical_margin"], scale)
    anchor_x, anchor_y = _center(anchor)
    min_x = work_area["x"] + margin
    max_x = _right(work_area) - margin - width
    min_y = work_area["y"] + margin
    max_y = _bottom(work_area) - margin - height
    edge = scenario["taskbar_edge"]

    if edge == "left":
        x = min_x
        y = _clamp(anchor_y - height // 2, min_y, max_y)
    elif edge == "right":
        x = max_x
        y = _clamp(anchor_y - height // 2, min_y, max_y)
    elif edge == "top":
        x = _clamp(anchor_x - width // 2, min_x, max_x)
        y = min_y
    else:
        x = _clamp(anchor_x - width // 2, min_x, max_x)
        y = max_y

    return {"x": x, "y": y, "width": width, "height": height}, monitor["name"], fallback_used


def _assert_not_clipped(rect: dict[str, int], work_area: dict[str, int]) -> None:
    assert rect["x"] >= work_area["x"]
    assert rect["y"] >= work_area["y"]
    assert _right(rect) <= _right(work_area)
    assert _bottom(rect) <= _bottom(work_area)


def test_picker_placement_contract_covers_required_geometry_cases() -> None:
    contract = _load_contract()
    scenarios = contract["scenarios"]

    assert contract["schema_version"] == "setpiece.picker.placement.v1"
    assert {scenario["taskbar_edge"] for scenario in scenarios} >= {
        "bottom",
        "top",
        "left",
        "right",
    }
    assert {scenario["scale"] for scenario in scenarios} >= {1.0, 1.25, 1.5}
    assert {scenario["expected"]["monitor"] for scenario in scenarios} >= {"primary", "secondary"}
    assert any(scenario["anchor"]["source"] == "cursor" for scenario in scenarios)
    assert any(scenario["expected"]["fallback_used"] for scenario in scenarios)


@pytest.mark.parametrize("scenario", _load_contract()["scenarios"], ids=lambda item: item["id"])
def test_picker_placement_matches_fixture_contract_without_gui_runtime(
    scenario: dict[str, Any],
) -> None:
    contract = _load_contract()

    rect, monitor_name, fallback_used = _place_picker(contract, scenario)

    assert monitor_name == scenario["expected"]["monitor"]
    assert fallback_used is scenario["expected"]["fallback_used"]
    assert rect == scenario["expected"]["rect"]


@pytest.mark.parametrize("scenario", _load_contract()["scenarios"], ids=lambda item: item["id"])
def test_picker_placement_uses_work_area_and_does_not_clip(scenario: dict[str, Any]) -> None:
    contract = _load_contract()

    rect, monitor_name, _fallback_used = _place_picker(contract, scenario)
    monitor = next(item for item in scenario["monitors"] if item["name"] == monitor_name)

    assert _taskbar_edge(monitor["monitor_rect"], monitor["work_area"]) == scenario["taskbar_edge"]
    _assert_not_clipped(rect, monitor["work_area"])


def test_picker_placement_fixture_stays_cross_platform_and_model_only() -> None:
    contract = _load_contract()

    assert contract["selection_policy"] == {
        "prefer_tray_anchor": True,
        "cursor_fallback": True,
        "outside_cursor_fallback": "primary_monitor",
    }
    for scenario in contract["scenarios"]:
        assert scenario["anchor"]["source"] in {"tray", "cursor"}
        assert "window_handle" not in scenario["anchor"]
        assert "adapter" not in scenario
