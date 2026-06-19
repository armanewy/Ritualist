from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

from setpiece.cli import app
from setpiece.errors import DependencyMissingError
from setpiece.home import app as home_app
from setpiece.home import (
    FakeHomeStatusEmitter,
    HomeCardStatus,
    HomeEventBridge,
    HomeRuntimeEvent,
    create_mock_home_model,
)
from setpiece.home.models import HomeCardStatus


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_home_help_works():
    result = CliRunner().invoke(app, ["home", "--help"])

    assert result.exit_code == 0
    assert "Open the experimental Qt Quick Home surface" in result.output


def test_home_mock_command_calls_launcher(monkeypatch):
    calls = []
    monkeypatch.setattr(home_app, "run_home", lambda *, mock: calls.append(mock))

    result = CliRunner().invoke(app, ["home", "--mock"])

    assert result.exit_code == 0
    assert calls == [True]


def test_home_command_loads_installed_recipes_by_default(monkeypatch):
    calls = []
    monkeypatch.setattr(home_app, "run_home", lambda *, mock: calls.append(mock))

    result = CliRunner().invoke(app, ["home"])

    assert result.exit_code == 0
    assert calls == [False]


def test_home_dependency_error_preserves_gui_extra(monkeypatch):
    def missing_home(*, mock: bool) -> None:
        raise DependencyMissingError("Home requires PySide6; install setpiece[gui]")

    monkeypatch.setattr(home_app, "run_home", missing_home)

    result = CliRunner().invoke(app, ["home", "--mock"])

    assert result.exit_code == 1
    assert "setpiece[gui]" in result.output


def test_home_doctor_incompatible_maps_to_failed_card_status():
    assert home_app._doctor_status("compatible") is HomeCardStatus.SUCCESS
    assert home_app._doctor_status("compatible_with_warnings") is HomeCardStatus.WARNING
    assert home_app._doctor_status("incompatible") is HomeCardStatus.FAILED


def test_home_qml_has_stop_control_and_modal_confirmation_blocker():
    qml = (Path(__file__).resolve().parents[1] / "setpiece" / "home" / "qml" / "Home.qml").read_text(
        encoding="utf-8"
    )

    assert "visibility: Window.Windowed" in qml
    assert "Window.FullScreen" not in qml
    assert "FramelessWindowHint" not in qml
    assert 'property var promotedRoomIds: ["gaming", "project", "support_desk"]' in qml
    assert "model: roomModel" in qml
    assert qml.count("Open on Desktop") == 1
    assert qml.count("Open in Window") == 1
    assert 'root.openRoom(model.id, "desktop-work-area")' in qml
    assert 'root.openRoom(model.id, "windowed")' in qml
    assert "Classic GUI" in qml
    assert "openClassicGui" in qml
    assert "Recipe Library" in qml
    assert "Minimal Room" not in qml
    assert "Focus Room" not in qml
    assert "Coding Room" not in qml
    assert "Media Room" not in qml
    assert "stopCurrentRun" in qml
    assert "pauseCurrentRun" in qml
    assert "resumeCurrentRun" in qml
    assert "closeKeepOpenBrowser" in qml
    assert "Close Browser" in qml
    assert "property bool runtimeActive" in qml
    assert "cellHeight: 382" in qml
    assert "confirmationModalBlocker" in qml
    assert "detailPanel" in qml
    assert "openCardDetails" in qml
    assert "root.confirmationPending" in qml
    assert "root.confirmationPending && root.inlineConfirmationVisible" in qml
    assert "maximumLineCount: 7" in qml
    assert "firstCategoryWithCards" in qml
    assert "Number(categoryModel.get(nextCategory).count || 0) === 0" in qml
    assert "Recent activity" in qml
    assert "detailSubtitleText" in qml
    assert "detailLastRunText" in qml
    assert "last_run_message" in qml
    assert "Last run:" in qml
    assert "statusDwellTimer" in qml
    assert "Math.max(100, root.minStatusDwellMs)" in qml


def test_home_rooms_payload_exposes_exactly_three_promoted_rooms() -> None:
    payload = home_app._rooms_payload()

    assert [room["id"] for room in payload["rooms"]] == [
        "gaming",
        "project",
        "support_desk",
    ]
    assert [room["name"] for room in payload["rooms"]] == [
        "Gaming Room",
        "Project Room",
        "Support Desk",
    ]
    assert "minimal_desktop" not in {room["canvas_id"] for room in payload["rooms"]}


