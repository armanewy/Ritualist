from __future__ import annotations

from setpiece.learning_sources import (
    ALLOWED_LEARNING_SOURCE_IDS,
    filter_allowed_learning_sources,
    get_learning_source,
    is_forbidden_learning_source,
    learning_source_registry,
)


def test_source_registry_only_exposes_allowed_v1_sources() -> None:
    registry = learning_source_registry()

    assert tuple(registry) == ALLOWED_LEARNING_SOURCE_IDS
    assert set(registry) == {"setpiece_journal", "open_windows", "recent_items"}
    assert all(source.enabled_by_default is False for source in registry.values())
    assert all(source.background_collection is False for source in registry.values())


def test_source_registry_rejects_forbidden_capture_sources() -> None:
    forbidden = (
        "watch_me",
        "Watch-Me",
        "browser_history",
        "Recall",
        "screenshots",
        "OCR",
        "recording",
        "keylogging",
        "click-coordinates",
    )

    for source_id in forbidden:
        assert get_learning_source(source_id) is None
        assert is_forbidden_learning_source(source_id) is True


def test_filter_allowed_learning_sources_ignores_unknown_and_forbidden_sources() -> None:
    assert filter_allowed_learning_sources(
        (
            "setpiece_journal",
            "watch_me",
            "open-windows",
            "screenshots",
            "recent_items",
            "browser_history",
            "open_windows",
        )
    ) == ("setpiece_journal", "open_windows", "recent_items")
