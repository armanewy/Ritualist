from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

LEARNING_CONSENT_VERSION = "local-learning-v1"

RITUALIST_JOURNAL_SOURCE_ID = "ritualist_journal"
OPEN_WINDOWS_SOURCE_ID = "open_windows"
RECENT_ITEMS_SOURCE_ID = "recent_items"

ALLOWED_LEARNING_SOURCE_IDS = (
    RITUALIST_JOURNAL_SOURCE_ID,
    OPEN_WINDOWS_SOURCE_ID,
    RECENT_ITEMS_SOURCE_ID,
)

FORBIDDEN_LEARNING_SOURCE_IDS = frozenset(
    {
        "watch_me",
        "watchme",
        "watch-me",
        "teach_by_watching",
        "teach-by-watching",
        "browser_history",
        "browser-history",
        "history",
        "recall",
        "windows_recall",
        "screenshots",
        "screenshot",
        "screen_capture",
        "screen-capture",
        "ocr",
        "recording",
        "recorder",
        "screen_recording",
        "screen-recording",
        "keylogging",
        "keylogger",
        "keys",
        "keystrokes",
        "click_coordinates",
        "click-coordinates",
        "coordinates",
        "coordinate_capture",
        "coordinate-capture",
    }
)


@dataclass(frozen=True)
class LearningSource:
    id: str
    label: str
    description: str
    enabled_by_default: bool = False
    background_collection: bool = False


_SOURCE_REGISTRY: dict[str, LearningSource] = {
    RITUALIST_JOURNAL_SOURCE_ID: LearningSource(
        id=RITUALIST_JOURNAL_SOURCE_ID,
        label="Ritualist journal",
        description="Local Ritualist run summaries and user-authored notes.",
    ),
    OPEN_WINDOWS_SOURCE_ID: LearningSource(
        id=OPEN_WINDOWS_SOURCE_ID,
        label="Open windows",
        description="Current top-level app/window names observed only during explicit use.",
    ),
    RECENT_ITEMS_SOURCE_ID: LearningSource(
        id=RECENT_ITEMS_SOURCE_ID,
        label="Recent items",
        description="Local recent Ritualist Rooms, shortcuts, and recipes.",
    ),
}


def normalize_learning_source_id(source_id: object) -> str:
    value = str(source_id or "").strip().casefold()
    return value.replace("-", "_").replace(" ", "_")


def learning_source_registry() -> dict[str, LearningSource]:
    return dict(_SOURCE_REGISTRY)


def get_learning_source(source_id: object) -> LearningSource | None:
    return _SOURCE_REGISTRY.get(normalize_learning_source_id(source_id))


def is_forbidden_learning_source(source_id: object) -> bool:
    normalized = normalize_learning_source_id(source_id)
    return normalized in {
        normalize_learning_source_id(item) for item in FORBIDDEN_LEARNING_SOURCE_IDS
    }


def filter_allowed_learning_sources(source_ids: Iterable[object]) -> tuple[str, ...]:
    selected: list[str] = []
    seen: set[str] = set()
    for source_id in source_ids:
        normalized = normalize_learning_source_id(source_id)
        if normalized in seen or normalized not in _SOURCE_REGISTRY:
            continue
        seen.add(normalized)
        selected.append(normalized)
    return tuple(selected)


__all__ = [
    "ALLOWED_LEARNING_SOURCE_IDS",
    "FORBIDDEN_LEARNING_SOURCE_IDS",
    "LEARNING_CONSENT_VERSION",
    "LearningSource",
    "filter_allowed_learning_sources",
    "get_learning_source",
    "is_forbidden_learning_source",
    "learning_source_registry",
    "normalize_learning_source_id",
]
