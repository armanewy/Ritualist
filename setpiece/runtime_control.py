from __future__ import annotations

import threading

from .errors import SetpieceError


class RuntimeStoppedError(SetpieceError):
    """Raised when a controlled runtime has been asked to stop."""


class RuntimeControl:
    """Thread-safe cooperative pause/resume/stop control for runtime loops."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._paused = False
        self._stopping = False

    def pause(self) -> None:
        with self._condition:
            if not self._stopping:
                self._paused = True

    def resume(self) -> None:
        with self._condition:
            self._paused = False
            self._condition.notify_all()

    def stop(self) -> None:
        with self._condition:
            self._stopping = True
            self._paused = False
            self._condition.notify_all()

    def is_paused(self) -> bool:
        with self._condition:
            return self._paused

    def is_stopping(self) -> bool:
        with self._condition:
            return self._stopping

    def wait_if_paused(self) -> None:
        with self._condition:
            self._raise_if_stopped_locked()
            self._condition.wait_for(lambda: not self._paused or self._stopping)
            self._raise_if_stopped_locked()

    def raise_if_stopped(self) -> None:
        with self._condition:
            self._raise_if_stopped_locked()

    def heartbeat(self) -> None:
        self.wait_if_paused()

    def _raise_if_stopped_locked(self) -> None:
        if self._stopping:
            raise RuntimeStoppedError("runtime stopped by request")
