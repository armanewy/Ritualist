from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "picker"
ACCESSIBILITY_FIXTURE = FIXTURE_DIR / "accessibility_contract.json"
PLACEMENT_FIXTURE = FIXTURE_DIR / "placement_contract.json"

INTERNAL_ID_PATTERN = re.compile(
    r"(\b[a-z]+[_-][0-9a-f]{6,}\b|\b[a-z]+(?:[_-][a-z]+){2,}[_-]\d+\b)",
    re.IGNORECASE,
)


def _load_contract() -> dict[str, Any]:
    return json.loads(ACCESSIBILITY_FIXTURE.read_text(encoding="utf-8"))


def test_picker_accessibility_contract_covers_dismissal_focus_and_keyboard_paths() -> None:
    contract = _load_contract()
    flow_by_id = {flow["id"]: flow for flow in contract["keyboard_flows"]}

    assert contract["schema_version"] == "setpiece.picker.accessibility.v1"
    assert contract["surface"]["dismissal_inputs"] == [
        "escape",
        "hotkey_toggle",
        "outside_click",
    ]
    assert contract["surface"]["focus_restoration"] == "previous_foreground_window"
    assert set(flow_by_id) >= {
        "escape_dismisses_and_restores_focus",
        "hotkey_toggles_picker",
        "outside_click_dismisses_and_restores_focus",
        "keyboard_search_select_preflight",
    }

    for flow in flow_by_id.values():
        assert flow["uses_absolute_position"] is False
        if flow["id"] != "outside_click_dismisses_and_restores_focus":
            assert flow["keyboard_only"] is True

    search_flow = flow_by_id["keyboard_search_select_preflight"]
    assert search_flow["inputs"] == ["type:pro", "ArrowDown", "Enter", "Tab", "Enter"]
    assert search_flow["expected"] == [
        "filter_results",
        "select_project_room",
        "show_preflight",
        "confirm_preflight",
    ]


def test_picker_hotkey_toggle_does_not_capture_typed_text() -> None:
    contract = _load_contract()

    assert contract["hotkey"]["sequence"] == "Win+Ctrl+R"
    assert contract["hotkey"]["toggle_behavior"] == ["open_picker", "dismiss_picker"]
    assert contract["hotkey"]["captures_text"] is False


def test_picker_accessible_elements_have_name_role_state_and_no_internal_ids() -> None:
    contract = _load_contract()
    names = []

    for element in contract["elements"]:
        name = element["accessible_name"]
        names.append(name)

        assert name.strip()
        assert element["role"] in {
            "button",
            "dialog",
            "listbox",
            "option",
            "searchbox",
            "status",
        }
        assert element["state"]["visible"] is True
        assert element["state"]["enabled"] is True
        assert element["key"] not in name
        assert INTERNAL_ID_PATTERN.search(name) is None

    assert len(names) == len(set(names))
    assert {"Gaming Room", "Project Room", "Support Desk"} <= set(names)


def test_picker_contract_keeps_picker_as_target_path_without_legacy_home_framing() -> None:
    contract = _load_contract()
    target_path = contract["target_path"]

    assert target_path["entry"] == "Picker"
    assert target_path["legacy_target"] is False
    assert "Home" not in target_path["route"]
    assert target_path["route"] == ["Picker", "Rituals", "Preflight", "Run"]


def test_picker_risky_actions_require_preflight_confirmation_gate() -> None:
    contract = _load_contract()
    policy = contract["risky_action_policy"]

    assert policy["requires_confirmation"] is True
    assert policy["confirmation_surface"] == "preflight"
    assert policy["preview_before_run"] is True
    assert set(policy["allowed_preflight_actions"]) == {
        "assert.file_exists",
        "assert.path_exists",
        "assert.process_running",
        "confirm.user",
    }


def test_picker_fixtures_are_cross_platform_contract_models() -> None:
    contract = _load_contract()
    boundary = contract["runtime_boundary"]

    assert boundary["requires_gui_runtime"] is False
    assert boundary["requires_desktop_session"] is False
    assert boundary["model_fixture_only"] is True
    assert boundary["live_adapter_calls"] == []


def test_picker_fixture_sources_do_not_add_forbidden_capability_markers() -> None:
    fixture_text = "\n".join(
        path.read_text(encoding="utf-8").casefold()
        for path in (ACCESSIBILITY_FIXTURE, PLACEMENT_FIXTURE)
    )
    forbidden_markers = (
        "arbitrary recipe",
        "cloud sync",
        "coordinate click",
        "desktop.click_coordinates",
        "gameplay",
        "keylogging",
        "macro replay",
        "marketplace",
        "password",
        "credential",
        "remote command",
        "screen capture",
        "taskbar hiding",
        "true shell replacement",
        "javascript",
        "powershell",
        "shell.run",
        "python",
        "qml",
        "html",
        "kiosk",
    )

    for marker in forbidden_markers:
        assert marker not in fixture_text
