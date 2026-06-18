from __future__ import annotations

from dataclasses import dataclass

from ritualist.agent.activation import ActivationIntent
from ritualist.agent.app import start_agent
from ritualist.agent.instrument_window import FakeInstrumentSurface
from ritualist.agent.menu_model import MenuAction
from ritualist.agent.models import AgentConfirmation, AgentRunState, AgentState
from ritualist.agent.picker_model import (
    PICKER_MODEL_SCHEMA_VERSION,
    PickerAction,
    PickerModel,
    PickerRitual,
    PickerRoom,
)
from ritualist.agent.picker_window import FakePickerSurface
from ritualist.agent.single_instance import InstanceActivationResult
from ritualist.agent.tray import FakeApplication, FakeSystemTrayIcon, fake_qt_types
from ritualist.agent.windows.hotkey import DEFAULT_HOTKEY, HotkeyEvent, HotkeyRegistrationResult
from ritualist.runtime_models import RunStarted, StepWaiting


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


class FakeHotkeyAdapter:
    def __init__(self) -> None:
        self.registered = False
        self.closed = False
        self.events: list[HotkeyEvent] = []

    def register(self) -> HotkeyRegistrationResult:
        self.registered = True
        return HotkeyRegistrationResult(
            registered=True,
            status="registered",
            hotkey=DEFAULT_HOTKEY,
            message="registered fake hotkey",
        )

    def poll(self):
        if not self.events:
            return None
        return self.events.pop(0)

    def emit(self) -> None:
        self.events.append(HotkeyEvent(hotkey_id=1, hotkey=DEFAULT_HOTKEY))

    def close(self) -> None:
        self.closed = True


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
    surfaces: list[FakePickerSurface] = []

    result = start_agent(
        application=FakeApplication(),
        coordinator=coordinator,
        qt_types=fake_qt_types(),
        picker_factory=lambda agent: _fake_picker(agent, surfaces),
        run_event_loop=False,
    )

    assert coordinator.initial_intents == ["open_picker"]
    assert result.agent is not None
    assert result.agent.opened_surfaces == ["open_picker"]
    assert surfaces[0].visible is True
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
    surfaces: list[FakePickerSurface] = []
    result = start_agent(
        startup=True,
        application=FakeApplication(),
        coordinator=coordinator,
        qt_types=fake_qt_types(),
        picker_factory=lambda agent: _fake_picker(agent, surfaces),
        run_event_loop=False,
    )
    assert result.agent is not None

    result.agent.tray.system_tray_icon.activated.emit(FakeSystemTrayIcon.ActivationReason.Trigger)

    assert result.agent.opened_surfaces == ["open_picker"]
    assert surfaces[0].visible is True

    result.agent.tray.system_tray_icon.activated.emit(FakeSystemTrayIcon.ActivationReason.Trigger)

    assert surfaces[0].visible is False


def test_hotkey_toggles_picker_while_idle() -> None:
    coordinator, _server = _primary_coordinator()
    surfaces: list[FakePickerSurface] = []
    hotkey = FakeHotkeyAdapter()
    result = start_agent(
        startup=True,
        application=FakeApplication(),
        coordinator=coordinator,
        qt_types=fake_qt_types(),
        picker_factory=lambda agent: _fake_picker(agent, surfaces),
        hotkey_adapter=hotkey,
        run_event_loop=False,
    )
    assert result.agent is not None

    hotkey.emit()
    result.agent.hotkey_timer.timeout.emit()

    assert hotkey.registered is True
    assert surfaces[0].visible is True


def test_picker_preflight_request_does_not_start_ritual() -> None:
    coordinator, _server = _primary_coordinator()
    surfaces: list[FakePickerSurface] = []
    instruments: list[FakeInstrumentSurface] = []
    result = start_agent(
        startup=True,
        application=FakeApplication(),
        coordinator=coordinator,
        qt_types=fake_qt_types(),
        picker_factory=lambda agent: _fake_picker(agent, surfaces),
        instrument_factory=lambda agent: _fake_instrument(agent, instruments),
        run_event_loop=False,
    )
    assert result.agent is not None
    result.agent.open_picker(toggle=False)

    surfaces[0].open_preflight("gaming_mode")

    assert result.agent.preflight_requests == ["gaming_mode"]
    assert result.agent.picker_intents == [
        {"kind": "open_preflight", "recipe_id": "gaming_mode", "room_id": ""}
    ]
    assert "run_recipe" not in result.agent.received_intents
    assert surfaces[0].visible is False
    assert instruments[0].visible is True
    assert instruments[0].payloads[-1]["state"] == "ready"
    assert instruments[0].payloads[-1]["primary_action"] == "start_ritual"


