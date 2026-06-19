from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from importlib.resources import files
from typing import Any

from setpiece.e2e import record_event
from setpiece.errors import DependencyMissingError

from .instrument_model import InstrumentModel, InstrumentSources, build_instrument_model
from .window_activation import activate_qml_window, place_qml_window


InstrumentModelProvider = Callable[[], InstrumentModel]
InstrumentActionHandler = Callable[[str, str], None]
InstrumentCollapseHandler = Callable[[str], None]


@dataclass
class FakeInstrumentSurface:
    model_provider: InstrumentModelProvider = build_instrument_model
    on_primary_action: InstrumentActionHandler | None = None
    on_collapse: InstrumentCollapseHandler | None = None
    visible: bool = False
    collapsed: bool = False
    keep_visible: bool = False
    payloads: list[dict[str, object]] = field(default_factory=list)
    primary_actions: list[tuple[str, str]] = field(default_factory=list)
    collapses: list[str] = field(default_factory=list)

    def show(self) -> None:
        self.refresh()
        self.visible = True
        self.collapsed = False

    def hide(self) -> None:
        self.visible = False

    def collapse(self, reason: str = "collapse") -> None:
        self.collapsed = True
        self.collapses.append(reason)
        if self.on_collapse is not None:
            self.on_collapse(reason)

    def toggle(self) -> None:
        if self.visible and not self.collapsed:
            self.collapse("toggle")
        else:
            self.show()

    def close(self) -> None:
        self.collapse("close")

    def refresh(self) -> dict[str, object]:
        payload = instrument_payload_for_qml(self.model_provider())
        self.payloads.append(payload)
        return payload

    def primary_action(self, state: str = "") -> None:
        payload = self.refresh()
        action = str(payload.get("primary_action") or "")
        current_state = state or str(payload.get("state") or "")
        self.primary_actions.append((current_state, action))
        if self.on_primary_action is not None:
            self.on_primary_action(current_state, action)

    def set_keep_visible(self, value: bool) -> None:
        self.keep_visible = bool(value)


class QmlInstrumentSurface:
    def __init__(
        self,
        *,
        model_provider: InstrumentModelProvider = build_instrument_model,
        on_primary_action: InstrumentActionHandler,
        on_collapse: InstrumentCollapseHandler,
    ) -> None:
        self.model_provider = model_provider
        self.on_primary_action = on_primary_action
        self.on_collapse = on_collapse
        self._payload: dict[str, object] = {}
        self._engine: Any | None = None
        self._root: Any | None = None
        self._bridge: Any | None = None

    @property
    def payload(self) -> dict[str, object]:
        if not self._payload:
            self.refresh()
        return dict(self._payload)

    @property
    def visible(self) -> bool:
        root = self._root
        if root is None:
            return False
        return bool(root.isVisible()) if hasattr(root, "isVisible") else bool(root.visible)

    def show(self) -> None:
        self._ensure_loaded()
        self.refresh()
        if hasattr(self._root, "setProperty"):
            self._root.setProperty("collapsed", False)
        if hasattr(self._root, "show"):
            self._root.show()
        place_qml_window(self._root, anchor="right-center", fallback_width=420, fallback_height=520)
        activate_qml_window(self._root)
        _schedule_activation_retries(self._root)
        record_event("agent.instrument.show")

    def hide(self) -> None:
        if self._root is not None and hasattr(self._root, "hide"):
            self._root.hide()
        record_event("agent.instrument.hide")

    def collapse(self, reason: str = "collapse") -> None:
        if self._root is not None and hasattr(self._root, "setProperty"):
            self._root.setProperty("collapsed", True)
        self.on_collapse(reason)
        record_event("agent.instrument.collapse", reason=reason)

    def toggle(self) -> None:
        if self.visible and not self._collapsed:
            self.collapse("toggle")
        else:
            self.show()

    def close(self) -> None:
        self.collapse("close")

    def refresh(self) -> dict[str, object]:
        self._payload = instrument_payload_for_qml(self.model_provider())
        bridge = self._bridge
        if bridge is not None and hasattr(bridge, "payloadChanged"):
            bridge.payloadChanged.emit()
        return dict(self._payload)

    def primary_action(self, state: str) -> None:
        action = str(self.payload.get("primary_action") or "")
        self.on_primary_action(state, action)

    def set_keep_visible(self, value: bool) -> None:
        record_event("agent.instrument.keep_visible", keep_visible=bool(value))

    def _ensure_loaded(self) -> None:
        if self._root is not None:
            return
        qt = _load_instrument_qt()
        self._bridge = _create_bridge(qt, self)
        self._engine = qt.QQmlApplicationEngine()
        self._engine.rootContext().setContextProperty("setpieceInstrumentController", self._bridge)
        qml_path = files("setpiece.agent.qml").joinpath("QuietInstrument.qml")
        self._engine.load(qt.QUrl.fromLocalFile(str(qml_path)))
        roots = self._engine.rootObjects()
        if not roots:
            raise DependencyMissingError("Quiet Instrument QML failed to load")
        self._root = roots[0]

    @property
    def _collapsed(self) -> bool:
        root = self._root
        if root is None:
            return False
        try:
            return bool(root.property("collapsed"))
        except Exception:
            return False


