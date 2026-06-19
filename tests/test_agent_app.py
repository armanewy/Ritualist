from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from setpiece.agent.activation import ActivationIntent
from setpiece.agent.app import start_agent
from setpiece.agent.instrument_window import FakeInstrumentSurface, QmlInstrumentSurface
from setpiece.agent.menu_model import MenuAction
from setpiece.agent.models import AgentConfirmation, AgentRunState, AgentState
from setpiece.agent.picker_model import (
    PICKER_MODEL_SCHEMA_VERSION,
    PickerAction,
    PickerModel,
    PickerRitual,
    PickerRoom,
)
from setpiece.agent.picker_window import FakePickerSurface, QmlPickerSurface
from setpiece.agent.single_instance import InstanceActivationResult
from setpiece.agent.tray import FakeApplication, FakeSystemTrayIcon, fake_qt_types
from setpiece.agent.windows.hotkey import DEFAULT_HOTKEY, HotkeyEvent, HotkeyRegistrationResult
from setpiece.runtime_models import RunStarted, StepWaiting


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
    assert result.agent.tray.system_tray_icon.tooltip == "Setpiece is ready"


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
    result.agent.tray.actions[MenuAction.EXIT_SETPIECE].triggered.emit()

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


def test_tray_left_click_toggles_active_instrument_instead_of_picker() -> None:
    coordinator, _server = _primary_coordinator()
    pickers: list[FakePickerSurface] = []
    instruments: list[FakeInstrumentSurface] = []
    result = start_agent(
        startup=True,
        application=FakeApplication(),
        coordinator=coordinator,
        qt_types=fake_qt_types(),
        picker_factory=lambda agent: _fake_picker(agent, pickers),
        instrument_factory=lambda agent: _fake_instrument(agent, instruments),
        run_event_loop=False,
    )
    assert result.agent is not None

    result.agent.open_preflight("gaming_mode")
    result.agent.tray.system_tray_icon.activated.emit(FakeSystemTrayIcon.ActivationReason.Trigger)

    assert result.agent.opened_surfaces[-1] == "toggle_active_ritual"
    assert pickers == []
    assert instruments[0].visible is True
    assert instruments[0].collapsed is True

    result.agent.tray.system_tray_icon.activated.emit(FakeSystemTrayIcon.ActivationReason.Trigger)

    assert instruments[0].visible is True
    assert instruments[0].collapsed is False


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


def test_hotkey_duplicate_chord_event_is_debounced() -> None:
    coordinator, _server = _primary_coordinator()
    surfaces: list[FakePickerSurface] = []
    hotkey = FakeHotkeyAdapter()
    clock = {"value": 10.0}
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
    result.agent.hotkey_clock = lambda: clock["value"]

    hotkey.emit()
    result.agent.hotkey_timer.timeout.emit()
    hotkey.emit()
    clock["value"] += 0.1
    result.agent.hotkey_timer.timeout.emit()

    assert surfaces[0].visible is True
    assert result.agent.opened_surfaces == ["open_picker"]

    hotkey.emit()
    clock["value"] += 0.4
    result.agent.hotkey_timer.timeout.emit()

    assert surfaces[0].visible is False


def test_qml_instrument_show_expands_collapsed_surface(monkeypatch) -> None:
    class Root:
        def __init__(self) -> None:
            self.properties: dict[str, object] = {"collapsed": True}
            self.shown = False

        def setProperty(self, key: str, value: object) -> None:
            self.properties[key] = value

        def property(self, key: str) -> object:
            return self.properties.get(key)

        def show(self) -> None:
            self.shown = True

    root = Root()
    surface = QmlInstrumentSurface(
        model_provider=lambda: None,  # type: ignore[arg-type, return-value]
        on_primary_action=lambda _state, _action: None,
        on_collapse=lambda _reason: None,
    )
    surface._root = root
    surface._bridge = None
    monkeypatch.setattr(surface, "_ensure_loaded", lambda: None)
    monkeypatch.setattr("setpiece.agent.instrument_window.activate_qml_window", lambda _root: None)
    monkeypatch.setattr(
        "setpiece.agent.instrument_window.instrument_payload_for_qml",
        lambda _model: {"state": "ready"},
    )

    surface.show()

    assert root.properties["collapsed"] is False
    assert root.shown is True


