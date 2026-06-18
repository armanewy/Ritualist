from __future__ import annotations

import sys
import time
from concurrent.futures import Future, ThreadPoolExecutor
from importlib.resources import as_file, files
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from typing import Any

from ritualist.e2e import enabled as e2e_enabled
from ritualist.e2e import record_event
from ritualist.errors import DependencyMissingError, RitualistError
from ritualist.config import load_app_config
from ritualist.home.actions import (
    ActivityJournalHook,
    HomeActionService,
    create_activity_journal_hook,
    home_event_from_runtime,
    home_event_from_step_status,
)
from ritualist.home.confirmation import InlineConfirmationPresenter
from ritualist.home.models import HomeCardStatus, HomeRuntimeEvent
from ritualist.recipe_loader import discover_recipes
from ritualist.runtime_control import RuntimeControl
from ritualist.target_resolution import builtin_target_catalog

from .controller import CanvasRuntimeController
from .edit import CanvasEditSession, create_edit_session
from .edit_ui import CanvasEditUiBridge, CanvasSuggestionsReviewBridge
from .host import (
    CANVAS_FORCE_WINDOWED_ENV,
    CanvasHostConfig,
    ensure_canvas_host_is_implemented,
    resolve_canvas_host_config,
)
from .models import CanvasBindingKind, CanvasDocument
from .ritual_state import ritual_state_from_action_result, ritual_state_from_runtime_event
from .runtime import CanvasRuntimeContext
from .storage import create_mock_canvas
from .view_model import build_canvas_view_model


def build_canvas_use_payload(
    document: CanvasDocument,
    *,
    runtime_state: dict[str, dict[str, Any]] | None = None,
    recipe_ids: set[str] | None = None,
    target_ids: set[str] | None = None,
    doctor_summaries: dict[str, dict[str, Any]] | None = None,
    dry_run_summaries: dict[str, dict[str, Any]] | None = None,
    load_recent_runs: bool = False,
) -> dict[str, object]:
    """Build a Canvas Use payload from explicit context.

    Recent runs stay disabled by default so CLI/perf/test callers remain
    side-effect-free. The live Canvas opts in so `recent.activity` can reflect
    local run history.
    """
    model = build_canvas_view_model(
        document,
        context=CanvasRuntimeContext(
            recipe_ids=set(recipe_ids or ()),
            target_ids=set(target_ids or ()),
            runtime_state=runtime_state or {},
            doctor_summaries=doctor_summaries or {},
            dry_run_summaries=dry_run_summaries or {},
            recent_runs=None if load_recent_runs else (),
            resolve_targets=False,
        ),
    )
    return model.to_dict()


