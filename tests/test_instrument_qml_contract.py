from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
AGENT_QML = REPO_ROOT / "ritualist" / "agent" / "qml"
QUIET_INSTRUMENT_QML = AGENT_QML / "QuietInstrument.qml"
STATE_QML = {
    "ready": AGENT_QML / "InstrumentReady.qml",
    "running": AGENT_QML / "InstrumentRunning.qml",
    "waiting": AGENT_QML / "InstrumentWaiting.qml",
    "failure": AGENT_QML / "InstrumentFailure.qml",
    "recovery": AGENT_QML / "InstrumentRecovery.qml",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _combined_qml() -> str:
    paths = [QUIET_INSTRUMENT_QML, *STATE_QML.values()]
    return "\n".join(_read(path) for path in paths)


def test_quiet_instrument_files_exist() -> None:
    assert QUIET_INSTRUMENT_QML.exists()
    for path in STATE_QML.values():
        assert path.exists()


def test_quiet_instrument_is_one_edge_anchored_surface() -> None:
    qml = _read(QUIET_INSTRUMENT_QML)

    assert "Window {" in qml
    assert qml.count("Window {") == 1
    assert "flags: Qt.Tool | Qt.FramelessWindowHint" in qml
    assert "WindowStaysOnTopHint" not in qml
    assert "Popup {" not in qml
    assert "Dialog {" not in qml

    assert "property int defaultWidthEpx: 420" in qml
    assert "property int expandedWidthEpx: 560" in qml
    assert "property real maxWorkAreaRatio: 0.70" in qml
    assert "Math.floor(workAreaWidth * maxWorkAreaRatio)" in qml
    assert "Math.floor(workAreaHeight * maxWorkAreaRatio)" in qml
    assert "Screen.desktopAvailableX + root.workAreaWidth - width - tokens.spaceLg" in qml
    assert "root.collapsed ? root.collapsedWidthEpx : Math.min(root.targetSurfaceWidth, root.maxSurfaceWidth)" in qml


def test_quiet_instrument_collapses_without_closing_runtime() -> None:
    qml = _read(QUIET_INSTRUMENT_QML)

    assert "property bool collapsed: false" in qml
    assert "function collapse(reason)" in qml
    assert "root.collapsed = true" in qml
    assert 'root.collapse("close")' in qml
    assert 'root.collapse("escape")' in qml
    assert "function expand()" in qml
    assert "root.expandRequested()" in qml
    assert "close()" not in qml
    assert "requestStop" not in qml
    assert "stopRitual" not in qml


def test_quiet_instrument_uses_structural_state_components() -> None:
    qml = _read(QUIET_INSTRUMENT_QML)

    assert "Loader {" in qml
    assert "function stateComponentSource()" in qml
    for filename in (
        "InstrumentReady.qml",
        "InstrumentRunning.qml",
        "InstrumentWaiting.qml",
        "InstrumentFailure.qml",
        "InstrumentRecovery.qml",
    ):
        assert filename in qml

    for path in STATE_QML.values():
        source = _read(path)
        assert "property var currentStep" in source
        assert "property var completedSteps" in source
        assert "property var futureSteps" in source
        assert "QuietButton" not in source


def test_quiet_instrument_has_one_primary_action_and_progressive_disclosure() -> None:
    qml = _read(QUIET_INSTRUMENT_QML)

    assert qml.count("QuietButton {") == 1
    assert qml.count('role: "primary"') == 1
    assert "function primaryActionLabel()" in qml
    assert "function invokePrimaryAction()" in qml
    assert "Technical details" in qml
    assert "Hide technical details" in qml
    assert "visible: root.technicalDetailsOpen" in qml
    assert "Accessible.name: \"Raw diagnostics\"" in qml
    assert "Keep visible for this ritual" in qml


def test_running_state_condenses_completed_and_future_steps() -> None:
    qml = _read(STATE_QML["running"])

    assert "Now running" in qml
    assert "model: root.completedSteps" in qml
    assert "model: root.limitedFutureSteps()" in qml
    assert "Layout.preferredHeight: 22" in qml
    assert "opacity: 0.72" in qml
    assert "opacity: 0.62" in qml


def test_each_state_has_distinct_semantic_structure() -> None:
    expected = {
        "ready": ("Ready", "First step"),
        "running": ("Now running", "Completed", "Upcoming"),
        "waiting": ("Confirmation required",),
        "failure": ("Needs attention",),
        "recovery": ("Recovery", "Recovery step"),
    }
    for state, snippets in expected.items():
        qml = _read(STATE_QML[state])
        for snippet in snippets:
            assert snippet in qml


def test_quiet_instrument_avoids_forbidden_capability_markers() -> None:
    combined = _combined_qml().casefold()

    forbidden = (
        "python",
        "javascript",
        "powershell",
        "shell",
        "coordinate",
        "ocr",
        "keylog",
        "screenshot",
        "macro",
        "replay",
        "cloud",
        "remote",
        "network command",
        "marketplace",
        "gameplay",
        "password",
        "credential",
        "taskbar",
        "kiosk",
        "home.qml",
        "canvasuse.qml",
    )
    for marker in forbidden:
        assert marker not in combined