@dataclass(frozen=True)
class _InstrumentQt:
    QObject: Any
    Property: Any
    Signal: Any
    Slot: Any
    QUrl: Any
    QQmlApplicationEngine: Any


def instrument_payload_for_qml(model: InstrumentModel) -> dict[str, object]:
    actions = [action.to_dict() for action in model.actions]
    primary = next((action for action in model.actions if action.role.value == "primary"), None)
    return {
        "schema_version": model.schema_version,
        "state": model.state.value,
        "title": model.headline,
        "summary": model.subheadline or model.intent,
        "ritual_id": model.ritual_id,
        "ritual_name": model.ritual_name,
        "current_step": _current_step_payload(model),
        "steps": _steps_payload(model),
        "actions": actions,
        "primary_action": primary.action if primary else "",
        "primary_action_label": primary.label if primary else "",
        "wait": model.wait.to_dict() if model.wait else None,
        "confirmation": model.confirmation.to_dict() if model.confirmation else None,
        "failure": model.failure.to_dict() if model.failure else None,
        "recovery": model.recovery.to_dict() if model.recovery else None,
        "technical_details": _technical_details(model),
    }


def model_from_agent_state(state: Any) -> InstrumentModel:
    return build_instrument_model(InstrumentSources(agent_state=state))


def _load_instrument_qt() -> _InstrumentQt:
    try:
        from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
        from PySide6.QtQml import QQmlApplicationEngine
    except ImportError as exc:
        raise DependencyMissingError("Quiet Instrument requires PySide6") from exc
    return _InstrumentQt(
        QObject=QObject,
        Property=Property,
        Signal=Signal,
        Slot=Slot,
        QUrl=QUrl,
        QQmlApplicationEngine=QQmlApplicationEngine,
    )


def _create_bridge(qt: _InstrumentQt, surface: QmlInstrumentSurface) -> Any:
    class InstrumentBridge(qt.QObject):  # type: ignore[misc, valid-type]
        payloadChanged = qt.Signal()
        keepVisibleChanged = qt.Signal()

        @qt.Property("QVariant", notify=payloadChanged)
        def payload(self) -> dict[str, object]:
            return surface.payload

        @qt.Slot(str)
        def primaryAction(self, state: str) -> None:
            surface.primary_action(state)

        @qt.Slot(str)
        def collapseInstrument(self, reason: str) -> None:
            surface.collapse(reason)

        @qt.Slot()
        def expandInstrument(self) -> None:
            surface.show()

        @qt.Slot(bool)
        def setKeepVisibleForRitual(self, keep_visible: bool) -> None:
            surface.set_keep_visible(keep_visible)

    return InstrumentBridge()


def _schedule_activation_retries(root: Any) -> None:
    try:
        from PySide6.QtCore import QTimer
    except ImportError:
        return

    for delay_ms in (75, 200):
        QTimer.singleShot(delay_ms, lambda root=root: _activate_if_visible(root))


def _activate_if_visible(root: Any) -> None:
    try:
        if hasattr(root, "isVisible") and not root.isVisible():
            return
        if hasattr(root, "property") and bool(root.property("collapsed")):
            return
    except Exception:
        return
    activate_qml_window(root)


def _current_step_payload(model: InstrumentModel) -> dict[str, object]:
    return {
        "index": model.progress.step_index,
        "title": model.current_verb or model.headline,
        "status": model.state.value,
        "summary": model.next_step,
    }


def _steps_payload(model: InstrumentModel) -> list[dict[str, object]]:
    steps: list[dict[str, object]] = []
    completed = max(0, int(model.progress.completed_steps or 0))
    current_index = model.progress.step_index
    total = max(model.step_count, model.progress.total_steps)
    for index in range(1, total + 1):
        if current_index == index:
            status = model.state.value
            title = model.current_verb or model.headline
        elif index <= completed:
            status = "completed"
            title = f"Step {index}"
        else:
            status = "future"
            title = model.next_step if index == completed + 1 and model.next_step else f"Step {index}"
        steps.append({"index": index, "title": title, "status": status})
    return steps


def _technical_details(model: InstrumentModel) -> dict[str, object]:
    return {
        "facts": [fact.to_dict() for fact in model.facts],
        "details": list(model.details),
        "history": model.history.to_dict(),
    }