def run_canvas_use(
    canvas: str | Path,
    *,
    mock: bool = False,
    mock_components: int = 24,
    host_config: CanvasHostConfig | None = None,
) -> int:
    """Launch Canvas Use Mode with a bundled, typed QML renderer."""
    resolved_host_config = host_config or resolve_canvas_host_config()
    ensure_canvas_host_is_implemented(resolved_host_config)
    try:
        from PySide6.QtCore import Property, QObject, QUrl, Qt, Signal, Slot
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtQml import QQmlApplicationEngine
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        raise DependencyMissingError("Canvas Use Mode requires PySide6; install ritualist[gui]") from exc

    class CanvasUseController(QObject):
        payloadChanged = Signal()
        editPayloadChanged = Signal()
        editModeChanged = Signal()
        suggestionsPayloadChanged = Signal()
        metricsChanged = Signal()
        actionStateChanged = Signal()
        actionCompleted = Signal(str, object)
        actionFailed = Signal(str, str)
        suggestionsOperationCompleted = Signal(object)
        suggestionsOperationFailed = Signal(str)
        runtimeEventReceived = Signal(str, object)
        statusEventReceived = Signal(str, object)
        confirmationRequested = Signal(str, object)
        confirmationDecision = Signal(bool)

        def __init__(
            self,
            document: CanvasDocument,
            edit_bridge: CanvasEditUiBridge,
            suggestions_bridge: CanvasSuggestionsReviewBridge,
            *,
            mock: bool,
            recipe_ids: set[str],
            target_ids: set[str],
            journal_hook: ActivityJournalHook,
        ) -> None:
            super().__init__()
            self._document = document
            self._edit_bridge = edit_bridge
            self._suggestions_bridge = suggestions_bridge
            self._mock = mock
            self._recipe_ids = recipe_ids
            self._target_ids = target_ids
            self._edit_mode = False
            self._runtime_state: dict[str, dict[str, Any]] = {}
            self._last_event_label = "Canvas ready"
            self._action_busy = False
            self._runtime_control: RuntimeControl | None = None
            self._runtime_paused = False
            self._suggestions_busy = False
            self._executor: ThreadPoolExecutor | None = None
            self._action_future: Future[object] | None = None
            self._confirmation_event = Event()
            self._confirmation_result = False
            self._confirmation_component_id = ""
            self._confirmation_presenter = _create_confirmation_presenter()
            self._activity_journal = journal_hook
            self._runtime_controller = CanvasRuntimeController(
                action_service=HomeActionService(journal_hook=journal_hook)
            )
            self._heartbeat_start = time.perf_counter()
            self.actionCompleted.connect(self._complete_action)
            self.actionFailed.connect(self._mark_action_failed)
            self.suggestionsOperationCompleted.connect(self._complete_suggestions_operation)
            self.suggestionsOperationFailed.connect(self._fail_suggestions_operation)
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

        @Property("QVariantMap", notify=suggestionsPayloadChanged)
        def suggestionsPayload(self) -> dict[str, object]:
            payload = self._suggestions_bridge.model()
            payload["busy"] = self._suggestions_busy
            return payload

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
            _record_canvas_component_clicked(
                self._activity_journal,
                self._document,
                component_id,
                action_id,
            )
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

        @Slot(float, int, float, int, int)
        def recordUiHeartbeat(
            self,
            qml_wall_ms: float,
            payload_version: int,
            last_payload_update_ms: float,
            payload_updates_this_second: int,
            measured_fps: int,
        ) -> None:
            if not e2e_enabled():
                return
            recent_items = _recent_activity_items(self._payload())
            record_event(
                "canvas.ui_heartbeat",
                canvas=self._document.id,
                mock=self._mock,
                monotonic_ms=round((time.perf_counter() - self._heartbeat_start) * 1000, 1),
                qml_wall_ms=round(float(qml_wall_ms), 1),
                payload_version=int(payload_version),
                last_payload_update_ms=round(float(last_payload_update_ms), 1),
                payload_updates_this_second=int(payload_updates_this_second),
                measured_fps=int(measured_fps),
                action_busy=self._action_busy,
                runtime_active=self._runtime_control is not None,
                recent_activity_count=len(recent_items),
                recent_activity_run_ids=[str(item.get("run_id") or "") for item in recent_items],
                recent_activity_items=recent_items[:5],
            )

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

        @Slot(result=bool)
        def saveCanvas(self) -> bool:
            if not self._edit_mode:
                return False
            if self._mock:
                self._last_event_label = "Mock Canvas edits are not saved"
                self.metricsChanged.emit()
                return False
            try:
                result = self._edit_bridge.save()
            except Exception as exc:  # noqa: BLE001 - surface validation errors in the UI.
                self._last_event_label = f"Save failed: {exc}"
                self.metricsChanged.emit()
                self.editPayloadChanged.emit()
                return False
            self._document = self._edit_bridge.document
            self._last_event_label = result.message
            self.metricsChanged.emit()
            self.editPayloadChanged.emit()
            self.payloadChanged.emit()
            return True

        @Slot(str)
        def filterSuggestions(self, filter_kind: str) -> None:
            if not self._suggestions_available():
                return
            self._suggestions_bridge.set_filter(filter_kind)
            self.suggestionsPayloadChanged.emit()

        @Slot()
        def findSuggestions(self) -> None:
            if not self._suggestions_available():
                return
            if self._suggestions_busy:
                return
            self._suggestions_busy = True
            self.suggestionsPayloadChanged.emit()
            future = self._ensure_executor().submit(self._suggestions_bridge.find_suggestions)
            future.add_done_callback(self._complete_suggestions_future)

        @Slot(str)
        def reviewSuggestion(self, suggestion_id: str) -> None:
            if not self._suggestions_available():
                return
            self._suggestions_bridge.review_suggestion(suggestion_id)
            self.suggestionsPayloadChanged.emit()

        @Slot(str)
        def editSuggestionBeforeCreating(self, suggestion_id: str) -> None:
            if not self._suggestions_available():
                return
            self._suggestions_bridge.edit_before_creating(suggestion_id)
            self.suggestionsPayloadChanged.emit()

        @Slot(str)
        def createSuggestionDraft(self, suggestion_id: str) -> None:
            if not self._suggestions_available():
                return
            self._suggestions_bridge.create_draft(suggestion_id)
            self.suggestionsPayloadChanged.emit()

        @Slot(str)
        def dismissSuggestion(self, suggestion_id: str) -> None:
            if not self._suggestions_available():
                return
            self._suggestions_bridge.dismiss_suggestion(suggestion_id)
            self.suggestionsPayloadChanged.emit()

        @Slot()
        def deleteAllSuggestions(self) -> None:
            if not self._suggestions_available():
                return
            self._suggestions_bridge.delete_all()
            self.suggestionsPayloadChanged.emit()

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
        def shutdown(self) -> None:
            if self._runtime_control is not None:
                self._runtime_control.stop()
            self._answer_confirmation(False)
            if self._executor is not None:
                self._executor.shutdown(wait=False, cancel_futures=True)
                self._executor = None
            self._activity_journal.shutdown(wait=False)

        def _payload(self) -> dict[str, object]:
            return build_canvas_use_payload(
                self._document,
                runtime_state=self._runtime_state,
                recipe_ids=self._recipe_ids,
                target_ids=self._target_ids,
                load_recent_runs=not self._mock,
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

        def _complete_suggestions_future(self, future: Future[object]) -> None:
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001 - report scan failures to Canvas.
                self.suggestionsOperationFailed.emit(str(exc))
                return
            self.suggestionsOperationCompleted.emit(result)

        def _complete_suggestions_operation(self, _result: object) -> None:
            self._suggestions_busy = False
            self.suggestionsPayloadChanged.emit()

        def _fail_suggestions_operation(self, message: str) -> None:
            self._suggestions_busy = False
            self._suggestions_bridge.last_error = message
            self._suggestions_bridge.last_message = "Suggestions scan failed"
            self.suggestionsPayloadChanged.emit()

        def _suggestions_available(self) -> bool:
            if self._edit_mode:
                return True
            self._last_event_label = "Switch to Edit Mode to review Suggestions"
            self.metricsChanged.emit()
            return False

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
            ritual_state: dict[str, Any] | None = None,
        ) -> None:
            record_event(
                "canvas.status",
                component_id=component_id,
                status=status,
                state=state,
                message=message,
            )
            reference = _component_reference(self._document, component_id)
            current = dict(self._runtime_state.get(reference, {}))
            current.update(
                {
                    "status": state or status,
                    "message": message,
                    "current_step": message,
                }
            )
            if ritual_state is not None:
                current["ritual_state"] = ritual_state
            self._runtime_state[reference] = current
            self._last_event_label = f"{component_id}: {message or status}"
            self.payloadChanged.emit()
            self.metricsChanged.emit()

        def _complete_action(self, component_id: str, result: object) -> None:
            status = str(getattr(result, "status", "success"))
            message = str(getattr(result, "message", "") or "Canvas action completed")
            data = getattr(result, "data", None)
            if isinstance(data, dict) and "path" in data:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(data["path"])))
            reference = _component_reference(self._document, component_id)
            action_id = str(getattr(result, "action_id", "") or "")
            _record_canvas_shortcut_opened(
                self._activity_journal,
                self._document,
                component_id,
                result,
            )
            current = self._runtime_state.get(reference, {})
            ritual_state = (
                ritual_state_from_action_result(
                    reference,
                    action_id,
                    getattr(result, "data", None),
                    existing=current.get("ritual_state"),
                )
                if action_id in {"doctor", "dry_run", "run"}
                else None
            )
            self._publish_status(component_id, status, message, state="success", ritual_state=ritual_state)
            self._runtime_control = None
            self._runtime_paused = False
            self._set_action_busy(False)

        def _mark_action_failed(self, component_id: str, message: str) -> None:
            self._publish_status(component_id, "failed", message, state="failed")
            self._runtime_control = None
            self._runtime_paused = False
            self._set_action_busy(False)

        def _apply_runtime_event(self, component_id: str, event: object) -> None:
            reference = _component_reference(self._document, component_id)
            current = dict(self._runtime_state.get(reference, {}))
            current["ritual_state"] = ritual_state_from_runtime_event(
                current.get("ritual_state"),
                event,
            )
            self._runtime_state[reference] = current
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
            self._confirmation_component_id = component_id
            self._publish_status(component_id, HomeCardStatus.WARNING.value, "Confirmation required")
            self._confirmation_presenter.request_confirmation(
                prompt,
                on_decision=self.confirmationDecision.emit,
            )

        def _answer_confirmation(self, accepted: bool) -> None:
            record_event("canvas.confirmation.answered", accepted=accepted)
            if accepted and self._confirmation_component_id:
                self._publish_confirmation_starting(self._confirmation_component_id)
            self._confirmation_component_id = ""
            self._confirmation_result = accepted
            self._confirmation_event.set()

        def _publish_confirmation_starting(self, component_id: str) -> None:
            reference = _component_reference(self._document, component_id)
            current = dict(self._runtime_state.get(reference, {}))
            ritual_state = ritual_state_from_runtime_event(
                current.get("ritual_state"),
                _confirmation_starting_event(current.get("ritual_state")),
            )
            self._publish_status(
                component_id,
                HomeCardStatus.RUNNING.value,
                "Starting...",
                state="starting",
                ritual_state=ritual_state,
            )

    app = QApplication.instance() or QApplication(sys.argv)
    edit_session = (
        CanvasEditSession(document=create_mock_canvas(mock_components), source="memory")
        if mock
        else create_edit_session(canvas)
    )
    document = edit_session.document
    recipe_ids = _canvas_recipe_ids(document) if mock else _discover_canvas_recipe_ids()
    target_ids = _canvas_target_ids(document) if mock else _discover_canvas_target_ids()
    config = load_app_config()
    journal_hook = create_activity_journal_hook()
    controller = CanvasUseController(
        document,
        CanvasEditUiBridge(edit_session),
        CanvasSuggestionsReviewBridge(),
        mock=mock,
        recipe_ids=recipe_ids,
        target_ids=target_ids,
        journal_hook=journal_hook,
    )
    performance = config.canvas.performance_settings().to_dict()
    host_payload = resolved_host_config.to_dict()

    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("ritualistMockMode", mock)
    engine.rootContext().setContextProperty("ritualistE2EEnabled", e2e_enabled())
    engine.rootContext().setContextProperty("ritualistCanvasHost", host_payload)
    engine.rootContext().setContextProperty("ritualistCanvasUseController", controller)
    engine.rootContext().setContextProperty("ritualistCanvasPayload", controller.payload)
    engine.rootContext().setContextProperty("ritualistCanvasEditPayload", controller.editPayload)
    engine.rootContext().setContextProperty("ritualistCanvasPerformance", performance)
    qml_resource = files("ritualist.canvas.qml").joinpath("CanvasUse.qml")
    with as_file(qml_resource) as qml_path:
        engine.load(QUrl.fromLocalFile(str(qml_path)))
        if not engine.rootObjects():
            raise RitualistError(f"Canvas Use UI failed to load: {qml_path}")
    root_window = engine.rootObjects()[0]
    applied_host = _apply_canvas_host(root_window, resolved_host_config, QApplication, Qt)
    record_event("canvas.host.ready", **applied_host)
    ready_payload = controller.payload
    ready_theme = {}
    if isinstance(ready_payload.get("canvas"), dict):
        ready_theme = dict(ready_payload["canvas"].get("theme") or {})
    ready_validation = dict(ready_theme.get("validation") or {})
    ready_accessibility = dict(ready_validation.get("accessibility") or {})
    record_event(
        "canvas.ready",
        canvas=str(canvas),
        mock=mock,
        component_count=len(document.components),
        component_ids=[component.id for component in document.components],
        component_types=[component.type for component in document.components],
        recent_activity_component_ids=[
            component.id for component in document.components if component.type == "recent.activity"
        ],
        theme_id=str(ready_theme.get("id") or ""),
        theme_valid=bool(ready_validation.get("valid")),
        theme_source=str(ready_theme.get("source") or ""),
        theme_warning_count=len(ready_validation.get("warnings") or []),
        theme_accessibility_warning_count=int(ready_accessibility.get("warning_count") or 0),
        theme_accessibility_warnings=list(ready_accessibility.get("warnings") or []),
        host=applied_host,
    )
    _record_canvas_room_opened(
        journal_hook,
        document,
        host_config=resolved_host_config,
        mock=mock,
    )
    app.aboutToQuit.connect(controller.shutdown)
    try:
        return app.exec()
    finally:
        controller.shutdown()


