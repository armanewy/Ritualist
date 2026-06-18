from __future__ import annotations

from dataclasses import dataclass

from ritualist.agent.activation import ActivationIntent
from ritualist.agent.app import start_agent
from ritualist.agent.menu_model import MenuAction
from ritualist.agent.single_instance import InstanceActivationResult
from ritualist.agent.tray import FakeApplication, FakeSystemTrayIcon, fake_qt_types


@dataclass
class FakeActivationServer:
    closed: bool = False

    def close(self) -> None:
        self.closed = True


class FakeCoordinator:
    def __init__(self, result: InstanceActivationResult) -> None:
        self.result = result
        self.initial_intents: list[str] = []
        self.on_activation = None

    def become_primary_or_redirect(self, initial_intent, on_activation):
        self.initial_intents.append(initial_intent.intent)
        self.on_activation = on_activation
        return self.result


def _primary_coordinator() -> tuple[FakeCoordinator, FakeActivationServer]:
    server = FakeActivationServer()
    coordinator = FakeCoordinator(
        InstanceActivationResult(is_primary=True, redirected=False, server=server)
    )
    return coordinator, server


def test_startup_agent_is_tray_resident_without_opening_surface() -> None:
    coordinator, _server = _primary_coordinator()
    app = FakeApplication()

    result = start_agent(
        startup=True,
        application=app,
        coordinator=coordinator,
        qt_types=fake_qt_types(),
        run_event_loop=False,
    )

    assert result.primary is True
    assert result.redirected is False
    assert result.agent is not None
    assert coordinator.initial_intents == ["startup_silent"]
    assert result.agent.opened_surfaces == []
    assert app.quit_on_last_window_closed is False
    assert result.agent.tray.system_tray_icon.visible is True
    assert result.agent.tray.system_tray_icon.tooltip == "Ritualist - Ready"


def test_manual_agent_launch_requests_picker_without_running_ritual() -> None:
    coordinator, _server = _primary_coordinator()

    result = start_agent(
        application=FakeApplication(),
        coordinator=coordinator,
        qt_types=fake_qt_types(),
        run_event_loop=False,
    )

    assert coordinator.initial_intents == ["open_picker"]
    assert result.agent is not None
    assert result.agent.opened_surfaces == ["open_picker"]
    assert result.agent.exit_requested is False


def test_second_agent_process_redirects_and_exits() -> None:
    coordinator = FakeCoordinator(
        InstanceActivationResult(is_primary=False, redirected=True, server=None)
    )

    result = start_agent(
        open_picker=True,
        application=FakeApplication(),
        coordinator=coordinator,
        qt_types=fake_qt_types(),
        run_event_loop=False,
    )

    assert result.primary is False
    assert result.redirected is True
    assert result.exit_code == 0
    assert result.agent is None
    assert coordinator.initial_intents == ["open_picker"]


def test_tray_menu_dispatches_settings_and_explicit_exit() -> None:
    coordinator, server = _primary_coordinator()
    app = FakeApplication()
    result = start_agent(
        startup=True,
        application=app,
        coordinator=coordinator,
        qt_types=fake_qt_types(),
        run_event_loop=False,
    )
    assert result.agent is not None

    result.agent.tray.actions[MenuAction.OPEN_SETTINGS].triggered.emit()
    result.agent.tray.actions[MenuAction.EXIT_RITUALIST].triggered.emit()

    assert result.agent.opened_surfaces == ["open_settings"]
    assert result.agent.received_intents[-1] == "exit"
    assert result.agent.exit_requested is True
    assert server.closed is True
    assert app.quit_called is True
    assert result.agent.tray.system_tray_icon.visible is False


def test_tray_left_click_routes_to_picker() -> None:
    coordinator, _server = _primary_coordinator()
    result = start_agent(
        startup=True,
        application=FakeApplication(),
        coordinator=coordinator,
        qt_types=fake_qt_types(),
        run_event_loop=False,
    )
    assert result.agent is not None

    result.agent.tray.system_tray_icon.activated.emit(FakeSystemTrayIcon.ActivationReason.Trigger)

    assert result.agent.opened_surfaces == ["open_picker"]


def test_taskbar_created_reregisters_visible_tray_icon() -> None:
    coordinator, _server = _primary_coordinator()
    result = start_agent(
        startup=True,
        application=FakeApplication(),
        coordinator=coordinator,
        qt_types=fake_qt_types(),
        run_event_loop=False,
    )
    assert result.agent is not None
    before = result.agent.tray.system_tray_icon.show_calls

    result.agent.handle_taskbar_created()

    assert result.agent.tray.received_taskbar_created is True
    assert result.agent.tray.system_tray_icon.show_calls == before + 1


def test_redirected_activation_is_handled_by_primary_agent() -> None:
    coordinator, _server = _primary_coordinator()
    result = start_agent(
        startup=True,
        application=FakeApplication(),
        coordinator=coordinator,
        qt_types=fake_qt_types(),
        run_event_loop=False,
    )
    assert result.agent is not None
    assert coordinator.on_activation is not None

    coordinator.on_activation(ActivationIntent("open_run_log"))

    assert result.agent.received_intents == ["open_run_log"]
    assert result.agent.opened_surfaces == ["open_run_log"]
