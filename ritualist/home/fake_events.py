from __future__ import annotations

import threading
import time
from collections.abc import Callable, Sequence

from .models import HomeCardStatus, HomeLastRunStatus, HomeRuntimeEvent

_DEFAULT_CARD_IDS = ("gaming-001", "media-002", "coding-003", "news-004")
_STATUS_CYCLE: tuple[tuple[HomeCardStatus, str, HomeLastRunStatus | None], ...] = (
    (HomeCardStatus.RUNNING, "Mock run event stream active", None),
    (HomeCardStatus.WARNING, "Waiting on a confirmation gate", None),
    (HomeCardStatus.SUCCESS, "Mock run completed", HomeLastRunStatus.SUCCESS),
    (HomeCardStatus.READY, "Ready for local launch", None),
)


class FakeHomeStatusEmitter:
    """Emit local mock Home status events without touching runtime automation."""

    def __init__(
        self,
        callback: Callable[[HomeRuntimeEvent], None],
        *,
        card_ids: Sequence[str] = _DEFAULT_CARD_IDS,
        interval_seconds: float = 0.08,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be greater than zero")
        if not card_ids:
            raise ValueError("card_ids must not be empty")
        self._callback = callback
        self._card_ids = tuple(card_ids)
        self._interval_seconds = interval_seconds
        self._sleeper = sleeper
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._sequence = 0

    @property
    def sequence(self) -> int:
        return self._sequence

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def emit_tick(self) -> HomeRuntimeEvent:
        sequence = self._sequence
        card_id = self._card_ids[sequence % len(self._card_ids)]
        cycle_index = (sequence // len(self._card_ids)) % len(_STATUS_CYCLE)
        status, subtitle, last_run_status = _STATUS_CYCLE[cycle_index]
        event = HomeRuntimeEvent(
            card_id=card_id,
            status=status,
            subtitle=subtitle,
            description=f"Mock Home event {sequence + 1}",
            last_run_status=last_run_status,
        )
        self._sequence += 1
        self._callback(event)
        return event

    def start(self) -> None:
        if self.is_running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="ritualist-home-fake-status",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = 1.0) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=timeout)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self.emit_tick()
            self._sleeper(self._interval_seconds)
