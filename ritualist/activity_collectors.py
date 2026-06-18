from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from .activity_signals import (
    OPEN_WINDOWS_SOURCE_ID,
    RECENT_ITEMS_SOURCE_ID,
    RITUALIST_JOURNAL_SOURCE_ID,
    ActivityCollectionResult,
    ActivitySignal,
    ActivityWarning,
    journal_event_signal,
    normalize_activity_id,
    process_name_signal,
    recent_reference_signal,
    window_metadata_signal,
)


@dataclass(frozen=True)
class ActivityCollectionContext:
    max_signals: int = 50

    def __post_init__(self) -> None:
        object.__setattr__(self, "max_signals", max(0, int(self.max_signals)))


class ActivityCollector(Protocol):
    collector_id: str

    def collect(
        self,
        *,
        context: ActivityCollectionContext | None = None,
    ) -> ActivityCollectionResult:
        """Collect activity signals once, on demand."""


@dataclass
class FakeActivityCollector:
    collector_id: str
    signals: Sequence[ActivitySignal] = ()
    warnings: Sequence[ActivityWarning] = ()
    supported: bool = True
    collect_count: int = 0

    def collect(
        self,
        *,
        context: ActivityCollectionContext | None = None,
    ) -> ActivityCollectionResult:
        self.collect_count += 1
        return ActivityCollectionResult(
            collector_id=self.collector_id,
            signals=tuple(self.signals),
            warnings=tuple(self.warnings),
            supported=self.supported,
        )


@dataclass
class FakeRitualistJournalCollector:
    events: Sequence[Mapping[str, Any]] = ()
    collector_id: str = RITUALIST_JOURNAL_SOURCE_ID
    collect_count: int = 0

    def collect(
        self,
        *,
        context: ActivityCollectionContext | None = None,
    ) -> ActivityCollectionResult:
        self.collect_count += 1
        signals = [
            journal_event_signal(
                label=event.get("recipe_name") or event.get("recipe_id") or event.get("run_id") or "",
                value=event.get("status") or "",
                metadata=_journal_metadata(event),
            )
            for event in self.events
        ]
        return ActivityCollectionResult(collector_id=self.collector_id, signals=tuple(signals))


@dataclass
class FakeOpenAppsCollector:
    process_names: Sequence[str] = ()
    windows: Sequence[Mapping[str, Any]] = ()
    collector_id: str = OPEN_WINDOWS_SOURCE_ID
    collect_count: int = 0

    def collect(
        self,
        *,
        context: ActivityCollectionContext | None = None,
    ) -> ActivityCollectionResult:
        self.collect_count += 1
        signals: list[ActivitySignal] = [process_name_signal(name) for name in self.process_names]
        for window in self.windows:
            signals.append(
                window_metadata_signal(
                    title=window.get("title") or window.get("window_title") or "",
                    app_name=window.get("app_name") or "",
                    process_name=window.get("process_name") or "",
                    foreground=window.get("foreground")
                    if isinstance(window.get("foreground"), bool)
                    else None,
                )
            )
        return ActivityCollectionResult(collector_id=self.collector_id, signals=tuple(signals))


@dataclass
class FakeRecentReferencesCollector:
    references: Sequence[Mapping[str, Any]] = ()
    collector_id: str = RECENT_ITEMS_SOURCE_ID
    collect_count: int = 0

    def collect(
        self,
        *,
        context: ActivityCollectionContext | None = None,
    ) -> ActivityCollectionResult:
        self.collect_count += 1
        signals = [
            recent_reference_signal(
                reference_type=reference.get("type") or reference.get("reference_type") or "",
                label=reference.get("label") or reference.get("name") or "",
                target=reference.get("target") or reference.get("path") or "",
            )
            for reference in self.references
        ]
        return ActivityCollectionResult(collector_id=self.collector_id, signals=tuple(signals))


@dataclass(frozen=True)
class RitualistJournalCollector:
    limit: int = 10
    base_dir: Path | None = None
    collector_id: str = RITUALIST_JOURNAL_SOURCE_ID

    def collect(
        self,
        *,
        context: ActivityCollectionContext | None = None,
    ) -> ActivityCollectionResult:
        try:
            from .run_logs import list_recent_runs

            records = list_recent_runs(limit=max(0, self.limit), base_dir=self.base_dir)
        except Exception as exc:
            return ActivityCollectionResult(
                collector_id=self.collector_id,
                warnings=(
                    ActivityWarning(
                        code="journal_unavailable",
                        source_id=RITUALIST_JOURNAL_SOURCE_ID,
                        message=f"Ritualist journal events are unavailable: {exc}",
                    ),
                ),
            )

        signals = [
            journal_event_signal(
                label=record.metadata.get("recipe_name")
                or record.metadata.get("recipe_id")
                or record.run_id,
                value=record.metadata.get("status") or "",
                metadata=_journal_metadata(record.metadata, run_id=record.run_id),
            )
            for record in records
        ]
        return ActivityCollectionResult(collector_id=self.collector_id, signals=tuple(signals))


