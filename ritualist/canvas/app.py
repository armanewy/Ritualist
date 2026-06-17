from __future__ import annotations

import sys
from concurrent.futures import Future, ThreadPoolExecutor
from importlib.resources import as_file, files
from pathlib import Path
from threading import Event
from typing import Any

from ritualist.adapters import create_default_adapters
from ritualist.e2e import record_event
from ritualist.errors import DependencyMissingError, RitualistError
from ritualist.config import load_app_config
from ritualist.home.actions import home_event_from_runtime, home_event_from_step_status
from ritualist.home.confirmation import InlineConfirmationPresenter
from ritualist.home.models import HomeCardStatus, HomeRuntimeEvent
from ritualist.recipe_loader import discover_recipes
from ritualist.runtime_control import RuntimeControl
from ritualist.target_resolution import builtin_target_catalog
from ritualist.watch_me import WatchMeService

from .controller import CanvasRuntimeController
from .edit import CanvasEditSession, create_edit_session
from .edit_ui import CanvasEditUiBridge
from .models import CanvasBindingKind, CanvasDocument
from .runtime import CanvasRuntimeContext
from .storage import create_mock_canvas
from .view_model import build_canvas_view_model


def build_canvas_use_payload(
    document: CanvasDocument,
    *,
    runtime_state: dict[str, dict[str, Any]] | None = None,
    recipe_ids: set[str] | None = None,
    target_ids: set[str] | None = None,
) -> dict[str, object]:
    """Build a Canvas Use payload from explicit, side-effect-free context."""
    model = build_canvas_view_model(
        document,
        context=CanvasRuntimeContext(
            recipe_ids=set(recipe_ids or ()),
            target_ids=set(target_ids or ()),
            runtime_state=runtime_state or {},
            recent_runs=(),
            resolve_targets=False,
        ),
    )
    return model.to_dict()


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
        editPayloadChanged = Signal()
        editModeChanged = Signal()
        metricsChanged = Signal()
        actionStateChanged = Signal()
        actionCompleted = Signal(str, object)
        actionFailed = Signal(str, str)
        runtimeEventReceived = Signal(str, object)
        statusEventReceived = Signal(str, object)
        confirmationRequested = Signal(str, object)
        confirmationDecision = Signal(bool)
        watchMeChanged = Signal()

        def __init__(
            self,
            document: CanvasDocument,
            edit_bridge: CanvasEditUiBridge,
            *,
            mock: bool,
            recipe_ids: set[str],
            target_ids: set[str],
        ) -> None:
            super().__init__()
            self._document = document
            self._edit_bridge = edit_bridge
            self._mock = mock
            self._recipe_ids = recipe_ids
            self._target_ids = target_ids
            self._edit_mode = False
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
            self._watch_me_service = WatchMeService(adapters=create_default_adapters())
            self._watch_me_session_id: str | None = None
            self._watch_me_recording = False
            self._watch_me_draft_available = False
            self._watch_me_status_label = "Watch Me ready"
            self._watch_me_draft_summary = ""
            self._watch_me_draft_preview = ""
            self.actionCompleted.connect(self._complete_action)
            self.actionFailed.connect(self._mark_action_failed)
            self.runtimeEventReceived.connect(self._apply_runtime_event)
            self.statusEventReceived.connect(self._apply_status_event)
            self.confirmationRequested.connect(self._request_confirmation)
            self.confirmationDecision.connect(self._answer_confirmation)

        @Property("QVariantMap", notify=payloadChanged)
        def payload(self) -> dict[str, object]:
            return self._payload()

        @Property("QVariantMap", notify=editPayloadChanged)
        def editPayload(self) -> dict[str, object]:
            return self._edit_bridge.model()

        @Property(bool, notify=editModeChanged)
        def editMode(self) -> bool:
            return self._edit_mode

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

        @Property(bool, notify=watchMeChanged)
        def watchMeRecording(self) -> bool:
            return self._watch_me_recording

        @Property(bool, notify=watchMeChanged)
        def watchMeDraftAvailable(self) -> bool:
            return self._watch_me_draft_available

        @Property(str, notify=watchMeChanged)
        def watchMeStatusLabel(self) -> str:
            return self._watch_me_status_label

        @Property(str, notify=watchMeChanged)
        def watchMeDraftSummary(self) -> str:
            return self._watch_me_draft_summary

        @Property(str, notify=watchMeChanged)
        def watchMeDraftPreview(self) -> str:
            return self._watch_me_draft_preview

        @Slot(str, str)
        def dispatchAction(self, component_id: str, action_id: str) -> None:
            record_event(
                "canvas.action.requested",
                component_id=component_id,
                action_id=action_id,
            )
            if self._edit_mode:
                self._last_event_label = "Switch to Use Mode before running Canvas actions"
                self.metricsChanged.emit()
                return
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

        @Slot(bool)
        def setEditMode(self, enabled: bool) -> None:
            enabled = bool(enabled)
            if self._edit_mode == enabled:
                return
            self._edit_mode = enabled
            self._last_event_label = "Edit Mode" if enabled else "Use Mode"
            self.editModeChanged.emit()
            self.metricsChanged.emit()
            self.editPayloadChanged.emit()
            self.payloadChanged.emit()

        @Slot(str)
        def selectComponent(self, component_id: str) -> None:
            if not self._edit_mode:
                return
            self._apply_edit(lambda: self._edit_bridge.select(component_id))

        @Slot(str)
        def addComponent(self, type_id: str) -> None:
            if not self._edit_mode:
                return
            self._apply_edit(lambda: self._edit_bridge.create_component(type_id))

        @Slot(str, float, float)
        def moveComponent(self, component_id: str, x: float, y: float) -> None:
            if not self._edit_mode:
                return
            self._apply_edit(lambda: self._edit_bridge.move_component(component_id, x, y))

        @Slot(str, float, float)
        def resizeComponent(self, component_id: str, width: float, height: float) -> None:
            if not self._edit_mode:
                return
            self._apply_edit(lambda: self._edit_bridge.resize_component(component_id, width, height))

        @Slot(str, str, "QVariant")
        def editComponentProperty(self, component_id: str, name: str, value: object) -> None:
            if not self._edit_mode:
                return
            self._apply_edit(lambda: self._edit_bridge.edit_property(component_id, name, value))

        @Slot(str, str, str)
        def editComponentBinding(self, component_id: str, kind: str, reference: str) -> None:
            if not self._edit_mode:
                return
            self._apply_edit(lambda: self._edit_bridge.edit_binding(component_id, kind, reference))

        @Slot()
        def duplicateSelectedComponent(self) -> None:
            if not self._edit_mode:
                return
            self._apply_edit(self._edit_bridge.duplicate_selected)

        @Slot()
        def deleteSelectedComponent(self) -> None:
            if not self._edit_mode:
                return
            self._apply_edit(self._edit_bridge.delete_selected)

        @Slot()
        def undoEdit(self) -> None:
            if not self._edit_mode:
                return
            self._apply_edit(self._edit_bridge.undo)

        @Slot()
        def redoEdit(self) -> None:
            if not self._edit_mode:
                return
            self._apply_edit(self._edit_bridge.redo)

        @Slot()
        def discardEdit(self) -> None:
            if not self._edit_mode:
                return
            self._apply_edit(self._edit_bridge.discard)

        @Slot()
        def saveCanvas(self) -> None:
            if not self._edit_mode:
                return
            if self._mock:
                self._last_event_label = "Mock Canvas edits are not saved"
                self.metricsChanged.emit()
                return
            try:
                result = self._edit_bridge.save()
            except Exception as exc:  # noqa: BLE001 - surface validation errors in the UI.
                self._last_event_label = f"Save failed: {exc}"
                self.metricsChanged.emit()
                self.editPayloadChanged.emit()
                return
            self._document = self._edit_bridge.document
            self._last_event_label = result.message
            self.metricsChanged.emit()
            self.editPayloadChanged.emit()
            self.payloadChanged.emit()

        @Slot()
        def pauseCurrentRun(self) -> None:
            record_event("canvas.runtime_control.requested", action="pause")
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
            record_event("canvas.runtime_control.requested", action="resume")
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
            record_event("canvas.runtime_control.requested", action="stop")
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
        def startWatchMe(self) -> None:
            record_event("canvas.watch_me.requested", action="start")
            if self._mock:
                self._set_watch_me_status("Watch Me is disabled in mock mode")
                return
            if self._watch_me_recording:
                self._set_watch_me_status("Watch Me is already recording")
                return
            try:
                session = self._watch_me_service.start()
            except Exception as exc:  # noqa: BLE001 - Watch Me errors are surfaced in Canvas.
                self._set_watch_me_status(f"Watch Me failed: {exc}")
                return
            self._watch_me_session_id = session.session_id
            self._watch_me_recording = True
            self._watch_me_draft_available = False
            self._watch_me_draft_summary = ""
            self._watch_me_draft_preview = ""
            self._set_watch_me_status(f"Recording Watch Me session {session.session_id}")

        @Slot()
        def stopWatchMe(self) -> None:
            record_event("canvas.watch_me.requested", action="stop")
            if not self._watch_me_session_id:
                self._set_watch_me_status("No Watch Me session is active")
                return
            if not self._watch_me_recording:
                self._set_watch_me_status("Watch Me is not recording")
                return
            try:
                session = self._watch_me_service.stop(self._watch_me_session_id)
            except Exception as exc:  # noqa: BLE001
                self._set_watch_me_status(f"Watch Me failed: {exc}")
                return
            self._watch_me_recording = False
            self._watch_me_draft_available = True
            self._watch_me_draft_summary = f"{len(session.events)} safe event(s) captured"
            self._set_watch_me_status("Watch Me stopped; draft can be created")

        @Slot()
        def createWatchMeDraft(self) -> None:
            record_event("canvas.watch_me.requested", action="create_draft")
            if not self._watch_me_session_id:
                self._set_watch_me_status("No Watch Me session is available")
                return
            try:
                draft = self._watch_me_service.create_draft(self._watch_me_session_id)
                session = self._watch_me_service.load(self._watch_me_session_id)
            except Exception as exc:  # noqa: BLE001
                self._set_watch_me_status(f"Watch Me draft failed: {exc}")
                return
            self._watch_me_draft_available = False
            self._watch_me_draft_summary = (
                f"Draft {draft.recipe.get('id')} disabled for review; "
                f"{len(draft.recipe.get('steps', []))} suggested step(s)."
            )
            self._watch_me_draft_preview = "\n".join(draft.preview[:10])
            if session.draft_path:
                self._watch_me_draft_summary += f" Saved to {session.draft_path}"
            self._set_watch_me_status("Watch Me draft created")

        @Slot()
        def discardWatchMe(self) -> None:
            record_event("canvas.watch_me.requested", action="discard")
            if not self._watch_me_session_id:
                self._set_watch_me_status("No Watch Me session is available")
                return
            try:
                session = self._watch_me_service.discard(self._watch_me_session_id)
            except Exception as exc:  # noqa: BLE001
                self._set_watch_me_status(f"Watch Me discard failed: {exc}")
                return
            self._watch_me_session_id = None
            self._watch_me_recording = False
            self._watch_me_draft_available = False
            self._watch_me_draft_summary = ""
            self._watch_me_draft_preview = ""
            self._set_watch_me_status(f"Watch Me discarded: {session.session_id}")

        @Slot()
        def shutdown(self) -> None:
            if self._runtime_control is not None:
                self._runtime_control.stop()
            self._answer_confirmation(False)
            if self._executor is not None:
                self._executor.shutdown(wait=False, cancel_futures=True)
                self._executor = None

        def _payload(self) -> dict[str, object]:
            return build_canvas_use_payload(
                self._document,
                runtime_state=self._runtime_state,
                recipe_ids=self._recipe_ids,
                target_ids=self._target_ids,
            )

        def _apply_edit(self, operation) -> None:
            try:
                operation()
            except Exception as exc:  # noqa: BLE001 - edit validation belongs in the UI footer.
                self._last_event_label = f"Edit failed: {exc}"
                self.metricsChanged.emit()
                self.editPayloadChanged.emit()
                return
            self._document = self._edit_bridge.document
            self._last_event_label = "Canvas edit applied"
            self.metricsChanged.emit()
            self.editPayloadChanged.emit()
            self.payloadChanged.emit()

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

        def _set_watch_me_status(self, message: str) -> None:
            record_event("canvas.watch_me.status", message=message)
            self._watch_me_status_label = message
            self._last_event_label = message
            self.watchMeChanged.emit()
            self.metricsChanged.emit()

        def _publish_status(
            self,
            component_id: str,
            status: str,
            message: str,
            *,
            state: str | None = None,
        ) -> None:
            record_event(
                "canvas.status",
                component_id=component_id,
                status=status,
                state=state,
                message=message,
            )
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
            record_event("canvas.confirmation.requested", component_id=component_id, prompt=prompt)
            self._publish_status(component_id, HomeCardStatus.WARNING.value, "Confirmation required")
            self._confirmation_presenter.request_confirmation(
                prompt,
                on_decision=self.confirmationDecision.emit,
            )

        def _answer_confirmation(self, accepted: bool) -> None:
            record_event("canvas.confirmation.answered", accepted=accepted)
            self._confirmation_result = accepted
            self._confirmation_event.set()

    app = QApplication.instance() or QApplication(sys.argv)
    edit_session = (
        CanvasEditSession(document=create_mock_canvas(mock_components), source="memory")
        if mock
        else create_edit_session(canvas)
    )
    document = edit_session.document
    recipe_ids = _canvas_recipe_ids(document) if mock else _discover_canvas_recipe_ids()
    target_ids = _canvas_target_ids(document) if mock else _discover_canvas_target_ids()
    controller = CanvasUseController(
        document,
        CanvasEditUiBridge(edit_session),
        mock=mock,
        recipe_ids=recipe_ids,
        target_ids=target_ids,
    )
    performance = load_app_config().canvas.performance_settings().to_dict()

    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("ritualistMockMode", mock)
    engine.rootContext().setContextProperty("ritualistCanvasUseController", controller)
    engine.rootContext().setContextProperty("ritualistCanvasPayload", controller.payload)
    engine.rootContext().setContextProperty("ritualistCanvasEditPayload", controller.editPayload)
    engine.rootContext().setContextProperty("ritualistCanvasPerformance", performance)
    qml_resource = files("ritualist.canvas.qml").joinpath("CanvasUse.qml")
    with as_file(qml_resource) as qml_path:
        engine.load(QUrl.fromLocalFile(str(qml_path)))
        if not engine.rootObjects():
            raise RitualistError(f"Canvas Use UI failed to load: {qml_path}")
    ready_payload = controller.payload
    ready_theme = {}
    if isinstance(ready_payload.get("canvas"), dict):
        ready_theme = dict(ready_payload["canvas"].get("theme") or {})
    ready_validation = dict(ready_theme.get("validation") or {})
    record_event(
        "canvas.ready",
        canvas=str(canvas),
        mock=mock,
        theme_id=str(ready_theme.get("id") or ""),
        theme_valid=bool(ready_validation.get("valid")),
        theme_source=str(ready_theme.get("source") or ""),
    )
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


def _canvas_recipe_ids(document: CanvasDocument) -> set[str]:
    ids: set[str] = set()
    for component in document.components:
        if component.binding is not None and component.binding.kind is CanvasBindingKind.RECIPE:
            _add_nonblank(ids, component.binding.reference)
        props = component.props_dict()
        _add_nonblank(ids, props.get("recipe_id"))
    return ids


def _discover_canvas_recipe_ids() -> set[str]:
    ids: set[str] = set()
    for path, recipe, _error in discover_recipes():
        _add_nonblank(ids, recipe.id if recipe is not None else path.stem)
    return ids


def _canvas_target_ids(document: CanvasDocument) -> set[str]:
    ids: set[str] = set()
    for component in document.components:
        if component.binding is not None and component.binding.kind is CanvasBindingKind.TARGET_START:
            _add_nonblank(ids, component.binding.reference)
        props = component.props_dict()
        _add_nonblank(ids, props.get("target"))
        _add_nonblank(ids, props.get("target_id"))
    return ids


def _discover_canvas_target_ids() -> set[str]:
    return {target.id for target in builtin_target_catalog().targets}


def _add_nonblank(values: set[str], value: object) -> None:
    text = str(value or "").strip()
    if text:
        values.add(text)


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
