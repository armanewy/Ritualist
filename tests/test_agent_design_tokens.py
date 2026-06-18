from __future__ import annotations

from pathlib import Path

from ritualist.agent.design_tokens import quiet_instrument_tokens, token


REPO_ROOT = Path(__file__).resolve().parents[1]
AGENT_QML = REPO_ROOT / "ritualist" / "agent" / "qml"


def _qml(name: str) -> str:
    return (AGENT_QML / name).read_text(encoding="utf-8")


def test_quiet_instrument_python_tokens_define_unified_shell_contract() -> None:
    tokens = quiet_instrument_tokens()

    assert tokens["contract.id"] == "ritualist.agent.quiet_instrument.v1"
    assert tokens["base.theme"] == "ritualist.paper"
    assert tokens["font.family.primary"] == "Segoe UI Variable"
    assert tokens["font.family.fallback"] == "Segoe UI"
    assert tokens["font.size.minimum_epx"] == 12
    assert tokens["font.case"] == "sentence"

    assert tokens["color.canvas"] == "#f6f2ea"
    assert tokens["color.panel"] == "#ffffff"
    assert tokens["color.accent"] == "#2f6f8f"
    assert tokens["color.semantic.running"] == "#2f6f8f"
    assert tokens["color.semantic.waiting"] == "#8a6a1f"
    assert tokens["color.semantic.confirmation"] == "#2f7d57"
    assert tokens["color.semantic.confirmation_panel"] == "#eaf7ee"
    assert tokens["color.semantic.failure"] == "#a23a3a"
    assert tokens["color.semantic.recovery"] == "#4f6f8f"

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
    assert token("color.panel") == "#ffffff"


def test_qml_tokens_mirror_agent_contract_without_runtime_dependencies() -> None:
    qml = _qml("RitualistTokens.qml")

    for snippet in (
        'readonly property string contractId: "ritualist.agent.quiet_instrument.v1"',
        'readonly property string baseThemeId: "ritualist.paper"',
        'readonly property string fontFamily: "Segoe UI Variable"',
        'readonly property string fallbackFontFamily: "Segoe UI"',
        "readonly property int minFontEpx: 12",
        'readonly property string textCase: "sentence case"',
        'readonly property color canvas: "#f6f2ea"',
        'readonly property color accent: "#2f6f8f"',
        'readonly property color confirmation: "#2f7d57"',
        'readonly property color confirmationPanel: "#eaf7ee"',
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


def test_quiet_qml_controls_expose_accessible_visual_contract() -> None:
    sources = {
        path.name: path.read_text(encoding="utf-8")
        for path in AGENT_QML.iterdir()
        if path.suffix == ".qml"
    }
    combined = "\n".join(sources.values())

    for name in (
        "RitualistTokens.qml",
        "QuietButton.qml",
        "QuietTextField.qml",
        "QuietDivider.qml",
        "QuietStatusIcon.qml",
    ):
        assert name in sources

    for snippet in (
        "property var tokens: RitualistTokens {}",
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


def test_agent_quiet_sources_do_not_add_forbidden_capabilities() -> None:
    combined = "\n".join(
        [
            (REPO_ROOT / "ritualist" / "agent" / "design_tokens.py").read_text(encoding="utf-8"),
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