@dataclass(frozen=True)
class OpenWindowsCollector:
    include_processes: bool = False
    include_windows: bool = True
    max_processes: int = 50
    max_windows: int = 50
    collector_id: str = OPEN_WINDOWS_SOURCE_ID

    def collect(
        self,
        *,
        context: ActivityCollectionContext | None = None,
    ) -> ActivityCollectionResult:
        if sys.platform != "win32":
            return ActivityCollectionResult.unsupported(
                collector_id=self.collector_id,
                source_id=OPEN_WINDOWS_SOURCE_ID,
                message="Open app/window collection is only available on Windows.",
            )

        warnings: list[ActivityWarning] = []
        signals: list[ActivitySignal] = []
        if self.include_processes:
            process_signals, process_warnings = self._collect_process_names()
            signals.extend(process_signals)
            warnings.extend(process_warnings)
        if self.include_windows:
            window_signals, window_warnings = self._collect_top_level_windows()
            signals.extend(window_signals)
            warnings.extend(window_warnings)
        return ActivityCollectionResult(
            collector_id=self.collector_id,
            signals=tuple(signals),
            warnings=tuple(warnings),
        )

    def _collect_process_names(self) -> tuple[list[ActivitySignal], list[ActivityWarning]]:
        try:
            import psutil  # type: ignore[import-not-found]
        except Exception as exc:
            return (
                [],
                [
                    ActivityWarning(
                        code="process_collection_unavailable",
                        source_id=OPEN_WINDOWS_SOURCE_ID,
                        message=f"Process names are unavailable: {exc}",
                    )
                ],
            )

        signals: list[ActivitySignal] = []
        seen: set[str] = set()
        for process in psutil.process_iter(["name"]):
            name = str(process.info.get("name") or "").strip()
            normalized = name.casefold()
            if not name or normalized in seen:
                continue
            seen.add(normalized)
            signals.append(process_name_signal(name))
            if len(signals) >= max(0, self.max_processes):
                break
        return signals, []

    def _collect_top_level_windows(self) -> tuple[list[ActivitySignal], list[ActivityWarning]]:
        try:
            import win32gui  # type: ignore[import-not-found]
            import win32process  # type: ignore[import-not-found]

            try:
                import psutil  # type: ignore[import-not-found]
            except Exception:
                psutil = None
        except Exception as exc:
            return (
                [],
                [
                    ActivityWarning(
                        code="window_collection_unavailable",
                        source_id=OPEN_WINDOWS_SOURCE_ID,
                        message=f"Top-level windows are unavailable: {exc}",
                    )
                ],
            )

        foreground_hwnd = win32gui.GetForegroundWindow()
        signals: list[ActivitySignal] = []

        def enum_window(hwnd: int, _extra: object) -> bool:
            if len(signals) >= max(0, self.max_windows):
                return False
            if not win32gui.IsWindowVisible(hwnd):
                return True
            title = str(win32gui.GetWindowText(hwnd) or "").strip()
            if not title:
                return True
            process_name = ""
            if psutil is not None:
                try:
                    _thread_id, process_id = win32process.GetWindowThreadProcessId(hwnd)
                    process_name = str(psutil.Process(process_id).name() or "")
                except Exception:
                    process_name = ""
            signals.append(
                window_metadata_signal(
                    title=title,
                    process_name=process_name,
                    foreground=hwnd == foreground_hwnd,
                )
            )
            return True

        win32gui.EnumWindows(enum_window, None)
        return signals, []


def collect_activity_signals(
    collectors: Sequence[ActivityCollector],
    *,
    context: ActivityCollectionContext | None = None,
) -> ActivityCollectionResult:
    resolved_context = context or ActivityCollectionContext()
    signals: list[ActivitySignal] = []
    warnings: list[ActivityWarning] = []
    supported = True

    for collector in collectors:
        collector_id = normalize_activity_id(getattr(collector, "collector_id", "activity_collector"))
        try:
            result = collector.collect(context=resolved_context)
        except Exception as exc:
            supported = False
            warnings.append(
                ActivityWarning(
                    code="collector_failed",
                    source_id=collector_id,
                    message=f"Activity collector failed: {exc}",
                )
            )
            continue

        supported = supported and result.supported
        signals.extend(result.signals)
        warnings.extend(result.warnings)

    limit = resolved_context.max_signals
    if limit >= 0 and len(signals) > limit:
        signals = signals[:limit]
        warnings.append(
            ActivityWarning(
                code="activity_signals_truncated",
                message=f"Activity signals were truncated to {limit} item(s).",
            )
        )

    return ActivityCollectionResult(
        collector_id="activity_collection",
        signals=tuple(signals),
        warnings=tuple(warnings),
        supported=supported,
    )


def _journal_metadata(raw: Mapping[str, Any], *, run_id: str = "") -> dict[str, object]:
    metadata: dict[str, object] = {}
    for key in (
        "recipe_id",
        "recipe_name",
        "status",
        "stopped_reason",
        "started_at",
        "ended_at",
        "final_state",
        "last_step_name",
    ):
        value = raw.get(key)
        if value is not None:
            metadata[key] = value
    if run_id:
        metadata["run_id"] = run_id
    return metadata


__all__ = [
    "ActivityCollectionContext",
    "ActivityCollector",
    "FakeActivityCollector",
    "FakeOpenAppsCollector",
    "FakeRecentReferencesCollector",
    "FakeRitualistJournalCollector",
    "OpenWindowsCollector",
    "RitualistJournalCollector",
    "collect_activity_signals",
]
