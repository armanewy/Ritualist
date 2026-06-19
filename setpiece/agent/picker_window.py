from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from importlib.resources import files
from typing import Any

from setpiece.e2e import record_event
from setpiece.errors import DependencyMissingError

from .picker_controller import PickerController, PickerIntent, PickerIntentKind
from .picker_model import PickerModel, build_picker_model
from .window_activation import activate_qml_window, place_qml_window


PickerModelProvider = Callable[[], PickerModel]
PickerIntentHandler = Callable[[PickerIntent], None]


@dataclass
class FakePickerSurface:
    model_provider: PickerModelProvider = build_picker_model
    on_intent: PickerIntentHandler | None = None
    visible: bool = False
    payloads: list[dict[str, object]] = field(default_factory=list)
    intents: list[PickerIntent] = field(default_factory=list)
    dismissals: list[str] = field(default_factory=list)
    focus_returned: bool = False

    def show(self) -> None:
        self.refresh()
        self.visible = True

    def hide(self) -> None:
        self.visible = False

    def toggle(self) -> None:
        if self.visible:
            self.hide()
        else:
            self.show()

    def close(self) -> None:
        self.hide()

    def refresh(self) -> dict[str, object]:
        payload = self.model_provider().to_dict()
        self.payloads.append(payload)
        return payload

    def open_preflight(self, recipe_id: str) -> PickerIntent:
        return self._emit(PickerIntent(PickerIntentKind.OPEN_PREFLIGHT, recipe_id=recipe_id))

    def browse_all(self) -> PickerIntent:
        return self._emit(PickerIntent(PickerIntentKind.BROWSE_ALL))

    def open_builder(self) -> PickerIntent:
        return self._emit(PickerIntent(PickerIntentKind.OPEN_BUILDER))

    def open_active_ritual(self) -> PickerIntent:
        model = self.model_provider()
        if model.active_ritual is None:
            raise ValueError("no active ritual to return to")
        return self._emit(
            PickerIntent(
                PickerIntentKind.RETURN_TO_ACTIVE,
                recipe_id=model.active_ritual.recipe_id,
            )
        )

    def dismiss(self, reason: str) -> None:
        self.dismissals.append(reason)
        self.hide()

    def return_focus_to_prior_app(self) -> None:
        self.focus_returned = True

    def _emit(self, intent: PickerIntent) -> PickerIntent:
        self.intents.append(intent)
        if self.on_intent is not None:
            self.on_intent(intent)
        return intent


class QmlPickerSurface:
    def __init__(
        self,
        *,
        model_provider: PickerModelProvider = build_picker_model,
        on_intent: PickerIntentHandler,
    ) -> None:
        self.model_provider = model_provider
        self.on_intent = on_intent
        self._payload: dict[str, object] = {}
        self._model: PickerModel | None = None
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
        if hasattr(self._root, "show"):
            self._root.show()
        place_qml_window(self._root, anchor="bottom-right", fallback_width=400, fallback_height=520)
        activate_qml_window(self._root)
        record_event("agent.picker.show")

    def hide(self) -> None:
        if self._root is not None and hasattr(self._root, "hide"):
            self._root.hide()
        record_event("agent.picker.hide")

    def toggle(self) -> None:
        if self.visible:
            self.hide()
        else:
            self.show()

    def close(self) -> None:
        self.hide()

    def refresh(self) -> dict[str, object]:
        self._model = self.model_provider()
        self._payload = self._model.to_dict()
        bridge = self._bridge
        if bridge is not None and hasattr(bridge, "payloadChanged"):
            bridge.payloadChanged.emit()
        return dict(self._payload)

    def open_preflight(self, recipe_id: str) -> PickerIntent:
        controller = PickerController(self._model or self.model_provider())
        intent = controller.open_preflight(recipe_id)
        self.on_intent(intent)
        return intent

    def browse_all(self) -> PickerIntent:
        intent = PickerIntent(PickerIntentKind.BROWSE_ALL)
        self.on_intent(intent)
        return intent

    def open_builder(self) -> PickerIntent:
        intent = PickerIntent(PickerIntentKind.OPEN_BUILDER)
        self.on_intent(intent)
        return intent

    def open_active_ritual(self) -> PickerIntent:
        controller = PickerController(self._model or self.model_provider())
        intent = controller.return_to_active()
        self.on_intent(intent)
        return intent

    def dismiss(self, reason: str) -> None:
        record_event("agent.picker.dismiss", reason=reason)
        self.hide()

    def return_focus_to_prior_app(self) -> None:
        record_event("agent.picker.return_focus")

    def _ensure_loaded(self) -> None:
        if self._root is not None:
            return
        qt = _load_picker_qt()
        self._bridge = _create_bridge(qt, self)
        self._engine = qt.QQmlApplicationEngine()
        self._engine.rootContext().setContextProperty("setpiecePickerController", self._bridge)
        qml_path = files("setpiece.agent.qml").joinpath("Picker.qml")
        self._engine.load(qt.QUrl.fromLocalFile(str(qml_path)))
        roots = self._engine.rootObjects()
        if not roots:
            raise DependencyMissingError("Picker QML failed to load")
        self._root = roots[0]
        _connect_if_present(self._root, "requestDismiss", self.dismiss)
        _connect_if_present(self._root, "requestReturnFocusToPriorApp", self.return_focus_to_prior_app)


@dataclass(frozen=True)
class _PickerQt:
    QObject: Any
    Property: Any
    Signal: Any
    Slot: Any
    QUrl: Any
    QQmlApplicationEngine: Any


def _load_picker_qt() -> _PickerQt:
    try:
        from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
        from PySide6.QtQml import QQmlApplicationEngine
    except ImportError as exc:
        raise DependencyMissingError("Picker requires PySide6") from exc
    return _PickerQt(
        QObject=QObject,
        Property=Property,
        Signal=Signal,
        Slot=Slot,
        QUrl=QUrl,
        QQmlApplicationEngine=QQmlApplicationEngine,
    )


def _create_bridge(qt: _PickerQt, surface: QmlPickerSurface) -> Any:
    class PickerBridge(qt.QObject):  # type: ignore[misc, valid-type]
        payloadChanged = qt.Signal()
        actionBusyChanged = qt.Signal()

        def __init__(self) -> None:
            super().__init__()
            self._action_busy = False

        @qt.Property("QVariant", notify=payloadChanged)
        def payload(self) -> dict[str, object]:
            return surface.payload

        @qt.Property(bool, notify=actionBusyChanged)
        def actionBusy(self) -> bool:
            return self._action_busy

        @qt.Slot(str)
        def openPreflight(self, recipe_id: str) -> None:
            surface.open_preflight(recipe_id)

        @qt.Slot()
        def browseAll(self) -> None:
            surface.browse_all()

        @qt.Slot()
        def openBuilder(self) -> None:
            surface.open_builder()

        @qt.Slot()
        def openActiveRitual(self) -> None:
            surface.open_active_ritual()

    return PickerBridge()


def _connect_if_present(root: Any, signal_name: str, callback: Callable[..., None]) -> None:
    signal = getattr(root, signal_name, None)
    if signal is not None and hasattr(signal, "connect"):
        signal.connect(callback)