def _apply_canvas_host(
    window: object,
    host_config: CanvasHostConfig,
    application: object,
    qt: object,
) -> dict[str, object]:
    payload = host_config.to_dict()
    if host_config.mode.value != "desktop_work_area":
        payload["applied"] = "windowed"
        payload["monitor"] = {"selection": "window_manager"}
        payload["recovery"] = {
            "visible_exit_control": False,
            "keyboard_exit": "",
            "force_windowed_env": CANVAS_FORCE_WINDOWED_ENV,
        }
        return payload

    primary_screen = getattr(application, "primaryScreen")()
    screen_getter = getattr(window, "screen", None)
    screen = screen_getter() if callable(screen_getter) else None
    screen = screen or primary_screen
    if screen is None:
        raise RitualistError("Desktop Work-Area Canvas requires a Qt screen with available geometry.")

    work_area = screen.availableGeometry()
    screen_geometry = screen.geometry()
    window_type = getattr(qt, "WindowType")
    flags = window_type.Window | window_type.FramelessWindowHint
    set_flags = getattr(window, "setFlags", None)
    if callable(set_flags):
        set_flags(flags)
    set_geometry = getattr(window, "setGeometry", None)
    if callable(set_geometry):
        set_geometry(work_area)
    show = getattr(window, "show", None)
    if callable(show):
        show()

    payload.update(
        {
            "applied": "desktop_work_area",
            "work_area": _qt_rect_to_dict(work_area),
            "screen_geometry": _qt_rect_to_dict(screen_geometry),
            "monitor": {
                "selection": "primary",
                "name": str(_call_optional(screen, "name", "")),
            },
            "dpi": {
                "scale": _call_float(screen, "devicePixelRatio", 1.0),
                "logical_x": _call_float(screen, "logicalDotsPerInchX", 96.0),
                "logical_y": _call_float(screen, "logicalDotsPerInchY", 96.0),
                "physical_x": _call_float(screen, "physicalDotsPerInchX", 96.0),
                "physical_y": _call_float(screen, "physicalDotsPerInchY", 96.0),
            },
            "recovery": {
                "visible_exit_control": True,
                "keyboard_exit": "Escape",
                "force_windowed_env": CANVAS_FORCE_WINDOWED_ENV,
            },
            "bounds_match_work_area": True,
            "taskbar_visible": True,
        }
    )
    return payload


