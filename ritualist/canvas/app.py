from __future__ import annotations

import sys
from concurrent.futures import Future, ThreadPoolExecutor
from importlib.resources import as_file, files
from pathlib import Path
from threading import Event
from typing import Any

from ritualist.errors import DependencyMissingError, RitualistError
from ritualist.home.actions import home_event_from_runtime, home_event_from_step_status
from ritualist.home.confirmation import InlineConfirmationPresenter
from ritualist.home.models import HomeCardStatus, HomeRuntimeEvent
from ritualist.runtime_control import RuntimeControl

from .controller import CanvasRuntimeController
from .models import CanvasDocument
from .runtime import CanvasRuntimeContext
from .storage import create_mock_canvas, load_canvas
from .view_model import build_canvas_view_model


def run_canvas_use(
    canvas: str | Path,
    *,
    mock: bool = False,
    mock_components: int = 24,
) -> int:
    """Launch Canvas Use Mode with a bundled, typed QML renderer."""
    try:
        from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtQml import QQmlApplicationEngine
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        raise DependencyMissingError("Canvas Use Mode requires PySide6; install ritualist[gui]") from exc

    class CanvasUseController(QObject):
        payloadChanged = Signal()
        metricsChanged = Signal()
        actionStateChanged = Signal()
        actionCompleted = Signal(str, object)
        actionFailed = Signal(str, str)
        runtimeEventReceived = Signal(str, object)
        statusEventReceived = Signal(str, object)
        confirmationRequested = Signal(str, object)
        confirmationDecision = Signal(bool)

        def __init__(self, document: CanvasDocument, *, mock: bool) -> None:
            super().__init__()
            self._document = document
            self._mock = mock
            self._runtime_state: dict[str, dict[str, Any]] = {}
            self._last_event_label = "Canvas ready"
            self._action_busy = False
            self._runtime_control: RuntimeControl | None = None
            self._runtime_paused = False
            self._executor: ThreadPoolExecutor | None = None
            self._action_future: Future[object] | None = None
            self._confirmation_event = Event()
            self._confirmation_result = False
            self._confirmation_presenter = _create_confirmation_presenter()
            self._runtime_controller = CanvasRuntimeController()
            self.actionCompleted.connect(self._complete_action)
            self.actionFailed.connect(self._mark_action_failed)
            self.runtimeEventReceived.connect(self._apply_runtime_event)
            self.statusEventReceived.connect(self._apply_status_event)
            self.confirmationRequested.connect(self._request_confirmation)
            self.confirmationDecision.connect(self._answer_confirmation)

        @Property("QVariantMap", notify=payloadChanged)
        def payload(self) -> dict[str, object]:
            return self._payload()

        @Property(str, notify=metricsChanged)
        def lastEventLabel(self) -> str:
            return self._last_event_label

        @Property(bool, notify=actionStateChanged)
        def actionBusy(self) -> bool:
            return self._action_busy

        @Property(bool, notify=actionStateChanged)
        def runtimeActive(self) -> bool:
            return self._runtime_control is not None

        @Property(bool, notify=actionStateChanged)
        def runtimePaused(self) -> bool:
            return self._runtime_paused

        @Slot(str, str)
        def dispatchAction(self, component_id: str, action_id: str) -> None:
            if self._mock:
                self._last_event_label = f"{action_id} is disabled in mock mode"
                self.metricsChanged.emit()
                return
            if self._action_busy:
                self._last_event_label = "Another Canvas action is still running"
                self.metricsChanged.emit()
                return
            self._set_action_busy(True)
            self._last_event_label = f"Dispatching {component_id}:{action_id}"
            self.metricsChanged.emit()
            control = RuntimeControl()
            self._runtime_control = control
            self._runtime_paused = False
            self._runtime_state[_component_reference(self._document, component_id)] = {
                "status": "running",
                "message": self._last_event_label,
            }
            self.payloadChanged.emit()
            future = self._ensure_executor().submit(
                self._dispatch_worker,
                component_id,
                action_id,
                control,
            )
            self._action_future = future
            future.add_done_callback(lambda completed: self._complete_future(component_id, completed))
            self.actionStateChanged.emit()

        @Slot()
        def pauseCurrentRun(self) -> None:
            if self._runtime_control is None:
                self._last_event_label = "No Canvas run is active"
                self.metricsChanged.emit()
                return
            self._runtime_control.pause()
            self._runtime_paused = True
            self._last_event_label = "Pausing current Canvas run"
            self.actionStateChanged.emit()
            self.metricsChanged.emit()

        @Slot()
        def resumeCurrentRun(self) -> None:
            if self._runtime_control is None:
                self._last_event_label = "No Canvas run is active"
                self.metricsChanged.emit()
                return
            self._runtime_control.resume()
            self._runtime_paused = False
            self._last_event_label = "Resuming current Canvas run"
            self.actionStateChanged.emit()
            self.metricsChanged.emit()

        @Slot()
        def stopCurrentRun(self) -> None:
            if self._runtime_control is None:
                self._last_event_label = "No Canvas run is active"
                self.metricsChanged.emit()
                return
            self._runtime_control.stop()
            self._answer_confirmation(False)
            self._runtime_paused = False
            self._last_event_label = "Stopping current Canvas run"
            self.actionStateChanged.emit()
            self.metricsChanged.emit()

        @Slot()
        def shutdown(self) -> None:
            if self._runtime_control is not None:
                self._runtime_control.stop()
            self._answer_confirmation(False)
            if self._executor is not None:
                self._executor.shutdown(wait=False, cancel_futures=True)
                self._executor = None

        def _payload(self) -> dict[str, object]:
            model = build_canvas_view_model(
                self._document,
                context=CanvasRuntimeContext(
                    runtime_state=self._runtime_state,
                    recent_runs=(),
                    resolve_targets=False,
                ),
            )
            return model.to_dict()

        def _ensure_executor(self) -> ThreadPoolExecutor:
            if self._executor is None:
                self._executor = ThreadPoolExecutor(
                    max_workers=2,
                    thread_name_prefix="ritualist-canvas-use",
                )
            return self._executor

        def _dispatch_worker(
            self,
            component_id: str,
            action_id: str,
            control: RuntimeControl,
        ) -> object:
            return self._runtime_controller.dispatch(
                self._document,
                component_id,
                action_id,
                runtime_event_callback=lambda event: self.runtimeEventReceived.emit(component_id, event),
                status_callback=lambda event: self.statusEventReceived.emit(component_id, event),
                confirmer=lambda prompt: self._confirm(component_id, prompt),
                control=control,
            )

        def _confirm(self, component_id: str, prompt: object) -> bool:
            self._confirmation_event.clear()
            self.confirmationRequested.emit(component_id, prompt)
            while not self._confirmation_event.wait(timeout=5):
                if self._runtime_control is not None:
                    self._runtime_control.heartbeat()
                    self._runtime_control.raise_if_stopped()
            return self._confirmation_result

        def _complete_future(self, component_id: str, future: Future[object]) -> None:
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001 - report worker failures to Canvas.
                self.actionFailed.emit(component_id, str(exc))
                return
            self.actionCompleted.emit(component_id, result)

        def _set_action_busy(self, busy: bool) -> None:
            if self._action_busy == busy:
                return
            self._action_busy = busy
            self.actionStateChanged.emit()

        def _publish_status(
            self,
            component_id: str,
            status: str,
            message: str,
            *,
            state: str | None = None,
        ) -> None:
            reference = _component_reference(self._document, component_id)
            self._runtime_state[reference] = {
                "status": state or status,
                "message": message,
                "current_step": message,
            }
            self._last_event_label = f"{component_id}: {message or status}"
            self.payloadChanged.emit()
            self.metricsChanged.emit()

        def _complete_action(self, component_id: str, result: object) -> None:
            status = str(getattr(result, "status", "success"))
            message = str(getattr(result, "message", "") or "Canvas action completed")
            data = getattr(result, "data", None)
            if isinstance(data, dict) and "path" in data:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(data["path"])))
            self._publish_status(component_id, status, message, state="success")
            self._runtime_control = None
            self._runtime_paused = False
            self._set_action_busy(False)

        def _mark_action_failed(self, component_id: str, message: str) -> None:
            self._publish_status(component_id, "failed", message, state="failed")
            self._runtime_control = None
            self._runtime_paused = False
            self._set_action_busy(False)

        def _apply_runtime_event(self, component_id: str, event: object) -> None:
            home_event = home_event_from_runtime(component_id, event)
            self._apply_home_event(component_id, home_event)

        def _apply_status_event(self, component_id: str, event: object) -> None:
            self._apply_home_event(component_id, home_event_from_step_status(component_id, event))

        def _apply_home_event(self, component_id: str, event: HomeRuntimeEvent | None) -> None:
            if event is None:
                return
            status = event.status.value if event.status is not None else "running"
            message = event.subtitle or event.description or status
            self._publish_status(component_id, status, message)

        def _request_confirmation(self, component_id: str, prompt: object) -> None:
            self._publish_status(component_id, HomeCardStatus.WARNING.value, "Confirmation required")
            self._confirmation_presenter.request_confirmation(
                prompt,
                on_decision=self.confirmationDecision.emit,
            )

        def _answer_confirmation(self, accepted: bool) -> None:
            self._confirmation_result = accepted
            self._confirmation_event.set()

    app = QApplication.instance() or QApplication(sys.argv)
    document = create_mock_canvas(mock_components) if mock else load_canvas(canvas)
    controller = CanvasUseController(document, mock=mock)

    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("ritualistMockMode", mock)
    engine.rootContext().setContextProperty("ritualistCanvasUseController", controller)
    engine.rootContext().setContextProperty("ritualistCanvasPayload", controller.payload)
    qml_resource = files("ritualist.canvas.qml").joinpath("CanvasUse.qml")
    with as_file(qml_resource) as qml_path:
        engine.load(QUrl.fromLocalFile(str(qml_path)))
        if not engine.rootObjects():
            raise RitualistError(f"Canvas Use UI failed to load: {qml_path}")
    app.aboutToQuit.connect(controller.shutdown)
    try:
        return app.exec()
    finally:
        controller.shutdown()


def _component_reference(document: CanvasDocument, component_id: str) -> str:
    for component in document.components:
        if component.id != component_id:
            continue
        if component.binding is not None and component.binding.reference:
            return component.binding.reference
        props = component.props_dict()
        return str(
            props.get("recipe_id")
            or props.get("target")
            or props.get("target_id")
            or component.id
        )
    return component_id


def _create_confirmation_presenter() -> object:
    try:
        from ritualist.home.confirmation import (
            create_qt_confirmation_presenter,
            create_win32_confirmation_presenter,
        )

        try:
            return create_qt_confirmation_presenter()
        except Exception:  # noqa: BLE001 - use native fallback before in-window fallback.
            if sys.platform == "win32":
                try:
                    return create_win32_confirmation_presenter()
                except Exception:  # noqa: BLE001 - fallback still preserves confirmation gate.
                    pass
    except Exception:  # noqa: BLE001 - fallback below remains safe.
        pass
    return InlineConfirmationPresenter(lambda _request, on_decision: on_decision(False))
