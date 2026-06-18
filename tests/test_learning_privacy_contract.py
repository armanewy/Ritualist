from __future__ import annotations

from pathlib import Path

from ritualist.learning_config import LEARNING_CONSENT_VERSION, LocalLearningConfig
from ritualist.learning_sources import (
    ALLOWED_LEARNING_SOURCE_IDS,
    filter_allowed_learning_sources,
    get_learning_source,
    is_forbidden_learning_source,
    learning_source_registry,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
LOCAL_LEARNING_DOC = REPO_ROOT / "docs" / "LOCAL_LEARNING.md"


def _local_learning_text() -> str:
    return LOCAL_LEARNING_DOC.read_text(encoding="utf-8")


def _normalized_doc_text() -> str:
    return " ".join(_local_learning_text().split())


def test_local_learning_doc_states_privacy_contract_without_ui_overclaim() -> None:
    normalized = _normalized_doc_text()

    required_phrases = (
        "Local Learning is off by default.",
        "Local Learning is local only.",
        "explicit source-level consent",
        "Users must have controls to view",
        "Users must have controls to delete",
        "Local Learning must not provide Watch Me",
        "Local Learning must not collect or ingest browser history.",
        "Local Learning must not collect screenshots, OCR text, screen recordings, keystrokes",
        "Local Learning must not auto-create",
        "Local Learning must not auto-run",
        "not a claim that a user-facing Local Learning Suggestions UI is currently shipped",
        "should not be read as evidence that a Suggestions UI has already shipped",
    )

    for phrase in required_phrases:
        assert phrase in normalized


def test_current_learning_defaults_and_sources_are_disabled_and_local() -> None:
    config = LocalLearningConfig()
    registry = learning_source_registry()

    assert config.enabled is False
    assert config.effective_enabled is False
    assert config.enabled_source_ids == ()
    assert config.background_collection is False
    assert tuple(registry) == ALLOWED_LEARNING_SOURCE_IDS
    assert tuple(registry) == ("ritualist_journal", "open_windows", "recent_items")
    assert all(source.enabled_by_default is False for source in registry.values())
    assert all(source.background_collection is False for source in registry.values())


def test_source_level_consent_limits_learning_to_explicitly_consented_sources() -> None:
    config = LocalLearningConfig.from_mapping(
        {
            "enabled": True,
            "sources": {
                "ritualist_journal": True,
                "open_windows": True,
                "recent_items": True,
            },
            "consent": {
                "timestamp": "2026-06-17T20:00:00Z",
                "version": LEARNING_CONSENT_VERSION,
                "sources": ["ritualist_journal"],
            },
        }
    )

    assert config.effective_enabled is True
    assert config.enabled_source_ids == ("ritualist_journal",)
    assert config.is_source_enabled("ritualist_journal") is True
    assert config.is_source_enabled("open_windows") is False
    assert config.is_source_enabled("recent_items") is False


def test_learning_config_ignores_auto_create_and_auto_run_inputs() -> None:
    config = LocalLearningConfig.from_mapping(
        {
            "enabled": True,
            "auto_create": True,
            "auto_run": True,
            "sources": {
                "ritualist_journal": True,
                "auto_create": True,
                "auto_run": True,
            },
            "consent": {
                "timestamp": "2026-06-17T20:00:00Z",
                "version": LEARNING_CONSENT_VERSION,
                "sources": ["ritualist_journal", "auto_create", "auto_run"],
            },
        }
    )

    serialized = config.to_dict()

    assert config.enabled_source_ids == ("ritualist_journal",)
    assert config.is_source_enabled("auto_create") is False
    assert config.is_source_enabled("auto_run") is False
    assert "auto_create" not in serialized
    assert "auto_run" not in serialized
    assert not hasattr(config, "auto_create")
    assert not hasattr(config, "auto_run")


def test_forbidden_capture_and_history_sources_are_not_learning_sources() -> None:
    forbidden_sources = (
        "watch_me",
        "watch-me",
        "teach_by_watching",
        "browser_history",
        "browser history",
        "history",
        "windows_recall",
        "screenshots",
        "screen_capture",
        "ocr",
        "screen_recording",
        "keystrokes",
        "keylogging",
        "click_coordinates",
        "coordinate_capture",
    )

    for source_id in forbidden_sources:
        assert get_learning_source(source_id) is None
        assert is_forbidden_learning_source(source_id) is True

    assert filter_allowed_learning_sources(
        ("ritualist_journal", *forbidden_sources, "open_windows", "recent_items")
    ) == ("ritualist_journal", "open_windows", "recent_items")
