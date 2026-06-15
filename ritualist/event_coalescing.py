from __future__ import annotations

import time
from collections.abc import Callable, Hashable
from typing import Any


DEFAULT_TARGET_HZ = 60.0


class EventCoalescer:
    """Coalesce high-frequency keyed events into bounded update batches."""

    def __init__(
        self,
        *,
        target_hz: float = DEFAULT_TARGET_HZ,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if target_hz <= 0:
            raise ValueError("target_hz must be greater than zero")
        self._interval_seconds = 1.0 / target_hz
        self._clock = clock
        self._pending: dict[Hashable, Any] = {}
        self._last_emit_at = self._clock()

    @property
    def interval_seconds(self) -> float:
        return self._interval_seconds

    @property
    def has_pending(self) -> bool:
        return bool(self._pending)

    def put(self, key: Hashable, state: Any) -> None:
        """Store the latest state for a key until the next emit."""
        self._pending[key] = state

    def emit_due(self, *, now: float | None = None) -> dict[Hashable, Any]:
        """Return pending updates when the target interval has elapsed."""
        current_time = self._clock() if now is None else now
        if current_time - self._last_emit_at < self._interval_seconds:
            return {}
        return self.flush(now=current_time)

    def flush(self, *, now: float | None = None) -> dict[Hashable, Any]:
        """Return all pending latest states immediately."""
        current_time = self._clock() if now is None else now
        emitted = dict(self._pending)
        self._pending.clear()
        self._last_emit_at = current_time
        return emitted
