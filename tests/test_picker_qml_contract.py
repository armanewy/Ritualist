from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PICKER_QML = REPO_ROOT / "setpiece" / "agent" / "qml" / "Picker.qml"
PICKER_ROW_QML = REPO_ROOT / "setpiece" / "agent" / "qml" / "PickerRow.qml"
ACTIVE_SUMMARY_QML = REPO_ROOT / "setpiece" / "agent" / "qml" / "ActiveSummary.qml"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_picker_qml_defines_tray_first_transient_surface_contract() -> None:
    qml = _read(PICKER_QML)

    assert "Window {" in qml
    assert "flags: Qt.Window | Qt.FramelessWindowHint" in qml
    assert "NoActivate" not in qml
    assert "WindowStaysOnTopHint" not in qml
    assert "width: 400" in qml
    assert "maximumHeight: 520" in qml
    assert "minimumWidth: 336" in qml
    assert "property bool compactActions: width < 380" in qml
    assert 'dismissIfIdle("outside")' in qml
    assert 'dismissIfIdle("escape")' in qml
    assert 'dismissIfIdle("hotkey")' in qml
    assert "requestReturnFocusToPriorApp" in qml


def test_picker_qml_surfaces_required_contextual_content() -> None:
    qml = _read(PICKER_QML)

    for snippet in (
        "Search rituals",
        "Current Room",
        "Recent rituals",
        "Browse all rituals",
        "New ritual",
        "Open Builder",
        "ActiveSummary",
        "PickerRow",
        "requestBrowseAllRituals",
        "requestOpenBuilder",
    ):
        assert snippet in qml

    assert "Home.qml" not in qml
    assert "CanvasUse.qml" not in qml
    assert "dashboard" not in qml.casefold()
    assert "sidebar" not in qml.casefold()
    assert "tile" not in qml.casefold()


def test_picker_row_requires_enter_preflight_and_blocks_double_click_start() -> None:
    qml = _read(PICKER_ROW_QML)

    assert "signal preflightRequested(string ritualId)" in qml
    assert "Qt.Key_Return || event.key === Qt.Key_Enter" in qml
    assert "root.preflightRequested(root.ritualId)" in qml
    assert "onDoubleClicked" in qml
    assert "Double-click does not start a ritual." in qml
    assert "runRecipe" not in qml
    assert "run_recipe" not in qml
    assert "startRitual" not in qml


def test_active_summary_is_passive_and_confirmation_aware() -> None:
    qml = _read(ACTIVE_SUMMARY_QML)

    assert "Active ritual" in qml
    assert "pendingConfirmation" in qml
    assert "confirmation" in qml
    assert "signal requestOpenActive()" in qml
    assert "requestPreflight" not in qml
    assert "runRecipe" not in qml


def test_picker_qml_avoids_forbidden_capability_markers() -> None:
    combined = "\n".join(_read(path).casefold() for path in (PICKER_QML, PICKER_ROW_QML, ACTIVE_SUMMARY_QML))

    forbidden = (
        "python",
        "javascript",
        "powershell",
        "shell",
        "coordinate",
        "ocr",
        "keylog",
        "macro",
        "replay",
        "remote",
        "network command",
        "password",
        "credential",
        "kiosk",
        "marketplace",
        "taskbar hiding",
    )
    for marker in forbidden:
        assert marker not in combined
