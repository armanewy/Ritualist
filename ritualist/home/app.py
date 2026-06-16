from __future__ import annotations

import sys
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError
from collections.abc import Sequence
from importlib.resources import as_file, files
from pathlib import Path
from threading import Event
from typing import Any

from ritualist.config import load_app_config
from ritualist.errors import DependencyMissingError, RitualistError
from ritualist.home.actions import (
    HomeActionDispatcher,
    HomeActionService,
    HomeCardAction,
    home_event_from_runtime,
    home_event_from_step_status,
)
from ritualist.home.fake_events import FakeHomeStatusEmitter
from ritualist.home.models import (
    HomeCardStatus,
    HomeEventBridge,
    HomeModel,
    HomeRuntimeEvent,
    create_installed_home_model,
    create_mock_home_model,
)


def run_home(*, mock: bool = False) -> int:
    """Launch the QML Home surface.

    PySide imports stay inside this launcher so the rest of Ritualist remains
    usable without GUI dependencies installed.
    """
    try:
        from PySide6.QtCore import Property, QObject, QTimer, QUrl, Signal, Slot
        from PySide6.QtGui import QDesktopServices, QGuiApplication
        from PySide6.QtQml import QQmlApplicationEngine
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        raise DependencyMissingError("Home UI requires PySide6; install ritualist[gui]") from exc

    class HomeController(QObject):
        payloadChanged = Signal()
        metricsChanged = Signal()
        installedModelLoaded = Signal(object)
        installedModelLoadFailed = Signal(str)
        actionStateChanged = Signal()
        confirmationChanged = Signal()
        actionCompleted = Signal(str, object)
        actionFailed = Signal(str, str)
        runtimeEventReceived = Signal(str, object)
        statusEventReceived = Signal(str, object)
        confirmationRequested = Signal(str, object)

        def __init__(
            self,
            model: HomeModel,
            bridge: HomeEventBridge,
            *,
            mock: bool,
            overlay_controller: Any | None,
        ) -> None:
            super().__init__()
            self._model = model
            self._bridge = bridge
            self._mock = mock
            self._last_event_label = "No mock events yet" if mock else "Loading recipes"
            self._loader_executor: ThreadPoolExecutor | None = None
            self._loader_future: Future[HomeModel] | None = None
            self._action_future: Future[object] | None = None
            self._dispatcher = HomeActionDispatcher(
                HomeActionService(overlay_controller=overlay_controller)
            )
            self._action_busy = False
            self._confirmation_pending = False
            self._confirmation_prompt = ""
            self._confirmation_event = Event()
            self._confirmation_result = False
            self._runtime_control: Any | None = None
            self._runtime_paused = False
            self.installedModelLoaded.connect(self._replace_model)
            self.installedModelLoadFailed.connect(self._mark_load_failed)
            self.actionCompleted.connect(self._complete_action)
            self.actionFailed.connect(self._mark_action_failed)
            self.runtimeEventReceived.connect(self._apply_runtime_event)
            self.statusEventReceived.connect(self._apply_status_event)
            self.confirmationRequested.connect(self._request_confirmation)

        @Property("QVariantMap", notify=payloadChanged)
        def payload(self) -> dict[str, object]:
            return self._model.to_qml()

        @Property(int, notify=metricsChanged)
        def updatesApplied(self) -> int:
            return self._bridge.applied_count

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

        @Property(bool, notify=confirmationChanged)
        def confirmationPending(self) -> bool:
            return self._confirmation_pending

        @Property(str, notify=confirmationChanged)
        def confirmationPrompt(self) -> str:
            return self._confirmation_prompt

        @Slot()
        def drainMockEvents(self) -> None:
            self._apply_events(self._bridge.apply_due())

        @Slot()
        def flushMockEvents(self) -> None:
            self._apply_events(self._bridge.flush())

        @Slot()
        def loadInstalledRecipes(self) -> None:
            if self._loader_future is not None and not self._loader_future.done():
                return
            executor = self._ensure_worker_executor()
            self._last_event_label = "Loading installed recipes"
            self.metricsChanged.emit()
            future = executor.submit(create_installed_home_model, categories=config.home.categories)
            self._loader_future = future
            future.add_done_callback(self._complete_installed_recipe_load)

        @Slot()
        def shutdown(self) -> None:
            if self._runtime_control is not None:
                self._runtime_control.stop()
            self.answerConfirmation(False)
            if self._action_future is not None and not self._action_future.done():
                try:
                    self._action_future.result(timeout=2)
                except TimeoutError:
                    pass
                except Exception:  # noqa: BLE001 - shutdown is best-effort finalization.
                    pass
            if self._loader_executor is None:
                return
            self._loader_executor.shutdown(wait=False, cancel_futures=True)
            self._loader_executor = None

        @Slot(str)
        def runCard(self, card_id: str) -> None:
            self._start_runtime_action(card_id, HomeCardAction.RUN)

        @Slot(str)
        def dryRunCard(self, card_id: str) -> None:
            self._start_runtime_action(card_id, HomeCardAction.DRY_RUN)

        @Slot(str)
        def doctorCard(self, card_id: str) -> None:
            self._start_action(card_id, HomeCardAction.DOCTOR)

        @Slot(str)
        def editRecipe(self, card_id: str) -> None:
            self._start_action(card_id, HomeCardAction.EDIT_RECIPE)

        @Slot(str)
        def openLogs(self, card_id: str) -> None:
            self._start_action(card_id, HomeCardAction.OPEN_LOGS)

        @Slot()
        def stopCurrentRun(self) -> None:
            if self._runtime_control is None:
                self._last_event_label = "No runtime run is active"
                self.metricsChanged.emit()
                return
            self._runtime_control.stop()
            self.answerConfirmation(False)
            self._runtime_paused = False
            self._last_event_label = "Stopping current run"
            self.actionStateChanged.emit()
            self.metricsChanged.emit()

        @Slot()
        def pauseCurrentRun(self) -> None:
            if self._runtime_control is None:
                self._last_event_label = "No runtime run is active"
                self.metricsChanged.emit()
                return
            self._runtime_control.pause()
            self._runtime_paused = True
            self._last_event_label = "Pausing current run"
            self.actionStateChanged.emit()
            self.metricsChanged.emit()

        @Slot()
        def resumeCurrentRun(self) -> None:
            if self._runtime_control is None:
                self._last_event_label = "No runtime run is active"
                self.metricsChanged.emit()
                return
            self._runtime_control.resume()
            self._runtime_paused = False
            self._last_event_label = "Resuming current run"
            self.actionStateChanged.emit()
            self.metricsChanged.emit()

        @Slot(bool)
        def answerConfirmation(self, accepted: bool) -> None:
            self._confirmation_result = accepted
            self._confirmation_pending = False
            self._confirmation_prompt = ""
            self._confirmation_event.set()
            self.confirmationChanged.emit()

        def _apply_events(self, events: Sequence[HomeRuntimeEvent]) -> None:
            if not events:
                return
            latest = events[-1]
            status_label = latest.status.value if latest.status is not None else "updated"
            self._last_event_label = f"{latest.card_id}: {status_label}"
            self.payloadChanged.emit()
            self.metricsChanged.emit()

        def _start_runtime_action(self, card_id: str, action: HomeCardAction) -> None:
            if self._action_guard(card_id, action):
                return
            from ritualist.runtime_control import RuntimeControl

            self._runtime_control = RuntimeControl()
            self._runtime_paused = False
            self._set_action_busy(True)
            label = "Dry run" if action is HomeCardAction.DRY_RUN else "Run"
            self._publish_event(
                HomeRuntimeEvent(
                    card_id=card_id,
                    status=HomeCardStatus.RUNNING,
                    subtitle=f"{label} starting",
                    description="Runtime worker started",
                    keep_open_active=False,
                    wait_action="",
                    wait_target="",
                    wait_started_at="",
                    wait_elapsed_seconds="",
                    wait_timeout_seconds="",
                )
            )
            future = self._ensure_worker_executor().submit(
                self._run_runtime_action,
                card_id,
                action,
                self._runtime_control,
            )
            self._action_future = future
            future.add_done_callback(lambda completed: self._complete_action_future(card_id, completed))

        def _start_action(self, card_id: str, action: HomeCardAction) -> None:
            if self._action_guard(card_id, action):
                return
            self._set_action_busy(True)
            if action is HomeCardAction.DOCTOR:
                self._publish_event(
                    HomeRuntimeEvent(
                        card_id=card_id,
                        status=HomeCardStatus.RUNNING,
                        subtitle="Doctor running",
                        description="Checking recipe compatibility",
                    )
                )
            future = self._ensure_worker_executor().submit(self._dispatcher.dispatch, action, card_id)
            self._action_future = future
            future.add_done_callback(lambda completed: self._complete_action_future(card_id, completed))

        def _run_runtime_action(self, card_id: str, action: HomeCardAction, control: object) -> object:
            return self._dispatcher.dispatch(
                action,
                card_id,
                runtime_event_callback=lambda event: self.runtimeEventReceived.emit(card_id, event),
                status_callback=lambda event: self.statusEventReceived.emit(card_id, event),
                confirmer=lambda prompt: self._confirm(card_id, prompt),
                control=control,
            )

        def _confirm(self, card_id: str, prompt: object) -> bool:
            self._confirmation_event.clear()
            self.confirmationRequested.emit(card_id, prompt)
            while not self._confirmation_event.wait(timeout=5):
                if self._runtime_control is not None:
                    self._runtime_control.raise_if_stopped()
            return self._confirmation_result

        def _complete_action_future(self, card_id: str, future: Future[object]) -> None:
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001 - report worker failures to Home.
                self.actionFailed.emit(card_id, str(exc))
                return
            self.actionCompleted.emit(card_id, result)

        def _ensure_worker_executor(self) -> ThreadPoolExecutor:
            if self._loader_executor is None:
                self._loader_executor = ThreadPoolExecutor(
                    max_workers=2,
                    thread_name_prefix="ritualist-home-worker",
                )
            return self._loader_executor

        def _action_guard(self, card_id: str, action: HomeCardAction) -> bool:
            if self._mock:
                self._last_event_label = f"{action.value} is disabled in mock mode"
                self.metricsChanged.emit()
                return True
            if self._action_busy:
                self._last_event_label = "Another Home action is still running"
                self.metricsChanged.emit()
                return True
            if not card_id:
                self._last_event_label = "No recipe card selected"
                self.metricsChanged.emit()
                return True
            return False

        def _publish_event(self, event: HomeRuntimeEvent) -> None:
            self._bridge.queue_runtime_event(event)
            self._apply_events(self._bridge.flush())

        def _set_action_busy(self, busy: bool) -> None:
            if self._action_busy == busy:
                return
            self._action_busy = busy
            self.actionStateChanged.emit()

        def _complete_installed_recipe_load(self, future: Future[HomeModel]) -> None:
            try:
                model = future.result()
            except Exception as exc:  # noqa: BLE001 - report best-effort Home load failures.
                self.installedModelLoadFailed.emit(str(exc))
                return
            self.installedModelLoaded.emit(model)

        @Slot(object)
        def _replace_model(self, model: object) -> None:
            if not isinstance(model, HomeModel):
                return
            self._model = model
            self._bridge.replace_model(model)
            self._last_event_label = f"{len(model.cards)} installed recipes"
            self.payloadChanged.emit()
            self.metricsChanged.emit()

        @Slot(str)
        def _mark_load_failed(self, message: str) -> None:
            self._last_event_label = f"Home load failed: {message}"
            self.metricsChanged.emit()

        @Slot(str, object)
        def _complete_action(self, card_id: str, outcome: object) -> None:
            action = getattr(outcome, "action", None)
            if action is HomeCardAction.DOCTOR:
                report = getattr(outcome, "result", None)
                compatibility = str(getattr(report, "compatibility", "complete"))
                status = _doctor_status(compatibility)
                self._publish_event(
                    HomeRuntimeEvent(
                        card_id=card_id,
                        status=status,
                        subtitle=f"Doctor: {compatibility}",
                        description=_doctor_summary(report),
                    )
                )
            elif action in {HomeCardAction.EDIT_RECIPE, HomeCardAction.OPEN_LOGS}:
                path = getattr(outcome, "path", None)
                if isinstance(path, Path):
                    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
                    self._last_event_label = f"Opened {path}"
                    self.metricsChanged.emit()
                else:
                    self._last_event_label = "Path could not be resolved"
                    self.metricsChanged.emit()
            else:
                self._last_event_label = f"{card_id}: action finished"
                self.metricsChanged.emit()
            self._runtime_control = None
            self._runtime_paused = False
            self.actionStateChanged.emit()
            self._set_action_busy(False)

        @Slot(str, str)
        def _mark_action_failed(self, card_id: str, message: str) -> None:
            self._publish_event(
                HomeRuntimeEvent(
                    card_id=card_id,
                    status=HomeCardStatus.FAILED,
                    subtitle="Action failed",
                    description=message,
                )
            )
            self._runtime_control = None
            self._runtime_paused = False
            self.actionStateChanged.emit()
            self._set_action_busy(False)

        @Slot(str, object)
        def _apply_runtime_event(self, card_id: str, event: object) -> None:
            home_event = home_event_from_runtime(card_id, event)
            if home_event is not None:
                self._publish_event(home_event)

        @Slot(str, object)
        def _apply_status_event(self, card_id: str, event: object) -> None:
            self._publish_event(home_event_from_step_status(card_id, event))

        @Slot(str, object)
        def _request_confirmation(self, card_id: str, prompt: object) -> None:
            from ritualist.overlay import format_confirmation_request

            self._confirmation_pending = True
            self._confirmation_prompt = format_confirmation_request(prompt)
            self.confirmationChanged.emit()
            self._publish_event(
                HomeRuntimeEvent(
                    card_id=card_id,
                    status=HomeCardStatus.WARNING,
                    subtitle="Confirmation required",
                    description=self._confirmation_prompt,
                )
            )

    config = load_app_config()
    app = QGuiApplication.instance() or QApplication(sys.argv)
    overlay_controller = None if mock else _create_overlay_controller()
    model = (
        create_mock_home_model(config.home.categories)
        if mock
        else HomeModel(categories=config.home.categories)
    )
    bridge = HomeEventBridge(model, target_hz=30.0)
    controller = HomeController(model, bridge, mock=mock, overlay_controller=overlay_controller)
    emitter = FakeHomeStatusEmitter(bridge.queue_runtime_event) if mock else None

    drain_timer = QTimer(controller)
    drain_timer.setInterval(max(1, round(bridge.interval_seconds * 1000)))
    drain_timer.timeout.connect(controller.drainMockEvents)

    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("ritualistMockMode", mock)
    engine.rootContext().setContextProperty("ritualistHomePayload", model.to_qml())
    engine.rootContext().setContextProperty("ritualistHomeController", controller)

    qml_resource = files("ritualist.home.qml").joinpath("Home.qml")
    with as_file(qml_resource) as qml_path:
        engine.load(QUrl.fromLocalFile(str(qml_path)))
        if not engine.rootObjects():
            raise RitualistError(f"Home UI failed to load: {qml_path}")

    if emitter is not None:
        drain_timer.start()
        emitter.start()
        app.aboutToQuit.connect(emitter.stop)
    else:
        QTimer.singleShot(0, controller.loadInstalledRecipes)
    app.aboutToQuit.connect(controller.shutdown)
    try:
        return app.exec()
    finally:
        if emitter is not None:
            emitter.stop()
        controller.shutdown()


def _doctor_summary(report: object) -> str:
    errors = getattr(report, "errors_count", None)
    warnings = getattr(report, "warnings_count", None)
    if errors is not None and warnings is not None:
        return f"{errors} errors, {warnings} warnings"
    return "Doctor completed"


def _doctor_status(compatibility: str) -> HomeCardStatus:
    if compatibility == "compatible":
        return HomeCardStatus.SUCCESS
    if compatibility == "incompatible":
        return HomeCardStatus.FAILED
    return HomeCardStatus.WARNING


def _create_overlay_controller() -> object | None:
    try:
        from ritualist.ui.overlay import QtOverlayController
    except Exception:  # noqa: BLE001 - Home remains usable if overlay setup is unavailable.
        return None
    try:
        return QtOverlayController()
    except Exception:  # noqa: BLE001 - visual trust remains best-effort.
        return None