def test_qml_instrument_toggle_reopens_collapsed_visible_surface(monkeypatch) -> None:
    class Root:
        def __init__(self) -> None:
            self.properties: dict[str, object] = {"collapsed": True}
            self.shown = False

        def isVisible(self) -> bool:
            return True

        def setProperty(self, key: str, value: object) -> None:
            self.properties[key] = value

        def property(self, key: str) -> object:
            return self.properties.get(key)

        def show(self) -> None:
            self.shown = True

    root = Root()
    collapse_calls: list[str] = []
    surface = QmlInstrumentSurface(
        model_provider=lambda: None,  # type: ignore[arg-type, return-value]
        on_primary_action=lambda _state, _action: None,
        on_collapse=collapse_calls.append,
    )
    surface._root = root
    surface._bridge = None
    monkeypatch.setattr(surface, "_ensure_loaded", lambda: None)
    monkeypatch.setattr("setpiece.agent.instrument_window.activate_qml_window", lambda _root: None)
    monkeypatch.setattr(
        "setpiece.agent.instrument_window.instrument_payload_for_qml",
        lambda _model: {"state": "ready"},
    )

    surface.toggle()

    assert root.properties["collapsed"] is False
    assert root.shown is True
    assert collapse_calls == []


def test_qml_instrument_toggle_collapses_visible_expanded_surface(monkeypatch) -> None:
    class Root:
        def __init__(self) -> None:
            self.properties: dict[str, object] = {"collapsed": False}

        def isVisible(self) -> bool:
            return True

        def setProperty(self, key: str, value: object) -> None:
            self.properties[key] = value

        def property(self, key: str) -> object:
            return self.properties.get(key)

    root = Root()
    collapse_calls: list[str] = []
    surface = QmlInstrumentSurface(
        model_provider=lambda: None,  # type: ignore[arg-type, return-value]
        on_primary_action=lambda _state, _action: None,
        on_collapse=collapse_calls.append,
    )
    surface._root = root

    surface.toggle()

    assert root.properties["collapsed"] is True
    assert collapse_calls == ["toggle"]


def test_picker_qml_arms_outside_dismissal_after_activation_handoff() -> None:
    qml = Path("setpiece/agent/qml/Picker.qml").read_text(encoding="utf-8")

    assert "property bool outsideDismissArmed: false" in qml
    assert "outsideDismissArmTimer.restart()" in qml
    assert "if (!outsideDismissArmed)" in qml
    assert "interval: 250" in qml


def test_qml_picker_visible_hotkey_toggle_uses_hotkey_dismissal() -> None:
    class Root:
        dismiss_hotkey_calls = 0

        def isVisible(self) -> bool:
            return True

        def dismissFromHotkey(self) -> None:
            self.dismiss_hotkey_calls += 1

    root = Root()
    surface = QmlPickerSurface(on_intent=lambda _intent: None)
    surface._root = root

    surface.toggle()

    assert root.dismiss_hotkey_calls == 1


def test_qml_picker_hotkey_consumes_recent_focus_handoff_dismissal(monkeypatch) -> None:
    class Root:
        shown = False
        hidden = False

        def isVisible(self) -> bool:
            return False

        def show(self) -> None:
            self.shown = True

        def hide(self) -> None:
            self.hidden = True

    root = Root()
    surface = QmlPickerSurface(on_intent=lambda _intent: None)
    surface._root = root
    monkeypatch.setattr(surface, "_ensure_loaded", lambda: None)

    surface.dismiss("outside")
    surface.toggle()

    assert root.hidden is True
    assert root.shown is False


def test_qml_surfaces_schedule_delayed_activation_retries() -> None:
    picker = Path("setpiece/agent/picker_window.py").read_text(encoding="utf-8")
    instrument = Path("setpiece/agent/instrument_window.py").read_text(encoding="utf-8")

    for source in (picker, instrument):
        assert "_schedule_activation_retries(self._root)" in source
        assert "for delay_ms in (75, 200)" in source
        assert "QTimer.singleShot(delay_ms, lambda root=root: _activate_if_visible(root))" in source
        assert "if hasattr(root, \"isVisible\") and not root.isVisible()" in source
    assert "bool(root.property(\"collapsed\"))" in instrument


def test_instrument_activation_retry_skips_collapsed_surface(monkeypatch) -> None:
    from setpiece.agent import instrument_window

    class Root:
        def __init__(self, *, visible: bool, collapsed: bool) -> None:
            self.visible = visible
            self.collapsed = collapsed

        def isVisible(self) -> bool:
            return self.visible

        def property(self, key: str) -> object:
            if key == "collapsed":
                return self.collapsed
            return None

    activations: list[Root] = []
    monkeypatch.setattr(instrument_window, "activate_qml_window", activations.append)

    instrument_window._activate_if_visible(Root(visible=True, collapsed=True))
    instrument_window._activate_if_visible(Root(visible=False, collapsed=False))
    expanded = Root(visible=True, collapsed=False)
    instrument_window._activate_if_visible(expanded)

    assert activations == [expanded]


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
