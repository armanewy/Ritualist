from __future__ import annotations

from pathlib import Path

import pytest

from setpiece.agent.design_tokens import quiet_instrument_tokens, token


REPO_ROOT = Path(__file__).resolve().parents[1]
AGENT_QML = REPO_ROOT / "setpiece" / "agent" / "qml"


def _qml(name: str) -> str:
    return (AGENT_QML / name).read_text(encoding="utf-8")


def test_quiet_instrument_python_tokens_define_unified_shell_contract() -> None:
    tokens = quiet_instrument_tokens()

    assert tokens["contract.id"] == "setpiece.agent.quiet_instrument.v1"
    assert tokens["base.theme"] == "setpiece.paper"
    assert tokens["font.family.primary"] == "Segoe UI Variable"
    assert tokens["font.family.fallback"] == "Segoe UI"
    assert tokens["font.size.minimum_epx"] == 12
    assert tokens["font.case"] == "sentence"

    assert tokens["color.canvas"] == "#F7F4EE"
    assert tokens["color.panel"] == "#FFFFFF"
    assert tokens["color.accent"] == "#3C6F82"
    assert tokens["color.semantic.running"] == "#3C6F82"
    assert tokens["color.semantic.waiting"] == "#A36B25"
    assert tokens["color.semantic.confirmation"] == "#6E5A8A"
    assert tokens["color.semantic.confirmation_panel"] == "#DDE7E8"
    assert tokens["color.semantic.paused"] == "#70777C"
    assert tokens["color.semantic.paused_panel"] == "#F7F4EE"
    assert tokens["color.semantic.failure"] == "#A84942"
    assert tokens["color.semantic.recovery"] == "#45715F"

    assert tokens["geometry.base_epx"] == 4
    assert tokens["geometry.space.sm_epx"] == 8
    assert tokens["geometry.space.md_epx"] == 12
    assert tokens["geometry.space.lg_epx"] == 16
    assert tokens["geometry.space.xl_epx"] == 24
    assert tokens["geometry.space.xxl_epx"] == 32
    assert tokens["geometry.radius.outer_epx"] == 10
    assert tokens["geometry.radius.control_epx"] == 6
    assert tokens["geometry.hit_target.primary_epx"] == 40
    assert tokens["geometry.shadow.outer.blur_epx"] == 24

    assert tokens["motion.flyout.min_ms"] == 120
    assert tokens["motion.flyout.max_ms"] == 160
    assert tokens["motion.state.min_ms"] == 180
    assert tokens["motion.state.max_ms"] == 220
    assert tokens["motion.reduced.default_ms"] == 0
    assert tokens["motion.reduced.fade_ms"] == 60
    assert token("color.panel") == "#FFFFFF"


def test_qml_tokens_mirror_agent_contract_without_runtime_dependencies() -> None:
    qml = _qml("SetpieceTokens.qml")

    for snippet in (
        'readonly property string contractId: "setpiece.agent.quiet_instrument.v1"',
        'readonly property string baseThemeId: "setpiece.paper"',
        'readonly property string fontFamily: "Segoe UI Variable"',
        'readonly property string fallbackFontFamily: "Segoe UI"',
        "readonly property int minFontEpx: 12",
        'readonly property string textCase: "sentence case"',
        'readonly property color canvas: "#F7F4EE"',
        'readonly property color accent: "#3C6F82"',
        'readonly property color accentText: "#FFFFFF"',
        'readonly property color confirmation: "#6E5A8A"',
        'readonly property color confirmationPanel: "#DDE7E8"',
        'readonly property color paused: "#70777C"',
        'readonly property color pausedPanel: "#F7F4EE"',
        "readonly property int outerRadiusEpx: 10",
        "readonly property int controlRadiusEpx: 6",
        "readonly property int primaryHitTargetEpx: 40",
        "readonly property int flyoutDurationMinMs: 120",
        "readonly property int flyoutDurationMaxMs: 160",
        "readonly property int stateDurationMinMs: 180",
        "readonly property int stateDurationMaxMs: 220",
        "readonly property int reducedMotionDurationMs: 0",
        "readonly property int reducedMotionFadeMs: 60",
        "function duration(kind, reducedMotion)",
        "function semanticColor(state)",
        "function semanticPanel(state)",
    ):
        assert snippet in qml

    assert "cardShadow" not in qml
    assert "DropShadow" not in qml
    assert "property color onAccent" not in qml


def test_quiet_qml_controls_expose_accessible_visual_contract() -> None:
    sources = {
        path.name: path.read_text(encoding="utf-8")
        for path in AGENT_QML.iterdir()
        if path.suffix == ".qml"
    }
    combined = "\n".join(sources.values())

    for name in (
        "SetpieceTokens.qml",
        "QuietButton.qml",
        "QuietTextField.qml",
        "QuietDivider.qml",
        "QuietStatusIcon.qml",
    ):
        assert name in sources

    for snippet in (
        "property var tokens: SetpieceTokens {}",
        "implicitHeight: tokens.primaryHitTargetEpx",
        "font.family: tokens.fontFamily",
        "font.pixelSize: Math.max(tokens.bodyFontEpx, tokens.minFontEpx)",
        "focusPolicy: Qt.StrongFocus",
        "Accessible.name: text",
        "Accessible.role: Accessible.Button",
        "Accessible.role: Accessible.EditableText",
        "Accessible.role: Accessible.Indicator",
        "radius: control.tokens.controlRadiusEpx",
        'ColorAnimation { duration: control.tokens.duration("state", control.reducedMotion) }',
        'NumberAnimation { duration: field.tokens.duration("fade", field.reducedMotion) }',
        "color: icon.tokens.semanticColor(icon.status)",
    ):
        assert snippet in combined


