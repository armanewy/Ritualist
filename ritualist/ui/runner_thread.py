from __future__ import annotations

from threading import Event

from PySide6.QtCore import QThread, Signal

from ritualist.executor import WorkflowExecutor
from ritualist.runtime_control import RuntimeControl, RuntimeStoppedError


class RunnerThread(QThread):
    log_message = Signal(str)
    step_event = Signal(object)
    run_state_changed = Signal(str)
    stopped = Signal(str)
    failed = Signal(str)
    finished_result = Signal(object)
    confirmation_requested = Signal(object)

    def __init__(
        self,
        executor: WorkflowExecutor,
        recipe,
        control: RuntimeControl | None = None,
    ) -> None:
        super().__init__()
        self.executor = executor
        self.recipe = recipe
        self.control = control or RuntimeControl()
        self._confirmation_event = Event()
        self._confirmation_result = False

    def run(self) -> None:
        self.executor.confirmer = self._confirm
        stop_requested = getattr(self.executor, "stop_requested", lambda: False)
        self.executor.stop_requested = lambda: self.control.is_stopping() or stop_requested()

        def status_callback(event) -> None:
            if event.status == "running":
                self._runtime_checkpoint(event)
                run_state = self._run_state_for_event(event)
                if run_state is not None:
                    self._record_run_state(run_state, event=event)
                    self.run_state_changed.emit(run_state)
            self.log_message.emit(
                f"{event.index}/{event.total} {event.status}: {event.step_name}"
                + (f" - {event.message}" if event.message else "")
            )
            self.step_event.emit(event)

        self.executor.status_callback = status_callback
        try:
            summary = self.executor.run(self.recipe)
        except RuntimeStoppedError as exc:
            self._finish_run_logger(success=False)
            self.run_state_changed.emit("stopped")
            self.stopped.emit(str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - report any worker failure to GUI.
            self.failed.emit(str(exc))
            return
        self.finished_result.emit(summary)

    def pause(self) -> None:
        self.control.pause()

    def resume(self) -> None:
        self.control.resume()

    def stop(self) -> None:
        self.control.stop()
        self.requestInterruption()
        self.answer_confirmation(False)

    def answer_confirmation(self, accepted: bool) -> None:
        self._confirmation_result = accepted
        self._confirmation_event.set()

    def _confirm(self, prompt: str) -> bool:
        self._confirmation_event.clear()
        self._record_run_state("confirming")
        self.run_state_changed.emit("confirming")
        self.confirmation_requested.emit(prompt)
        while not self._confirmation_event.wait(timeout=5):
            heartbeat = getattr(self.executor.run_logger, "heartbeat", None)
            if heartbeat is not None:
                heartbeat()
            self.control.raise_if_stopped()
        self._record_run_state("running")
        self.run_state_changed.emit("running")
        return self._confirmation_result

    def _runtime_checkpoint(self, event) -> None:
        self.control.raise_if_stopped()
        if not self.control.is_paused():
            return
        self._record_run_state("paused", event=event)
        self.run_state_changed.emit("paused")
        self.control.wait_if_paused()
        resumed_state = self._run_state_for_event(event) or "running"
        self._record_run_state(resumed_state, event=event)
        self.run_state_changed.emit(resumed_state)

    def _record_run_state(self, state: str, *, event=None) -> None:
        run_logger = getattr(self.executor, "run_logger", None)
        if run_logger is None:
            return
        metadata = None
        if event is not None:
            metadata = {
                "step_index": event.index,
                "step_name": event.step_name,
                "action": event.action,
            }
        record_run_state = getattr(run_logger, "record_run_state", None)
        if record_run_state is not None:
            record_run_state(
                state,
                event="run.state_changed",
                metadata=metadata,
            )
        if state == "paused":
            set_paused_metadata = getattr(run_logger, "set_paused_metadata", None)
            if set_paused_metadata is not None:
                set_paused_metadata({"reason": "user", **(metadata or {})})

    def _finish_run_logger(self, *, success: bool) -> None:
        run_logger = getattr(self.executor, "run_logger", None)
        finish = getattr(run_logger, "finish", None)
        if finish is not None:
            try:
                finish(success=success, final_state="success" if success else "stopped")
            except TypeError:
                finish(success=success)

    def _run_state_for_event(self, event) -> str | None:
        if event.status != "running":
            return None
        if event.action == "window.wait" or str(event.action).startswith("wait."):
            return "waiting"
        return "running"