def test_instrument_start_uses_injected_runner_and_runtime_events() -> None:
    coordinator, _server = _primary_coordinator()
    surfaces: list[FakePickerSurface] = []
    instruments: list[FakeInstrumentSurface] = []
    started: list[str] = []

    def runtime_runner(recipe_id, callback):
        started.append(recipe_id)
        callback(
            RunStarted(
                run_id="run-1",
                sequence=0,
                recipe_id=recipe_id,
                recipe_name="Gaming Mode",
                steps_total=2,
            )
        )
        callback(
            StepWaiting(
                run_id="run-1",
                sequence=1,
                step_index=1,
                step_name="Wait for launcher",
                action="window.wait",
                reason="waiting for launcher",
                target="Battle.net",
                elapsed_seconds=3,
                timeout_seconds=30,
            )
        )

    result = start_agent(
        startup=True,
        application=FakeApplication(),
        coordinator=coordinator,
        qt_types=fake_qt_types(),
        picker_factory=lambda agent: _fake_picker(agent, surfaces),
        instrument_factory=lambda agent: _fake_instrument(agent, instruments),
        runtime_runner=runtime_runner,
        run_event_loop=False,
    )
    assert result.agent is not None

    result.agent.open_preflight("gaming_mode")
    instruments[0].primary_action("ready")

    assert started == ["gaming_mode"]
    assert result.agent.runtime_events == ["run.started", "step.waiting"]
    assert instruments[0].payloads[-1]["state"] == "waiting"
    assert instruments[0].payloads[-1]["title"] == "Waiting for Battle.net"
    assert "run:gaming_mode" in result.agent.opened_surfaces


def test_preflight_for_second_ritual_returns_to_active_instrument() -> None:
    coordinator, _server = _primary_coordinator()
    instruments: list[FakeInstrumentSurface] = []
    result = start_agent(
        startup=True,
        application=FakeApplication(),
        coordinator=coordinator,
        qt_types=fake_qt_types(),
        instrument_factory=lambda agent: _fake_instrument(agent, instruments),
        run_event_loop=False,
    )
    assert result.agent is not None

    result.agent.open_preflight("gaming_mode")
    result.agent.open_preflight("support_triage_workspace")

    assert result.agent.blocked_start_requests == ["support_triage_workspace"]
    assert result.agent.state.active_ritual_id == "gaming_mode"
    assert "return_to_active:gaming_mode" in result.agent.opened_surfaces


def test_run_recipe_redirect_does_not_start_second_ritual_when_slot_occupied() -> None:
    coordinator, _server = _primary_coordinator()
    started: list[str] = []
    result = start_agent(
        startup=True,
        application=FakeApplication(),
        coordinator=coordinator,
        qt_types=fake_qt_types(),
        instrument_factory=lambda agent: FakeInstrumentSurface(
            model_provider=agent.instrument_surface_model,
            on_primary_action=agent.handle_instrument_primary_action,
            on_collapse=agent.collapse_instrument,
        ),
        runtime_runner=lambda recipe_id, _callback: started.append(recipe_id),
        run_event_loop=False,
    )
    assert result.agent is not None
    result.agent.open_preflight("gaming_mode")

    result.agent.handle_activation(
        ActivationIntent("run_recipe", {"recipe_id": "support_triage_workspace"})
    )

    assert started == []
    assert result.agent.blocked_start_requests == ["support_triage_workspace"]
    assert result.agent.state.active_ritual_id == "gaming_mode"