def test_agent_qml_surfaces_load_with_qt_engine_offscreen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    qt_core = pytest.importorskip("PySide6.QtCore")
    qt_qml = pytest.importorskip("PySide6.QtQml")
    qt_widgets = pytest.importorskip("PySide6.QtWidgets")

    try:
        app = qt_widgets.QApplication.instance() or qt_widgets.QApplication([])
    except Exception as exc:  # pragma: no cover - platform plugin availability varies in CI.
        pytest.skip(f"Qt offscreen application is unavailable: {exc}")

    class PickerBridge(qt_core.QObject):  # type: ignore[misc, valid-type]
        payloadChanged = qt_core.Signal()
        actionBusyChanged = qt_core.Signal()

        @qt_core.Property("QVariant", notify=payloadChanged)
        def payload(self) -> dict[str, object]:
            return {
                "current_room": {"room_id": "gaming", "name": "Gaming Room"},
                "recent_rituals": [
                    {
                        "id": "gaming_mode",
                        "title": "Diablo Night",
                        "room_name": "Gaming Room",
                        "description": "Prepare the desktop for a play session.",
                    }
                ],
                "matching_rituals": [],
                "active_ritual": None,
            }

        @qt_core.Property(bool, notify=actionBusyChanged)
        def actionBusy(self) -> bool:
            return False

        @qt_core.Slot(str)
        def openPreflight(self, recipe_id: str) -> None:
            return None

        @qt_core.Slot()
        def browseAll(self) -> None:
            return None

        @qt_core.Slot()
        def openBuilder(self) -> None:
            return None

        @qt_core.Slot()
        def openActiveRitual(self) -> None:
            return None

    class InstrumentBridge(qt_core.QObject):  # type: ignore[misc, valid-type]
        payloadChanged = qt_core.Signal()
        keepVisibleChanged = qt_core.Signal()

        @qt_core.Property("QVariant", notify=payloadChanged)
        def payload(self) -> dict[str, object]:
            return {
                "title": "Diablo Night",
                "state": "ready",
                "summary": "Prepare the desktop for a play session.",
                "steps": [{"index": 1, "title": "Open Battle.net", "status": "future"}],
                "primary_action": "start",
                "primary_action_label": "Start ritual",
            }

        @qt_core.Slot(str)
        def primaryAction(self, state: str) -> None:
            return None

        @qt_core.Slot(str)
        def collapseInstrument(self, reason: str) -> None:
            return None

        @qt_core.Slot()
        def expandInstrument(self) -> None:
            return None

        @qt_core.Slot(bool)
        def setKeepVisibleForRitual(self, keep_visible: bool) -> None:
            return None

    assert app is not None
    bridges = [PickerBridge(), InstrumentBridge()]
    surfaces = (
        ("Picker.qml", "setpiecePickerController", bridges[0]),
        ("QuietInstrument.qml", "setpieceInstrumentController", bridges[1]),
    )
    failures: list[str] = []
    for qml_name, property_name, bridge in surfaces:
        engine = qt_qml.QQmlApplicationEngine()
        warnings: list[str] = []
        engine.warnings.connect(
            lambda warning_list, warnings=warnings: warnings.extend(
                warning.toString() for warning in warning_list
            )
        )
        engine.rootContext().setContextProperty(property_name, bridge)
        engine.load(qt_core.QUrl.fromLocalFile(str(AGENT_QML / qml_name)))
        if not engine.rootObjects():
            failures.append(f"{qml_name}: {'; '.join(warnings) or 'no root object'}")

    assert failures == []


def test_agent_quiet_sources_do_not_add_forbidden_capabilities() -> None:
    combined = "\n".join(
        [
            (REPO_ROOT / "setpiece" / "agent" / "design_tokens.py").read_text(encoding="utf-8"),
            *[
                path.read_text(encoding="utf-8")
                for path in sorted(AGENT_QML.iterdir())
                if path.suffix == ".qml"
            ],
        ]
    ).casefold()

    for forbidden in (
        "python:",
        "javascript:",
        "shell.execute",
        "shell command",
        "cmd.exe",
        "powershell",
        "subprocess",
        "coordinate",
        "ocr",
        "keylog",
        "recording",
        "macro",
        "cloud",
        "remote",
        "network",
        "marketplace",
        "password",
        "taskbar",
        "kiosk",
        "home.qml",
        "canvasuse.qml",
    ):
        assert forbidden not in combined
