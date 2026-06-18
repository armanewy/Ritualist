from __future__ import annotations

from typing import Iterable

from ritualist.canvas import CanvasComponent, load_bundled_canvas


FIRST_VIEWPORT_WIDTH = 1000
FIRST_VIEWPORT_HEIGHT = 720
SUPPORT_LEDGER_VIEWPORT_HEIGHT = 820


def test_gaming_room_composition_keeps_release_surfaces_in_first_viewport() -> None:
    components = _components("gaming_desktop")

    _assert_first_viewport(
        components,
        (
            "category_dock",
            "diablo_night",
            "run_status",
            "run_controller",
            "recent_activity",
            "diablo_target",
            "local_clock",
        ),
    )
    _assert_no_overlap(
        components,
        (
            "category_dock",
            "diablo_night",
            "run_status",
            "run_controller",
            "recent_activity",
            "diablo_target",
            "local_clock",
        ),
    )
    _assert_useful_heights(components, ("diablo_night", "run_status", "run_controller"))
    assert components["diablo_night"].x < components["diablo_target"].x
    assert components["run_status"].y > components["diablo_night"].y
    assert components["recent_activity"].y > components["run_controller"].y


def test_project_room_composition_keeps_preflight_shortcuts_in_first_viewport() -> None:
    components = _components("project_room")

    _assert_first_viewport(
        components,
        (
            "title",
            "project_clock",
            "categories",
            "coding_mode_card",
            "coding_status",
            "coding_controller",
            "project_folder",
            "editor_shortcut",
            "terminal_shortcut",
            "docs_shortcut",
            "tracker_shortcut",
            "recent_activity",
        ),
    )
    _assert_no_overlap(
        components,
        (
            "title",
            "project_clock",
            "categories",
            "coding_mode_card",
            "coding_status",
            "coding_controller",
            "project_folder",
            "editor_shortcut",
            "terminal_shortcut",
            "docs_shortcut",
            "tracker_shortcut",
            "recent_activity",
        ),
    )
    _assert_useful_heights(
        components,
        ("coding_mode_card", "coding_status", "coding_controller"),
    )
    assert components["coding_mode_card"].x < components["project_folder"].x
    assert components["project_folder"].y == components["editor_shortcut"].y
    assert components["terminal_shortcut"].y == components["docs_shortcut"].y
    assert components["recent_activity"].y > components["coding_status"].y


def test_support_desk_composition_prioritizes_runbooks_and_ledger_in_first_viewport() -> None:
    components = _components("helpdesk_desktop")

    _assert_first_viewport(
        components,
        (
            "title",
            "subtitle",
            "doctor_badge",
            "support_triage_card",
            "diagnostics_card",
            "meeting_audio_card",
            "vpn_repair_card",
            "new_hire_setup_card",
            "run_status",
            "run_controller",
            "recent_runs",
            "evidence_note",
        ),
        max_height=SUPPORT_LEDGER_VIEWPORT_HEIGHT,
    )
    _assert_no_overlap(
        components,
        (
            "title",
            "subtitle",
            "doctor_badge",
            "support_triage_card",
            "diagnostics_card",
            "meeting_audio_card",
            "vpn_repair_card",
            "new_hire_setup_card",
            "run_status",
            "run_controller",
            "recent_runs",
            "evidence_note",
        ),
    )
    _assert_useful_heights(
        components,
        (
            "support_triage_card",
            "diagnostics_card",
            "meeting_audio_card",
            "vpn_repair_card",
            "new_hire_setup_card",
            "doctor_badge",
            "run_status",
            "run_controller",
        ),
    )
    assert components["support_triage_card"].width > components["diagnostics_card"].width
    assert components["support_triage_card"].height > components["diagnostics_card"].height
    assert components["diagnostics_card"].x > components["support_triage_card"].x
    assert components["recent_runs"].y > components["run_controller"].y


def _components(canvas_id: str) -> dict[str, CanvasComponent]:
    canvas = load_bundled_canvas(canvas_id)
    return {component.id: component for component in canvas.components}


def _assert_first_viewport(
    components: dict[str, CanvasComponent],
    component_ids: Iterable[str],
    *,
    max_height: int = FIRST_VIEWPORT_HEIGHT,
) -> None:
    for component_id in component_ids:
        component = components[component_id]
        assert component.x >= 0
        assert component.y >= 0
        assert component.x + component.width <= FIRST_VIEWPORT_WIDTH, component_id
        assert component.y + component.height <= max_height, component_id


def _assert_useful_heights(
    components: dict[str, CanvasComponent],
    component_ids: Iterable[str],
) -> None:
    minimum_by_type = {
        "doctor.badge": 128,
        "ritual.card": 172,
        "ritual.controller": 128,
        "ritual.status": 128,
    }
    for component_id in component_ids:
        component = components[component_id]
        assert component.height >= minimum_by_type[component.type], component_id


def _assert_no_overlap(
    components: dict[str, CanvasComponent],
    component_ids: Iterable[str],
) -> None:
    selected = [components[component_id] for component_id in component_ids]
    for index, first in enumerate(selected):
        for second in selected[index + 1 :]:
            assert not _overlaps(first, second), f"{first.id} overlaps {second.id}"


def _overlaps(first: CanvasComponent, second: CanvasComponent) -> bool:
    return (
        first.x < second.x + second.width
        and first.x + first.width > second.x
        and first.y < second.y + second.height
        and first.y + first.height > second.y
    )
