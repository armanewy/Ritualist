from __future__ import annotations

from threading import Event

from PySide6.QtCore import QThread, Signal

from ritualist.executor import WorkflowExecutor


class RunnerThread(QThread):
    log_message = Signal(str)
    failed = Signal(str)
    finished_result = Signal(object)
    confirmation_requested = Signal(str)

    def __init__(self, executor: WorkflowExecutor, recipe) -> None:
        super().__init__()
        self.executor = executor
        self.recipe = recipe
        self._confirmation_event = Event()
        self._confirmation_result = False

    def run(self) -> None:
        self.executor.confirmer = self._confirm
        self.executor.status_callback = (
            lambda event: self.log_message.emit(
                f"{event.index}/{event.total} {event.status}: {event.step_name}"
                + (f" - {event.message}" if event.message else "")
            )
        )
        try:
            summary = self.executor.run(self.recipe)
        except Exception as exc:  # noqa: BLE001 - report any worker failure to GUI.
            self.failed.emit(str(exc))
            return
        self.finished_result.emit(summary)

    def answer_confirmation(self, accepted: bool) -> None:
        self._confirmation_result = accepted
        self._confirmation_event.set()

    def _confirm(self, prompt: str) -> bool:
        self._confirmation_event.clear()
        self.confirmation_requested.emit(prompt)
        self._confirmation_event.wait()
        return self._confirmation_result