def test_home_room_launch_command_uses_packaged_room_arguments(monkeypatch) -> None:
    monkeypatch.setattr(home_app.sys, "executable", "Setpiece.exe")
    monkeypatch.setattr(home_app.sys, "frozen", True, raising=False)

    command, args, room = home_app._room_launch_command("gaming", "desktop-work-area")

    assert command == "Setpiece.exe"
    assert args == [
        "--room",
        "gaming",
        "--host",
        "desktop-work-area",
        "--taskbar-policy",
        "respect",
    ]
    assert room.canvas_id == "gaming_desktop"


def test_home_room_launch_command_uses_source_canvas_cli(monkeypatch) -> None:
    monkeypatch.setattr(home_app.sys, "executable", sys.executable)
    monkeypatch.setattr(home_app.sys, "frozen", False, raising=False)

    command, args, room = home_app._room_launch_command("support_desk", "windowed")

    assert command == sys.executable
    assert args == [
        "-m",
        "setpiece",
        "canvas",
        "use",
        "helpdesk_desktop",
        "--host",
        "windowed",
        "--taskbar-policy",
        "respect",
    ]
    assert room.name == "Support Desk"


def test_home_classic_gui_launch_command_keeps_source_and_packaged_paths(monkeypatch) -> None:
    monkeypatch.setattr(home_app.sys, "executable", "Setpiece.exe")
    monkeypatch.setattr(home_app.sys, "frozen", True, raising=False)
    assert home_app._classic_gui_launch_command() == ("Setpiece.exe", ["--classic-gui"])

    monkeypatch.setattr(home_app.sys, "executable", sys.executable)
    monkeypatch.setattr(home_app.sys, "frozen", False, raising=False)
    assert home_app._classic_gui_launch_command() == (sys.executable, ["-m", "setpiece", "gui"])


def test_home_runtime_control_is_active_before_action_state_signal():
    source = (Path(__file__).resolve().parents[1] / "setpiece" / "home" / "app.py").read_text(
        encoding="utf-8"
    )
    start = source.index("def _start_runtime_action")
    body = source[start : source.index("def _start_action", start)]

    assert body.index("self._runtime_control = RuntimeControl()") < body.index(
        "self._set_action_busy(True)"
    )




def test_home_confirmation_wait_refreshes_run_logger_heartbeat():
    source = (Path(__file__).resolve().parents[1] / "setpiece" / "home" / "app.py").read_text(
        encoding="utf-8"
    )
    assert "def _heartbeat_home_confirmation" in source
    assert 'record_run_state("confirming", event="confirmation.waiting"' in source


def test_home_uses_native_confirmation_presenter_when_available():
    source = (Path(__file__).resolve().parents[1] / "setpiece" / "home" / "app.py").read_text(
        encoding="utf-8"
    )
    assert "app = QApplication.instance() or QApplication(sys.argv)" in source
    assert "confirmation_presenter = None if mock else _create_confirmation_presenter()" in source
    assert "self._inline_confirmation_visible = _should_show_inline_confirmation(" in source
    assert "self._confirmation_presenter.request_confirmation(" in source
    assert "create_qt_confirmation_presenter" in source
    assert "create_win32_confirmation_presenter" in source
    assert "return create_win32_confirmation_presenter()" in source
    assert "confirmationDecision = Signal(bool)" in source
    assert "on_decision=self.confirmationDecision.emit" in source


def test_home_confirmation_presenter_uses_win32_fallback_when_qt_factory_fails(monkeypatch):
    from setpiece.home import confirmation as home_confirmation

    fallback = object()

    def fail_qt() -> object:
        raise RuntimeError("qt dialog unavailable")

    monkeypatch.setattr(home_app.sys, "platform", "win32")
    monkeypatch.setattr(home_confirmation, "create_qt_confirmation_presenter", fail_qt)
    monkeypatch.setattr(
        home_confirmation,
        "create_win32_confirmation_presenter",
        lambda: fallback,
    )

    assert home_app._create_confirmation_presenter() is fallback


def test_home_inline_confirmation_visibility_depends_on_presenter():
    assert home_app._should_show_inline_confirmation(None) is True
    assert home_app._should_show_inline_confirmation(object()) is False


