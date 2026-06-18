from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from ritualist.approvals import ConfirmationDecision
from ritualist.e2e import record_event
from ritualist.errors import RitualistError

from .activation import ActivationIntent
from .confirmation_coordinator import ConfirmationCoordinator
from .instrument_window import QmlInstrumentSurface, model_from_agent_state
from .menu_model import MenuAction
from .models import AgentRunState, AgentState
from .picker_controller import PickerIntent, PickerIntentKind
from .picker_model import build_picker_model
from .picker_window import QmlPickerSurface
from .run_coordinator import AgentRunCoordinator, AgentStartDecision
from .single_instance import ActivationServer, SingleInstanceCoordinator
from .state import initial_agent_state
from .tray import AgentTray, TrayQtTypes, create_agent_tray, load_tray_qt_types
from .windows.hotkey import WindowsGlobalHotkeyAdapter


MenuIntentMap = dict[MenuAction, ActivationIntent]
PickerFactory = Callable[["ResidentAgent"], Any]
InstrumentFactory = Callable[["ResidentAgent"], Any]
RuntimeRunner = Callable[[str, Callable[[Any], None]], Any]


@dataclass
class ResidentAgent:
    application: Any
    tray: AgentTray
    activation_server: ActivationServer | None = None
    state: AgentState = field(default_factory=initial_agent_state)
    run_coordinator: AgentRunCoordinator = field(default_factory=AgentRunCoordinator)
    picker_factory: PickerFactory | None = None
    picker_surface: Any | None = None
    instrument_factory: InstrumentFactory | None = None
    instrument_surface: Any | None = None
    runtime_runner: RuntimeRunner | None = None
    confirmation_coordinator: ConfirmationCoordinator | None = None
    confirmation_decisions: list[str] = field(default_factory=list)
    opened_surfaces: list[str] = field(default_factory=list)
    received_intents: list[str] = field(default_factory=list)
    picker_intents: list[dict[str, str]] = field(default_factory=list)
    preflight_requests: list[str] = field(default_factory=list)
    runtime_events: list[str] = field(default_factory=list)
    blocked_start_requests: list[str] = field(default_factory=list)
    exit_requested: bool = False

    def __post_init__(self) -> None:
        self.run_coordinator = AgentRunCoordinator(self.state)
        self.state = self.run_coordinator.state

    def handle_activation(self, intent: ActivationIntent) -> None:
        self.received_intents.append(intent.intent)
        record_event("agent.activation", intent=intent.intent, parameters=dict(intent.parameters))

        if intent.intent == "exit":
            self.exit()
            return
        if intent.intent == "startup_silent":
            return

        if intent.intent == "open_picker":
            self.open_picker(toggle=False)
            return
        if intent.intent == "open_active_ritual":
            self.open_instrument()
            return
        if intent.intent == "run_recipe":
            recipe_id = intent.parameters.get("recipe_id", "")
            if self.open_preflight(recipe_id):
                self.start_current_ritual()
            return

        self.opened_surfaces.append(intent.intent)

    def handle_menu_action(self, action: MenuAction) -> None:
        if action == MenuAction.EXIT_RITUALIST:
            self.handle_activation(ActivationIntent("exit"))
            return
        if action == MenuAction.OPEN_RITUALIST:
            self.open_picker(toggle=True)
            return
        intent = _intent_for_menu_action(action)
        if intent is not None:
            self.handle_activation(intent)

    def handle_hotkey(self) -> None:
        if self.state.state == AgentRunState.IDLE:
            self.open_picker(toggle=True)
        else:
            self.open_instrument()

    def open_picker(self, *, toggle: bool) -> None:
        picker = self._ensure_picker()
        if toggle:
            picker.toggle()
        else:
            picker.show()
        self.opened_surfaces.append("open_picker")

    def handle_picker_intent(self, intent: PickerIntent) -> None:
        self.picker_intents.append(intent.to_dict())
        record_event("agent.picker.intent", **intent.to_dict())
        if intent.kind is PickerIntentKind.OPEN_PREFLIGHT:
            self.open_preflight(intent.recipe_id)
        elif intent.kind is PickerIntentKind.OPEN_BUILDER:
            self.opened_surfaces.append("open_builder")
        elif intent.kind is PickerIntentKind.BROWSE_ALL:
            self.opened_surfaces.append("browse_all_rituals")
        elif intent.kind is PickerIntentKind.RETURN_TO_ACTIVE:
            self.open_instrument()

    def open_preflight(self, recipe_id: str) -> bool:
        result = self.run_coordinator.request_start(
            recipe_id,
            ritual_name=_ritual_title(recipe_id),
            step_count=_ritual_step_count(recipe_id),
        )
        self.state = result.state
        if result.decision == AgentStartDecision.RETURN_TO_ACTIVE:
            self.opened_surfaces.append(f"return_to_active:{result.active_ritual_id}")
            self.open_instrument()
            return False
        if result.decision == AgentStartDecision.STOP_AND_SWITCH_REQUIRED:
            self.blocked_start_requests.append(recipe_id)
            self.opened_surfaces.append(f"return_to_active:{result.active_ritual_id}")
            self.open_instrument()
            return False
        self.preflight_requests.append(recipe_id)
        self.opened_surfaces.append(f"preflight:{recipe_id}")
        if self.picker_surface is not None and hasattr(self.picker_surface, "hide"):
            self.picker_surface.hide()
        self.open_instrument()
        return True

    def open_instrument(self) -> None:
        instrument = self._ensure_instrument()
        instrument.show()
        self.opened_surfaces.append("open_active_ritual")

    def handle_instrument_primary_action(self, _state: str, action: str) -> None:
        if action == "start_ritual":
            self.start_current_ritual()
        elif action == "check_again":
            self.opened_surfaces.append("check_again")
        elif action in {"open_logs", "details"}:
            self.opened_surfaces.append(action)
        elif action in {"resume_ritual", "leave_restored"}:
            self.opened_surfaces.append(action)
        elif action == "approve_once":
            self.resolve_pending_confirmation(ConfirmationDecision.allow_once())
        elif action == "approve_and_remember":
            self.resolve_pending_confirmation(ConfirmationDecision.always_allow_local())
        elif action in {"cancel_confirmation", "cancel_safely"}:
            self.resolve_pending_confirmation(ConfirmationDecision.cancel())

    def collapse_instrument(self, reason: str) -> None:
        self.state = self.run_coordinator.hide_instrument()
        record_event("agent.instrument.collapsed", reason=reason)

    def start_current_ritual(self) -> bool:
        recipe_id = self.state.active_ritual_id
        if not recipe_id:
            return False
        if self.runtime_runner is None:
            self.opened_surfaces.append("run_waiting_for_worker")
            record_event("agent.runtime.start_deferred", recipe_id=recipe_id)
            return False
        self.opened_surfaces.append(f"run:{recipe_id}")
        self.runtime_runner(recipe_id, self.handle_runtime_event)
        self._refresh_instrument()
        return True

    def handle_runtime_event(self, event: Any) -> None:
        self.state = self.run_coordinator.apply_runtime_event(event)
        self.runtime_events.append(str(getattr(event, "type", "")))
        self._refresh_instrument()

    def instrument_surface_model(self) -> Any:
        return model_from_agent_state(self.state)

    def resolve_pending_confirmation(self, decision: ConfirmationDecision) -> bool:
        coordinator = self.confirmation_coordinator
        if coordinator is not None and coordinator.pending_confirmation is not None:
            resolved = coordinator.resolve_pending(decision)
            if resolved:
                self.state = coordinator.state
                self.run_coordinator._state = self.state
                self.confirmation_decisions.append(decision.value)
                self._refresh_instrument()
            return resolved

        if self.state.pending_confirmation is None:
            return False
        from ritualist.runtime_models import ConfirmationResolved, StepState

        confirmation = self.state.pending_confirmation
        self.state = self.run_coordinator.apply_runtime_event(
            ConfirmationResolved(
                run_id=self.state.run_id or "agent-confirmation",
                sequence=len(self.runtime_events) + 1,
                confirmation_id=confirmation.confirmation_id or "agent-confirmation",
                step_index=confirmation.step_index or 1,
                step_name=confirmation.step_name or "Confirmation",
                action=confirmation.action or "confirm.ask",
                approved=decision.approved,
                state=StepState.RUNNING if decision.approved else StepState.CANCELLED,
                message="approved" if decision.approved else "declined",
            )
        )
        self.confirmation_decisions.append(decision.value)
        self._refresh_instrument()
        return True

    def handle_taskbar_created(self) -> None:
        self.tray.handle_taskbar_created()
        record_event("agent.tray.reregistered", reason="taskbar_created")

    def exit(self) -> None:
        self.exit_requested = True
        hotkey_adapter = getattr(self, "hotkey_adapter", None)
        if hotkey_adapter is not None and hasattr(hotkey_adapter, "close"):
            hotkey_adapter.close()
        if self.activation_server is not None:
            self.activation_server.close()
        self.tray.close()
        self.application.quit()

    def _ensure_picker(self) -> Any:
        if self.picker_surface is None:
            factory = self.picker_factory or _default_picker_factory
            self.picker_surface = factory(self)
        return self.picker_surface

    def _ensure_instrument(self) -> Any:
        if self.instrument_surface is None:
            factory = self.instrument_factory or _default_instrument_factory
            self.instrument_surface = factory(self)
        return self.instrument_surface

    def _refresh_instrument(self) -> None:
        if self.instrument_surface is not None and hasattr(self.instrument_surface, "refresh"):
            self.instrument_surface.refresh()


