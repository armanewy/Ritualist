from __future__ import annotations

import yaml

from ritualist.config import load_app_config
from ritualist.learning_config import (
    LEARNING_CONSENT_VERSION,
    LearningConsentRecord,
    LocalLearningConfig,
)


def test_local_learning_defaults_disabled() -> None:
    config = LocalLearningConfig()

    assert config.enabled is False
    assert config.effective_enabled is False
    assert config.enabled_source_ids == ()
    assert config.background_collection is False
    assert config.is_source_enabled("ritualist_journal") is False


def test_local_learning_requires_consent_before_sources_enable() -> None:
    config = LocalLearningConfig.from_mapping(
        {
            "enabled": True,
            "sources": {
                "ritualist_journal": True,
                "open_windows": True,
                "recent_items": True,
            },
        }
    )

    assert config.enabled is True
    assert config.effective_enabled is False
    assert config.source_ids == ("ritualist_journal", "open_windows", "recent_items")
    assert config.enabled_source_ids == ()
    assert config.is_source_enabled("open_windows") is False


def test_local_learning_requires_source_level_consent() -> None:
    config = LocalLearningConfig.from_mapping(
        {
            "enabled": True,
            "sources": {
                "ritualist_journal": True,
                "open_windows": True,
                "recent_items": True,
            },
            "consent": {
                "timestamp": "2026-06-17T13:45:00Z",
                "version": LEARNING_CONSENT_VERSION,
                "sources": ["ritualist_journal", "recent_items"],
            },
            "background_collection": True,
        }
    )

    assert config.effective_enabled is True
    assert config.enabled_source_ids == ("ritualist_journal", "recent_items")
    assert config.is_source_enabled("ritualist_journal") is True
    assert config.is_source_enabled("recent-items") is True
    assert config.is_source_enabled("open_windows") is False
    assert config.background_collection is False
    assert config.consent == LearningConsentRecord(
        timestamp="2026-06-17T13:45:00Z",
        version=LEARNING_CONSENT_VERSION,
        source_ids=("ritualist_journal", "recent_items"),
    )


def test_local_learning_ignores_forbidden_and_obsolete_watch_me_config() -> None:
    config = LocalLearningConfig.from_mapping(
        {
            "enabled": True,
            "watch_me": {"enabled": True},
            "sources": {
                "ritualist_journal": True,
                "watch_me": True,
                "browser_history": True,
                "screenshots": True,
                "ocr": True,
                "recording": True,
                "keylogging": True,
                "click_coordinates": True,
            },
            "consent": {
                "timestamp": "2026-06-17T13:45:00Z",
                "version": LEARNING_CONSENT_VERSION,
                "sources": [
                    "ritualist_journal",
                    "watch_me",
                    "browser_history",
                    "screenshots",
                    "ocr",
                    "recording",
                    "keylogging",
                    "click_coordinates",
                ],
            },
        }
    )

    assert config.enabled_source_ids == ("ritualist_journal",)
    assert config.is_source_enabled("watch_me") is False
    assert not hasattr(config, "watch_me")


def test_load_app_config_reads_only_local_top_level_learning_settings(tmp_path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "packs": [
                    {
                        "name": "Shared pack",
                        "learning": {
                            "enabled": True,
                            "sources": {"open_windows": True},
                        },
                    }
                ],
                "canvas_packs": {
                    "learning": {
                        "enabled": True,
                        "sources": {"recent_items": True},
                    }
                },
                "watch_me": {"enabled": True},
                "learning": {
                    "enabled": True,
                    "sources": {
                        "ritualist_journal": True,
                        "open_windows": False,
                    },
                    "consent": {
                        "timestamp": "2026-06-17T13:45:00Z",
                        "version": LEARNING_CONSENT_VERSION,
                        "sources": ["ritualist_journal"],
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    config = load_app_config(path)

    assert config.learning.effective_enabled is True
    assert config.learning.enabled_source_ids == ("ritualist_journal",)
    assert config.learning.is_source_enabled("open_windows") is False
    assert config.learning.is_source_enabled("recent_items") is False
    assert not hasattr(config, "watch_me")


def test_load_app_config_defaults_learning_disabled(tmp_path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("version: '0.1'\n", encoding="utf-8")

    config = load_app_config(path)

    assert config.learning == LocalLearningConfig()
