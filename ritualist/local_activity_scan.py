from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from ritualist.activity_collectors import (
    ActivityCollectionContext,
    ActivityCollector,
    RitualistJournalCollector,
    collect_activity_signals,
)
from ritualist.activity_journal import ActivityJournal, JournalEvent
from ritualist.activity_signals import (
    OPEN_WINDOWS_SOURCE_ID,
    RECENT_ITEMS_SOURCE_ID,
    RITUALIST_JOURNAL_SOURCE_ID,
    ActivityCollectionResult,
    ActivityWarning,
    journal_event_signal,
    normalize_activity_id,
)
from ritualist.collectors.open_windows import OpenWindowsAppsCollector
from ritualist.collectors.recent_items import RecentItemsCollector


DEFAULT_LOCAL_ACTIVITY_SOURCE_IDS = (
    OPEN_WINDOWS_SOURCE_ID,
    RECENT_ITEMS_SOURCE_ID,
    RITUALIST_JOURNAL_SOURCE_ID,
)


@dataclass(frozen=True)
class LocalActivityScanRequest:
    source_ids: Sequence[str] = ()
    max_signals: int = 50
    max_open_windows: int = 20
    max_open_processes: int = 0
    max_recent_items: int = 20
    max_journal_events: int = 10
    include_window_titles: bool = False
    recent_item_roots: Sequence[Path | str] = ()
    include_default_windows_recent: bool = False
    journal: ActivityJournal | None = None
    journal_path: Path | None = None
    run_log_base_dir: Path | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_ids", _normalize_source_ids(self.source_ids))
        object.__setattr__(self, "max_signals", _bounded_limit(self.max_signals))
        object.__setattr__(self, "max_open_windows", _bounded_limit(self.max_open_windows))
        object.__setattr__(self, "max_open_processes", _bounded_limit(self.max_open_processes))
        object.__setattr__(self, "max_recent_items", _bounded_limit(self.max_recent_items))
        object.__setattr__(self, "max_journal_events", _bounded_limit(self.max_journal_events))
        object.__setattr__(
            self,
            "recent_item_roots",
            tuple(Path(root) for root in self.recent_item_roots),
        )


@dataclass(frozen=True)
class LocalActivityScan:
    request: LocalActivityScanRequest = field(default_factory=LocalActivityScanRequest)
    collectors: Sequence[ActivityCollector] | None = None

    def scan(self) -> ActivityCollectionResult:
        collectors = (
            tuple(self.collectors)
            if self.collectors is not None
            else build_local_activity_collectors(self.request)
        )
        return collect_activity_signals(
            collectors,
            context=ActivityCollectionContext(max_signals=self.request.max_signals),
        )


@dataclass(frozen=True)
class ActivityJournalCollector:
    journal: ActivityJournal | None = None
    path: Path | None = None
    limit: int = 10
    collector_id: str = RITUALIST_JOURNAL_SOURCE_ID

    def collect(
        self,
        *,
        context: ActivityCollectionContext | None = None,
    ) -> ActivityCollectionResult:
        limit = _bounded_limit(self.limit)
        if context is not None:
            limit = min(limit, context.max_signals)
        if limit <= 0:
            return ActivityCollectionResult.empty(collector_id=self.collector_id)

        journal = self.journal or ActivityJournal(path=self.path)
        try:
            events = journal.read(limit=limit)
        except Exception as exc:  # noqa: BLE001 - collectors report warnings, not crashes.
            return ActivityCollectionResult(
                collector_id=self.collector_id,
                warnings=(
                    ActivityWarning(
                        code="journal_unavailable",
                        source_id=RITUALIST_JOURNAL_SOURCE_ID,
                        message=f"Ritualist activity journal is unavailable: {exc}",
                    ),
                ),
            )

        return ActivityCollectionResult(
            collector_id=self.collector_id,
            signals=tuple(_journal_event_signal(event) for event in events),
        )


def build_local_activity_collectors(
    request: LocalActivityScanRequest | None = None,
) -> tuple[ActivityCollector, ...]:
    resolved = request or LocalActivityScanRequest()
    collectors: list[ActivityCollector] = []
    source_ids = set(resolved.source_ids)

    if OPEN_WINDOWS_SOURCE_ID in source_ids:
        collectors.append(
            OpenWindowsAppsCollector(
                include_processes=resolved.max_open_processes > 0,
                include_windows=resolved.max_open_windows > 0,
                include_window_titles=resolved.include_window_titles,
                max_processes=resolved.max_open_processes,
                max_windows=resolved.max_open_windows,
            )
        )
    if RECENT_ITEMS_SOURCE_ID in source_ids:
        collectors.append(
            RecentItemsCollector(
                roots=resolved.recent_item_roots,
                max_items=resolved.max_recent_items,
                include_default_windows_recent=resolved.include_default_windows_recent,
            )
        )
    if RITUALIST_JOURNAL_SOURCE_ID in source_ids:
        collectors.append(_journal_collector(resolved))

    return tuple(collectors)


def scan_local_activity(
    request: LocalActivityScanRequest | None = None,
    *,
    collectors: Sequence[ActivityCollector] | None = None,
) -> ActivityCollectionResult:
    return LocalActivityScan(
        request=request or LocalActivityScanRequest(),
        collectors=collectors,
    ).scan()


def _journal_collector(request: LocalActivityScanRequest) -> ActivityCollector:
    if request.journal is not None or request.journal_path is not None:
        return ActivityJournalCollector(
            journal=request.journal,
            path=request.journal_path,
            limit=request.max_journal_events,
        )
    return RitualistJournalCollector(
        limit=request.max_journal_events,
        base_dir=request.run_log_base_dir,
    )


def _journal_event_signal(event: JournalEvent):
    metadata = _journal_event_metadata(event.event_type, event.payload)
    return journal_event_signal(
        label=_journal_event_label(event.event_type, event.payload),
        value=event.event_type,
        metadata=metadata,
    )


def _journal_event_label(event_type: str, payload: Mapping[str, Any]) -> str:
    for key in ("recipe_name", "recipe_id", "shortcut_id", "room_id", "component_id"):
        value = payload.get(key)
        if value:
            return str(value)
    return event_type


def _journal_event_metadata(event_type: str, payload: Mapping[str, Any]) -> dict[str, object]:
    metadata: dict[str, object] = {"event_type": event_type}
    for key in (
        "room_id",
        "component_id",
        "shortcut_id",
        "recipe_id",
        "recipe_name",
        "status",
        "stopped_reason",
        "final_state",
        "last_step_name",
        "dry_run",
    ):
        value = payload.get(key)
        if value is not None:
            metadata[key] = value
    return metadata


def _normalize_source_ids(source_ids: Sequence[str]) -> tuple[str, ...]:
    allowed = set(DEFAULT_LOCAL_ACTIVITY_SOURCE_IDS)
    selected: list[str] = []
    seen: set[str] = set()
    for source_id in source_ids:
        normalized = normalize_activity_id(source_id)
        if normalized in allowed and normalized not in seen:
            selected.append(normalized)
            seen.add(normalized)
    return tuple(selected)


def _bounded_limit(value: int) -> int:
    try:
        resolved = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, resolved)


__all__ = [
    "DEFAULT_LOCAL_ACTIVITY_SOURCE_IDS",
    "ActivityJournalCollector",
    "LocalActivityScan",
    "LocalActivityScanRequest",
    "build_local_activity_collectors",
    "scan_local_activity",
]
