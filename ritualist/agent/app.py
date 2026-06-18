from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ritualist.e2e import record_event
from ritualist.errors import RitualistError

from .activation import ActivationIntent
from .menu_model import MenuAction
from .single_instance import ActivationServer, SingleInstanceCoordinator
from .state import initial_agent_state
from .tray import AgentTray, TrayQtTypes, create_agent_tray, load_tray_qt_types


MenuIntentMap = dict[MenuAction, ActivationIntent]


@dataclass
class ResidentAgent:
    application: Any
    tray: AgentTray
    activation_server: ActivationServer | None = None
    opened_surfaces: list[str] = field(default_factory=list)
    received_intents: list[str] = field(default_factory=list)
    exit_requested: bool = False

    def handle_activation(self, intent: ActivationIntent) -> None:
        self.received_intents.append(intent.intent)
        record_event("agent.activation", intent=intent.intent, parameters=dict(intent.parameters))

        if intent.intent == "exit":
            self.exit()
            return
        if intent.intent == "startup_silent":
            return

        self.opened_surfaces.append(intent.intent)

    def handle_menu_action(self, action: MenuAction) -> None:
        if action == MenuAction.EXIT_RITUALIST:
            self.handle_activation(ActivationIntent("exit"))
            return
        intent = _intent_for_menu_action(action)
        if intent is not None:
            self.handle_activation(intent)

    def handle_taskbar_created(self) -> None:
        self.tray.handle_taskbar_created()
        record_event("agent.tray.reregistered", reason="taskbar_created")

    def exit(self) -> None:
        self.exit_requested = True
        if self.activation_server is not None:
            self.activation_server.close()
        self.tray.close()
        self.application.quit()


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
    run_event_loop: bool = True,
) -> int:
    result = start_agent(
        startup=startup,
        open_picker=open_picker,
        qt_types=qt_types,
        application=application,
        coordinator=coordinator,
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
    agent = ResidentAgent(application=app, tray=tray, activation_server=claim.server)
    holder["agent"] = agent

    tray.show()
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