@dataclass(frozen=True)
class AgentRunResult:
    primary: bool
    redirected: bool
    exit_code: int
    agent: ResidentAgent | None = None


def run_agent(
    *,
    startup: bool = False,
    open_picker: bool = False,
    qt_types: TrayQtTypes | None = None,
    application: Any | None = None,
    coordinator: SingleInstanceCoordinator | None = None,
    picker_factory: PickerFactory | None = None,
    instrument_factory: InstrumentFactory | None = None,
    runtime_runner: RuntimeRunner | None = None,
    hotkey_adapter: Any | None = None,
    run_event_loop: bool = True,
) -> int:
    result = start_agent(
        startup=startup,
        open_picker=open_picker,
        qt_types=qt_types,
        application=application,
        coordinator=coordinator,
        picker_factory=picker_factory,
        instrument_factory=instrument_factory,
        runtime_runner=runtime_runner,
        hotkey_adapter=hotkey_adapter,
        run_event_loop=run_event_loop,
    )
    return result.exit_code


def start_agent(
    *,
    startup: bool = False,
    open_picker: bool = False,
    qt_types: TrayQtTypes | None = None,
    application: Any | None = None,
    coordinator: SingleInstanceCoordinator | None = None,
    picker_factory: PickerFactory | None = None,
    instrument_factory: InstrumentFactory | None = None,
    runtime_runner: RuntimeRunner | None = None,
    hotkey_adapter: Any | None = None,
    run_event_loop: bool = True,
) -> AgentRunResult:
    qt = qt_types or load_tray_qt_types()
    app = application or _ensure_application(qt)
    app.setQuitOnLastWindowClosed(False)

    initial_intent = _initial_intent(startup=startup, open_picker=open_picker)
    state = initial_agent_state()
    holder: dict[str, ResidentAgent] = {}

    def on_activation(intent: ActivationIntent) -> None:
        agent = holder.get("agent")
        if agent is not None:
            agent.handle_activation(intent)

    instance = coordinator or SingleInstanceCoordinator()
    claim = instance.become_primary_or_redirect(initial_intent, on_activation)
    if claim.redirected:
        return AgentRunResult(primary=False, redirected=True, exit_code=0)
    if not claim.is_primary:
        raise RitualistError(claim.error or "Resident Agent could not start.")

    tray = create_agent_tray(
        app,
        lambda action: holder["agent"].handle_menu_action(action),
        qt_types=qt,
    )
    agent = ResidentAgent(
        application=app,
        tray=tray,
        activation_server=claim.server,
        state=state,
        picker_factory=picker_factory,
        instrument_factory=instrument_factory,
        runtime_runner=runtime_runner,
    )
    holder["agent"] = agent

    tray.show()
    _start_hotkey_polling(qt, agent, hotkey_adapter)
    record_event(
        "agent.started",
        startup=startup,
        open_picker=open_picker,
        tray_tooltip=state.tray_tooltip,
    )
    if initial_intent.intent != "startup_silent":
        agent.handle_activation(initial_intent)

    exit_code = int(app.exec()) if run_event_loop else 0
    return AgentRunResult(primary=True, redirected=False, exit_code=exit_code, agent=agent)