def test_run_recipe_redirect_does_not_restart_same_active_ritual() -> None:
    coordinator, _server = _primary_coordinator()
    started: list[str] = []
    result = start_agent(
        startup=True,
        application=FakeApplication(),
        coordinator=coordinator,
        qt_types=fake_qt_types(),
        instrument_factory=lambda agent: FakeInstrumentSurface(
            model_provider=agent.instrument_surface_model,
            on_primary_action=agent.handle_instrument_primary_action,
            on_collapse=agent.collapse_instrument,
        ),
        runtime_runner=lambda recipe_id, _callback: started.append(recipe_id),
        run_event_loop=False,
    )
    assert result.agent is not None
    result.agent.open_preflight("gaming_mode")

    result.agent.handle_activation(ActivationIntent("run_recipe", {"recipe_id": "gaming_mode"}))

    assert started == []
    assert result.agent.state.active_ritual_id == "gaming_mode"
    assert "return_to_active:gaming_mode" in result.agent.opened_surfaces


def test_instrument_confirmation_actions_resolve_agent_state_safely() -> None:
    coordinator, _server = _primary_coordinator()
    instruments: list[FakeInstrumentSurface] = []
    result = start_agent(
        startup=True,
        application=FakeApplication(),
        coordinator=coordinator,
        qt_types=fake_qt_types(),
        instrument_factory=lambda agent: _fake_instrument(agent, instruments),
        run_event_loop=False,
    )
    assert result.agent is not None
    result.agent.state = result.agent.run_coordinator._state = _confirmation_state("confirm-1")
    result.agent.open_instrument()

    instruments[0].primary_action("confirmation")

    assert result.agent.state.state == AgentRunState.RUNNING
    assert result.agent.confirmation_decisions == ["allow_once"]

    result.agent.state = result.agent.run_coordinator._state = _confirmation_state("confirm-2")

    result.agent.handle_instrument_primary_action("confirmation", "cancel_confirmation")

    assert result.agent.state.state == AgentRunState.STOPPED
    assert result.agent.confirmation_decisions[-1] == "cancel"


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


def _fake_picker(_agent, surfaces: list[FakePickerSurface]) -> FakePickerSurface:
    surface = FakePickerSurface(model_provider=_picker_model, on_intent=_agent.handle_picker_intent)
    surfaces.append(surface)
    return surface


def _fake_instrument(_agent, surfaces: list[FakeInstrumentSurface]) -> FakeInstrumentSurface:
    surface = FakeInstrumentSurface(
        model_provider=lambda: _agent.instrument_surface_model(),
        on_primary_action=_agent.handle_instrument_primary_action,
        on_collapse=_agent.collapse_instrument,
    )
    surfaces.append(surface)
    return surface


def _picker_model() -> PickerModel:
    room = PickerRoom(room_id="gaming", name="Gaming Room", current=True, ritual_count=1)
    ritual = PickerRitual(
        recipe_id="gaming_mode",
        title="Diablo IV Night",
        subtitle="Review before run",
        description="Prepare a safe local gaming setup.",
        room_name="Gaming Room",
        step_count=3,
        affected_apps_count=2,
        intent_summary="Prepare a safe local gaming setup.",
        readiness_summary="Ready",
        setup_summary="2 setup fields",
    )
    return PickerModel(
        schema_version=PICKER_MODEL_SCHEMA_VERSION,
        search_query="",
        current_room=room,
        last_room=None,
        rooms=(room,),
        recent_rituals=(ritual,),
        matching_rituals=(ritual,),
        selected_ritual=ritual,
        active_ritual=None,
        intent_summary="1 ritual available in Gaming Room",
        available_actions=(PickerAction("open_preflight", "Open preflight"),),
    )


def _confirmation_state(confirmation_id: str) -> AgentState:
    return AgentState(
        state=AgentRunState.CONFIRMATION,
        active_ritual_id="gaming_mode",
        active_ritual_name="Gaming Mode",
        pending_confirmation=AgentConfirmation(
            confirmation_id=confirmation_id,
            step_index=2,
            step_name="Launch Diablo IV",
            action="app.launch",
            prompt="Launch Diablo IV?",
            target="Diablo IV",
            target_type="application",
        ),
    )
