from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from ritualist.activity_collectors import ActivityCollectionContext
from ritualist.activity_signals import (
    RECENT_ITEMS_SOURCE_ID,
    ActivityCollectionResult,
    ActivitySignal,
    ActivityWarning,
    recent_reference_signal,
)


@dataclass(frozen=True)
class RecentItemsCollector:
    roots: Sequence[Path | str] = ()
    max_items: int = 20
    max_candidates_per_root: int = 100
    include_default_windows_recent: bool = True
    include_full_paths: bool = False
    collector_id: str = RECENT_ITEMS_SOURCE_ID

    def collect(
        self,
        *,
        context: ActivityCollectionContext | None = None,
    ) -> ActivityCollectionResult:
        limit = _bounded_limit(self.max_items)
        if context is not None:
            limit = min(limit, context.max_signals)
        if limit <= 0:
            return ActivityCollectionResult.empty(collector_id=self.collector_id)

        roots = _resolved_roots(
            self.roots,
            include_default_windows_recent=self.include_default_windows_recent,
        )
        if not roots:
            return ActivityCollectionResult.unsupported(
                collector_id=self.collector_id,
                source_id=RECENT_ITEMS_SOURCE_ID,
                message="Recent item collection requires configured roots or the Windows Recent folder.",
            )

        warnings: list[ActivityWarning] = []
        candidates: list[_RecentCandidate] = []
        candidate_limit = _bounded_limit(self.max_candidates_per_root)
        for root in roots:
            root_candidates, root_warnings = _collect_root_candidates(
                root,
                max_candidates=candidate_limit,
            )
            candidates.extend(root_candidates)
            warnings.extend(root_warnings)

        candidates.sort(key=lambda candidate: candidate.modified_at, reverse=True)
        signals: list[ActivitySignal] = []
        for candidate in candidates[:limit]:
            signals.append(
                recent_reference_signal(
                    reference_type=candidate.reference_type,
                    label=candidate.label,
                    target=str(candidate.path) if self.include_full_paths else candidate.label,
                )
            )

        if len(candidates) > limit:
            warnings.append(
                ActivityWarning(
                    code="recent_items_truncated",
                    source_id=RECENT_ITEMS_SOURCE_ID,
                    message=f"Recent items were truncated to {limit} item(s).",
                )
            )

        return ActivityCollectionResult(
            collector_id=self.collector_id,
            signals=tuple(signals),
            warnings=tuple(warnings),
        )


@dataclass(frozen=True)
class _RecentCandidate:
    path: Path
    label: str
    reference_type: str
    modified_at: float


def _resolved_roots(
    roots: Sequence[Path | str],
    *,
    include_default_windows_recent: bool,
) -> tuple[Path, ...]:
    explicit_roots = tuple(Path(root) for root in roots)
    if explicit_roots:
        return explicit_roots
    if not include_default_windows_recent or sys.platform != "win32":
        return ()
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return ()
    return (Path(appdata) / "Microsoft" / "Windows" / "Recent",)


def _collect_root_candidates(
    root: Path,
    *,
    max_candidates: int,
) -> tuple[list[_RecentCandidate], list[ActivityWarning]]:
    warnings: list[ActivityWarning] = []
    candidates: list[_RecentCandidate] = []
    if max_candidates <= 0:
        return candidates, warnings
    try:
        iterator = root.iterdir()
    except OSError as exc:
        return (
            candidates,
            [
                ActivityWarning(
                    code="recent_items_root_unavailable",
                    source_id=RECENT_ITEMS_SOURCE_ID,
                    message=f"Recent items root is unavailable: {root.name or root}: {exc}",
                )
            ],
        )

    try:
        for entry in iterator:
            if len(candidates) >= max_candidates:
                warnings.append(
                    ActivityWarning(
                        code="recent_items_candidates_truncated",
                        source_id=RECENT_ITEMS_SOURCE_ID,
                        message=f"Recent item candidates were capped for {root.name or root}.",
                    )
                )
                break
            candidate = _candidate_from_entry(entry)
            if candidate is not None:
                candidates.append(candidate)
    except OSError as exc:
        warnings.append(
            ActivityWarning(
                code="recent_items_root_unavailable",
                source_id=RECENT_ITEMS_SOURCE_ID,
                message=f"Recent items root is unavailable: {root.name or root}: {exc}",
            )
        )
    return candidates, warnings


def _candidate_from_entry(entry: Path) -> _RecentCandidate | None:
    try:
        stat_result = entry.stat()
    except OSError:
        return None

    label = _entry_label(entry)
    if not label:
        return None
    return _RecentCandidate(
        path=entry,
        label=label,
        reference_type=_reference_type(entry),
        modified_at=stat_result.st_mtime,
    )


def _entry_label(entry: Path) -> str:
    if entry.suffix.casefold() == ".lnk":
        return entry.stem.strip()
    if entry.suffix.casefold() in {".yaml", ".yml"}:
        return entry.stem.replace("_", " ").strip()
    return entry.name.strip()


def _reference_type(entry: Path) -> str:
    try:
        if entry.is_dir():
            return "folder"
    except OSError:
        return "file"
    if entry.suffix.casefold() in {".exe", ".appref-ms"}:
        return "app"
    return "file"


def _bounded_limit(value: int) -> int:
    try:
        resolved = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, resolved)


__all__ = ["RecentItemsCollector"]