def _ensure_application(qt: TrayQtTypes) -> Any:
    instance = getattr(qt.QApplication, "instance", lambda: None)()
    if instance is not None:
        return instance
    return qt.QApplication([])


def _initial_intent(*, startup: bool, open_picker: bool) -> ActivationIntent:
    if startup:
        return ActivationIntent("startup_silent")
    if open_picker:
        return ActivationIntent("open_picker")
    return ActivationIntent("open_picker")


def _intent_for_menu_action(action: MenuAction) -> ActivationIntent | None:
    mapping: MenuIntentMap = {
        MenuAction.OPEN_RITUALIST: ActivationIntent("open_picker"),
        MenuAction.SHOW_ACTIVE_RITUAL: ActivationIntent("open_active_ritual"),
        MenuAction.OPEN_ROOMS: ActivationIntent("open_picker"),
        MenuAction.OPEN_RECENT_RITUALS: ActivationIntent("open_picker"),
        MenuAction.VIEW_RUN_DETAILS: ActivationIntent("open_run_log"),
        MenuAction.OPEN_RUN_LOG: ActivationIntent("open_run_log"),
        MenuAction.OPEN_SETTINGS: ActivationIntent("open_settings"),
    }
    return mapping.get(action)


def _default_picker_factory(agent: ResidentAgent) -> QmlPickerSurface:
    return QmlPickerSurface(
        model_provider=lambda: build_picker_model(active_state=agent.state),
        on_intent=agent.handle_picker_intent,
    )