def _record_canvas_room_opened(
    journal: ActivityJournalHook,
    document: CanvasDocument,
    *,
    host_config: CanvasHostConfig,
    mock: bool,
) -> bool:
    payload: dict[str, object] = {
        "surface": "canvas",
        "canvas_id": document.id,
        "canvas_name": document.name,
        "host": host_config.mode.value,
        "mock": bool(mock),
    }
    room = _room_for_canvas(document.id)
    if room is not None:
        payload["room_id"] = str(getattr(room, "room_id", "") or "")
        payload["room_name"] = str(getattr(room, "name", "") or "")
    return journal.record("room_opened", **payload)


def _record_canvas_component_clicked(
    journal: ActivityJournalHook,
    document: CanvasDocument,
    component_id: str,
    action_id: str,
) -> bool:
    component = _find_canvas_component(document, component_id)
    payload: dict[str, object] = {
        "surface": "canvas",
        "canvas_id": document.id,
        "component_id": component_id,
        "component_type": str(getattr(component, "type", "") or ""),
        "action_id": action_id,
    }
    recipe_id = _component_recipe_id(component)
    if recipe_id:
        payload["recipe_id"] = recipe_id
    return journal.record("component_clicked", **payload)


def _record_canvas_shortcut_opened(
    journal: ActivityJournalHook,
    document: CanvasDocument,
    component_id: str,
    result: object,
) -> bool:
    if str(getattr(result, "status", "") or "") != "success":
        return False
    data = getattr(result, "data", None)
    if not isinstance(data, dict):
        return False
    shortcut = data.get("shortcut")
    if not isinstance(shortcut, dict):
        return False
    component = _find_canvas_component(document, component_id)
    return journal.record(
        "shortcut_opened",
        surface="canvas",
        canvas_id=document.id,
        component_id=component_id,
        component_type=str(getattr(component, "type", "") or ""),
        action_id=str(getattr(result, "action_id", "") or ""),
        kind=str(shortcut.get("kind") or ""),
        target_label=str(shortcut.get("target_label") or ""),
    )


