from __future__ import annotations

import sys
from collections.abc import Sequence
from importlib.resources import as_file, files

from ritualist.errors import DependencyMissingError, RitualistError
from ritualist.home.fake_events import FakeHomeStatusEmitter
from ritualist.home.models import HomeEventBridge, HomeModel, HomeRuntimeEvent, create_mock_home_model


def run_home(*, mock: bool = True) -> int:
    """Launch the QML Home surface.

    PySide imports stay inside this launcher so the rest of Ritualist remains
    usable without GUI dependencies installed.
    """
    try:
        from PySide6.QtCore import Property, QObject, QTimer, QUrl, Signal, Slot
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtQml import QQmlApplicationEngine
    except ImportError as exc:
        raise DependencyMissingError("Home UI requires PySide6; install ritualist[gui]") from exc

    class HomeController(QObject):
        payloadChanged = Signal()
        metricsChanged = Signal()

        def __init__(self, model: HomeModel, bridge: HomeEventBridge) -> None:
            super().__init__()
            self._model = model
            self._bridge = bridge
            self._last_event_label = "No mock events yet"

        @Property("QVariantMap", notify=payloadChanged)
        def payload(self) -> dict[str, object]:
            return self._model.to_qml()

        @Property(int, notify=metricsChanged)
        def updatesApplied(self) -> int:
            return self._bridge.applied_count

        @Property(str, notify=metricsChanged)
        def lastEventLabel(self) -> str:
            return self._last_event_label

        @Slot()
        def drainMockEvents(self) -> None:
            self._apply_events(self._bridge.apply_due())

        @Slot()
        def flushMockEvents(self) -> None:
            self._apply_events(self._bridge.flush())

        def _apply_events(self, events: Sequence[HomeRuntimeEvent]) -> None:
            if not events:
                return
            latest = events[-1]
            status_label = latest.status.value if latest.status is not None else "updated"
            self._last_event_label = f"{latest.card_id}: {status_label}"
            self.payloadChanged.emit()
            self.metricsChanged.emit()

    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    model = create_mock_home_model() if mock else HomeModel()
    bridge = HomeEventBridge(model, target_hz=30.0)
    controller = HomeController(model, bridge)
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
    try:
        return app.exec()
    finally:
        if emitter is not None:
            emitter.stop()
