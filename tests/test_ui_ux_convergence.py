from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CONVERGENCE_DOC = REPO_ROOT / "docs" / "UI_UX_CONVERGENCE.md"
CANVAS_QML = REPO_ROOT / "ritualist" / "canvas" / "qml" / "CanvasUse.qml"
HOME_QML = REPO_ROOT / "ritualist" / "home" / "qml" / "Home.qml"


def test_ui_ux_convergence_has_phase_six_without_new_product_scope() -> None:
    text = CONVERGENCE_DOC.read_text(encoding="utf-8")

    for snippet in (
        "## Sixth Milestone",
        "focus-ring contrast",
        "keyboard-visible controls",
        "reduced motion",
        "100 and 300 component performance output",
        "blank-area click-through remains `NEEDS_HUMAN_REVIEW`",
        "separate products or themes",
    ):
        assert snippet in text

    sixth = text[text.index("## Sixth Milestone") :]
    for forbidden in (
        "recording",
        "OCR",
        "arbitrary recipe-supplied",
        "cloud sync",
        "remote execution",
        "marketplace",
        "password automation",
        "gameplay automation",
    ):
        assert forbidden not in sixth


def test_canvas_controls_have_keyboard_focus_and_accessible_names() -> None:
    qml = CANVAS_QML.read_text(encoding="utf-8")

    for snippet in (
        "component PaperButton: Button",
        "focusPolicy: Qt.StrongFocus",
        "Accessible.name: text",
        "Accessible.role: Accessible.Button",
        "component PaperTextField: TextField",
        "Accessible.role: Accessible.EditableText",
        "component PaperComboBox: ComboBox",
        "Accessible.role: Accessible.ComboBox",
        'sequence: "Esc"',
        "root.token(\"focus_ring\"",
    ):
        assert snippet in qml


def test_home_keeps_keyboard_navigation_without_capture_hooks() -> None:
    qml = HOME_QML.read_text(encoding="utf-8")

    for snippet in (
        "focus: true",
        "Keys.onPressed",
        "Qt.Key_Escape",
        "Qt.Key_Left",
        "Qt.Key_Right",
        "Qt.Key_Up",
        "Qt.Key_Down",
    ):
        assert snippet in qml

    forbidden = ("keyboard_logger", "keylogger", "global hook", "recording")
    lowered = qml.casefold()
    assert not any(marker in lowered for marker in forbidden)