def _find_canvas_component(document: CanvasDocument, component_id: str) -> object | None:
    for component in document.components:
        if component.id == component_id:
            return component
    return None


def _component_recipe_id(component: object | None) -> str:
    if component is None:
        return ""
    binding = getattr(component, "binding", None)
    if binding is not None and getattr(binding, "kind", None) is CanvasBindingKind.RECIPE:
        return str(getattr(binding, "reference", "") or "").strip()
    props_dict = getattr(component, "props_dict", None)
    props = props_dict() if callable(props_dict) else {}
    if not isinstance(props, dict):
        return ""
    return str(props.get("recipe_id") or "").strip()


def _room_for_canvas(canvas_id: str) -> object | None:
    try:
        from ritualist.rooms import list_rooms
    except Exception:  # noqa: BLE001 - room labels are best-effort journal metadata.
        return None
    for room in list_rooms():
        if room.canvas_id == canvas_id:
            return room
    return None


def _qt_rect_to_dict(rect: object) -> dict[str, int]:
    return {
        "x": int(rect.x()),
        "y": int(rect.y()),
        "width": int(rect.width()),
        "height": int(rect.height()),
    }


def _call_optional(obj: object, name: str, default: object) -> object:
    value = getattr(obj, name, None)
    if not callable(value):
        return default
    try:
        return value()
    except Exception:
        return default


