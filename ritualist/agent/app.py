from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from ritualist.e2e import record_event
from ritualist.errors import RitualistError

from .activation import ActivationIntent
from .menu_model import MenuAction
from .models import AgentRunState, AgentState
from .picker_controller import PickerIntent, PickerIntentKind
from .picker_model import build_picker_model
from .picker_window import QmlPickerSurface
from .single_instance import ActivationServer, SingleInstanceCoordinator
from .state import initial_agent_state
from .tray import AgentTray, TrayQtTypes, create_agent_tray, load_tray_qt_types
from .windows.hotkey import WindowsGlobalHotkeyAdapter


MenuIntentMap = dict[MenuAction, ActivationIntent]
PickerFactory = Callable[["ResidentAgent"], Any]


@dataclass
class ResidentAgent:
    application: Any
    tray: AgentTray
    activation_server: ActivationServer | None = None
    state: AgentState = field(default_factory=initial_agent_state)
    picker_factory: PickerFactory | None = None
    picker_surface: Any | None = None
    opened_surfaces: list[str] = field(default_factory=list)
    received_intents: list[str] = field(default_factory=list)
    picker_intents: list[dict[str, str]] = field(default_factory=list)
    preflight_requests: list[str] = field(default_factory=list)
    exit_requested: bool = False

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
            self.handle_activation(ActivationIntent("open_active_ritual"))

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
            self.preflight_requests.append(intent.recipe_id)
            self.opened_surfaces.append(f"preflight:{intent.recipe_id}")
        elif intent.kind is PickerIntentKind.OPEN_BUILDER:
            self.opened_surfaces.append("open_builder")
        elif intent.kind is PickerIntentKind.BROWSE_ALL:
            self.opened_surfaces.append("browse_all_rituals")
        elif intent.kind is PickerIntentKind.RETURN_TO_ACTIVE:
            self.opened_surfaces.append("open_active_ritual")

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