def test_home_command_import_does_not_load_pyside6():
    repo_root = Path(__file__).resolve().parents[1]
    code = """
import sys
from setpiece.cli import app

loaded = [name for name in sys.modules if name == "PySide6" or name.startswith("PySide6.")]
if loaded:
    raise SystemExit(f"CLI import loaded PySide6 modules: {loaded}")
"""

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_fake_events_are_coalesced_to_latest_status():
    clock = FakeClock()
    model = create_mock_home_model()
    bridge = HomeEventBridge(model, target_hz=10, clock=clock)

    first = HomeRuntimeEvent(
        card_id="gaming-001",
        status=HomeCardStatus.RUNNING,
        subtitle="first status",
    )
    latest = HomeRuntimeEvent(
        card_id="gaming-001",
        status=HomeCardStatus.WARNING,
        subtitle="latest status",
    )

    bridge.queue_runtime_event(first)
    bridge.queue_runtime_event(latest)

    assert bridge.apply_due() == []
    clock.advance(bridge.interval_seconds)

    applied = bridge.apply_due()
    card = model.get_card("gaming-001")

    assert applied == [latest]
    assert card.status is HomeCardStatus.WARNING
    assert card.subtitle == "latest status"
    assert bridge.applied_count == 1


def test_home_event_bridge_coalesces_repeated_heartbeat_style_updates():
    clock = FakeClock()
    model = create_mock_home_model()
    bridge = HomeEventBridge(model, target_hz=30, clock=clock)

    for index in range(20):
        bridge.queue_runtime_event(
            HomeRuntimeEvent(
                card_id="gaming-001",
                status=HomeCardStatus.RUNNING,
                subtitle=f"heartbeat {index}",
            )
        )

    clock.advance(bridge.interval_seconds)
    applied = bridge.apply_due()

    assert len(applied) == 1
    assert model.get_card("gaming-001").subtitle == "heartbeat 19"


def test_home_runtime_flush_policy_only_flushes_important_events():
    assert (
        home_app._should_flush_home_event(
            HomeRuntimeEvent(
                card_id="gaming-001",
                status=HomeCardStatus.RUNNING,
                subtitle="Run state: running",
            )
        )
        is False
    )
    assert (
        home_app._should_flush_home_event(
            HomeRuntimeEvent(
                card_id="gaming-001",
                status=HomeCardStatus.WARNING,
                subtitle="Confirmation required",
            )
        )
        is True
    )
    assert (
        home_app._should_flush_home_event(
            HomeRuntimeEvent(
                card_id="gaming-001",
                status=HomeCardStatus.RUNNING,
                subtitle="Starting...",
            )
        )
        is True
    )
    assert (
        home_app._should_flush_home_event(
            HomeRuntimeEvent(
                card_id="gaming-001",
                last_run_status="success",
            )
        )
        is True
    )


def test_fake_emitter_updates_model_through_bridge():
    clock = FakeClock()
    model = create_mock_home_model()
    bridge = HomeEventBridge(model, target_hz=30, clock=clock)
    emitter = FakeHomeStatusEmitter(
        bridge.queue_runtime_event,
        card_ids=["gaming-001"],
        interval_seconds=0.01,
    )

    first = emitter.emit_tick()
    second = emitter.emit_tick()
    clock.advance(bridge.interval_seconds)
    applied = bridge.apply_due()
    card = model.get_card("gaming-001")

    assert first.status is HomeCardStatus.RUNNING
    assert second.status is HomeCardStatus.WARNING
    assert applied == [second]
    assert card.status is HomeCardStatus.WARNING
    assert card.description == "Mock Home event 2"


def test_home_import_does_not_load_runtime_automation():
    repo_root = Path(__file__).resolve().parents[1]
    code = """
import sys
import setpiece.home.app
import setpiece.home.fake_events
import setpiece.home.models

blocked = [
    name for name in sys.modules
    if name == "PySide6"
    or name.startswith("PySide6.")
    or name == "setpiece.executor"
    or name == "setpiece.adapters.windows_uia"
    or name == "setpiece.adapters.browser_playwright"
]
if blocked:
    raise SystemExit(f"Home import loaded blocked modules: {blocked}")
"""

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