def _call_float(obj: object, name: str, default: float) -> float:
    value = _call_optional(obj, name, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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


def _confirmation_starting_event(ritual_state: object) -> SimpleNamespace:
    state = ritual_state if isinstance(ritual_state, dict) else {}
    active = state.get("active_run") if isinstance(state.get("active_run"), dict) else {}
    confirmation = active.get("confirmation") if isinstance(active.get("confirmation"), dict) else {}
    return SimpleNamespace(
        type="confirmation.resolved",
        approved=True,
        step_index=confirmation.get("step_index"),
        step_name=confirmation.get("step_name"),
        action=confirmation.get("action"),
        message="Starting...",
    )


def _recent_activity_items(payload: dict[str, object]) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    components = payload.get("components")
    if not isinstance(components, list):
        return items
    for component in components:
        if not isinstance(component, dict) or component.get("type") != "recent.activity":
            continue
        data = component.get("data")
        if not isinstance(data, dict):
            continue
        rows = data.get("items")
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            items.append(
                {
                    "component_id": str(component.get("id") or ""),
                    "run_id": str(row.get("run_id") or ""),
                    "recipe_id": str(row.get("recipe_id") or ""),
                    "status": str(row.get("status") or ""),
                    "message": str(row.get("message") or ""),
                    "stopped_reason": str(row.get("stopped_reason") or ""),
                }
            )
    return items


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
