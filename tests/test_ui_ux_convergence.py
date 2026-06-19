from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CONVERGENCE_DOC = REPO_ROOT / "docs" / "UI_UX_CONVERGENCE.md"
CANVAS_QML = REPO_ROOT / "setpiece" / "canvas" / "qml" / "CanvasUse.qml"
CANVAS_QML_DIR = REPO_ROOT / "setpiece" / "canvas" / "qml"
HOME_QML = REPO_ROOT / "setpiece" / "home" / "qml" / "Home.qml"


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
    control_sources = "\n".join(
        (CANVAS_QML_DIR / name).read_text(encoding="utf-8")
        for name in (
            "CanvasPaperButton.qml",
            "CanvasPaperTextField.qml",
            "CanvasPaperComboBox.qml",
        )
    )

    for snippet in (
        "component PaperButton: CanvasPaperButton",
        "component PaperTextField: CanvasPaperTextField",
        "component PaperComboBox: CanvasPaperComboBox",
        "themeRoot: root",
        'sequence: "Esc"',
    ):
        assert snippet in qml

    for snippet in (
        "Button {",
        "focusPolicy: Qt.StrongFocus",
        "Accessible.name: text",
        "Accessible.role: Accessible.Button",
        "TextField {",
        "Accessible.role: Accessible.EditableText",
        "ComboBox {",
        "Accessible.role: Accessible.ComboBox",
        'themeRoot.token("focus_ring"',
    ):
        assert snippet in control_sources


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


def test_home_keeps_rooms_primary_and_privacy_settings_disclosed() -> None:
    qml = HOME_QML.read_text(encoding="utf-8")

    for snippet in (
        "property bool privacyPanelExpanded: false",
        "function learningDetailsVisible()",
        "return privacyPanelExpanded || firstRunLearningChoiceVisible()",
        'text: root.privacyPanelExpanded ? "Hide Settings" : "Privacy Settings"',
        "Accessible.name: root.privacyPanelExpanded ? \"Hide privacy settings\" : \"Show privacy settings\"",
        "Accessible.role: Accessible.Button",
        "activeFocusOnTab: true",
        "Keys.onPressed: (event) =>",
        "root.togglePrivacyPanel()",
        "visible: root.learningDetailsVisible()",
        "Secondary recipe surface",
        "Secondary surface - ",
    ):
        assert snippet in qml
