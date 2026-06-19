from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
import time

from pydantic import BaseModel, ConfigDict, Field


class PerformanceReport(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    operation: str
    duration_ms: float = Field(ge=0)
    started_at: datetime
    ended_at: datetime
    counts: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    def to_json(self) -> str:
        return self.model_dump_json()


@contextmanager
def measure_operation(
    operation: str,
    *,
    counts: dict[str, int] | None = None,
    warnings: list[str] | None = None,
) -> Iterator[PerformanceReport]:
    started_at = _now_utc()
    started_perf = time.perf_counter()
    report = PerformanceReport(
        operation=operation,
        duration_ms=0,
        started_at=started_at,
        ended_at=started_at,
        counts=dict(counts or {}),
        warnings=list(warnings or []),
    )
    try:
        yield report
    finally:
        ended_at = _now_utc()
        report.ended_at = ended_at
        report.duration_ms = max(0, (time.perf_counter() - started_perf) * 1000)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)