def _default_instrument_factory(agent: ResidentAgent) -> QmlInstrumentSurface:
    return QmlInstrumentSurface(
        model_provider=agent.instrument_surface_model,
        on_primary_action=agent.handle_instrument_primary_action,
        on_collapse=agent.collapse_instrument,
    )


def _ritual_title(recipe_id: str) -> str:
    model = build_picker_model(selected_ritual_id=recipe_id)
    rituals = (*model.matching_rituals, *model.recent_rituals)
    for ritual in rituals:
        if ritual.recipe_id == recipe_id:
            return ritual.title
    return recipe_id.replace("_", " ").replace("-", " ").title()


def _ritual_step_count(recipe_id: str) -> int:
    model = build_picker_model(selected_ritual_id=recipe_id)
    rituals = (*model.matching_rituals, *model.recent_rituals)
    for ritual in rituals:
        if ritual.recipe_id == recipe_id:
            return ritual.step_count
    return 0


def _start_hotkey_polling(qt: TrayQtTypes, agent: ResidentAgent, hotkey_adapter: Any | None) -> None:
    adapter = hotkey_adapter or WindowsGlobalHotkeyAdapter()
    result = adapter.register()
    record_event("agent.hotkey.register", status=result.status, registered=result.registered)
    if not result.registered:
        return

    timer_type = getattr(qt, "QTimer", None)
    if timer_type is None:
        return
    timer = timer_type()

    def poll_hotkey() -> None:
        if adapter.poll() is not None:
            agent.handle_hotkey()

    timer.timeout.connect(poll_hotkey)
    timer.start(80)
    agent.hotkey_adapter = adapter
    agent.hotkey_timer = timer
