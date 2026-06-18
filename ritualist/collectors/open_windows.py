from __future__ import annotations

from dataclasses import dataclass

from ritualist.activity_collectors import ActivityCollectionContext, OpenWindowsCollector
from ritualist.activity_signals import (
    OPEN_WINDOWS_SOURCE_ID,
    WINDOW_METADATA_KIND,
    ActivityCollectionResult,
    ActivitySignal,
    window_metadata_signal,
)


@dataclass(frozen=True)
class OpenWindowsAppsCollector:
    include_processes: bool = False
    include_windows: bool = True
    include_window_titles: bool = False
    max_processes: int = 20
    max_windows: int = 20
    collector_id: str = OPEN_WINDOWS_SOURCE_ID

    def collect(
        self,
        *,
        context: ActivityCollectionContext | None = None,
    ) -> ActivityCollectionResult:
        delegate = OpenWindowsCollector(
            include_processes=self.include_processes,
            include_windows=self.include_windows,
            max_processes=max(0, int(self.max_processes)),
            max_windows=max(0, int(self.max_windows)),
            collector_id=self.collector_id,
        )
        result = delegate.collect(context=context)
        return ActivityCollectionResult(
            collector_id=self.collector_id,
            signals=tuple(
                _sanitize_window_signal(signal, include_title=self.include_window_titles)
                for signal in result.signals
            ),
            warnings=result.warnings,
            supported=result.supported,
        )


def _sanitize_window_signal(signal: ActivitySignal, *, include_title: bool) -> ActivitySignal:
    if include_title or signal.kind != WINDOW_METADATA_KIND:
        return signal

    metadata = dict(signal.metadata)
    app_name = str(metadata.get("app_name") or "").strip()
    process_name = str(metadata.get("process_name") or signal.value or "").strip()
    foreground = metadata.get("foreground")
    safe_label = app_name or process_name or "Open window"

    return window_metadata_signal(
        title=safe_label,
        app_name=app_name,
        process_name=process_name,
        foreground=foreground if isinstance(foreground, bool) else None,
    )


__all__ = ["OpenWindowsAppsCollector"]
