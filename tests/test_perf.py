from __future__ import annotations

import json
from datetime import datetime, timezone

from ritualist.perf import PerformanceReport, measure_operation


def test_measure_operation_duration_is_non_negative():
    with measure_operation("home.refresh") as report:
        report.counts["recipes"] = 2

    assert report.duration_ms >= 0
    assert report.ended_at >= report.started_at


def test_performance_report_counts_serialize():
    report = PerformanceReport(
        operation="recipe.load",
        duration_ms=3.5,
        started_at=datetime(2026, 6, 15, 18, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 6, 15, 18, 0, 0, 3500, tzinfo=timezone.utc),
        counts={"recipes": 4, "warnings": 1},
    )

    payload = json.loads(report.to_json())

    assert payload["counts"] == {"recipes": 4, "warnings": 1}


def test_performance_report_warnings_serialize():
    report = PerformanceReport(
        operation="recipe.load",
        duration_ms=0,
        started_at=datetime(2026, 6, 15, 18, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 6, 15, 18, 0, tzinfo=timezone.utc),
        warnings=["Skipped malformed recipe"],
    )

    payload = json.loads(report.to_json())

    assert payload["warnings"] == ["Skipped malformed recipe"]


def test_performance_report_shape_is_stable():
    report = PerformanceReport(
        operation="home.refresh",
        duration_ms=1.25,
        started_at=datetime(2026, 6, 15, 18, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 6, 15, 18, 0, 0, 1250, tzinfo=timezone.utc),
        counts={"recipes": 7},
        warnings=["slow recipe metadata"],
    )

    payload = report.model_dump(mode="json")

    assert list(payload) == [
        "operation",
        "duration_ms",
        "started_at",
        "ended_at",
        "counts",
        "warnings",
    ]
    assert payload == {
        "operation": "home.refresh",
        "duration_ms": 1.25,
        "started_at": "2026-06-15T18:00:00Z",
        "ended_at": "2026-06-15T18:00:00.001250Z",
        "counts": {"recipes": 7},
        "warnings": ["slow recipe metadata"],
    }
