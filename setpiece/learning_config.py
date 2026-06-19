from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .learning_sources import (
    ALLOWED_LEARNING_SOURCE_IDS,
    LEARNING_CONSENT_VERSION,
    filter_allowed_learning_sources,
    normalize_learning_source_id,
)


@dataclass(frozen=True)
class LearningConsentRecord:
    timestamp: str = ""
    version: str = LEARNING_CONSENT_VERSION
    source_ids: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_valid(self) -> bool:
        return bool(self.timestamp.strip() and self.version.strip())

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> "LearningConsentRecord | None":
        if not isinstance(raw, Mapping):
            return None

        timestamp = str(raw.get("timestamp") or "").strip()
        version = str(raw.get("version") or LEARNING_CONSENT_VERSION).strip()
        source_ids = _load_source_ids(raw.get("sources") or raw.get("source_ids"))
        record = cls(timestamp=timestamp, version=version, source_ids=source_ids)
        return record if record.is_valid else None

    def to_dict(self) -> dict[str, object]:
        return {
            "timestamp": self.timestamp,
            "version": self.version,
            "sources": list(self.source_ids),
        }


@dataclass(frozen=True)
class LocalLearningConfig:
    enabled: bool = False
    source_ids: tuple[str, ...] = field(default_factory=tuple)
    consent: LearningConsentRecord | None = None
    background_collection: bool = False

    @property
    def effective_enabled(self) -> bool:
        return self.enabled and self.consent is not None and self.consent.is_valid

    @property
    def enabled_source_ids(self) -> tuple[str, ...]:
        if not self.effective_enabled or self.consent is None:
            return ()
        consented = set(self.consent.source_ids)
        return tuple(source_id for source_id in self.source_ids if source_id in consented)

    def is_source_enabled(self, source_id: object) -> bool:
        normalized = normalize_learning_source_id(source_id)
        return normalized in self.enabled_source_ids

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> "LocalLearningConfig":
        if not isinstance(raw, Mapping):
            return cls()

        consent = LearningConsentRecord.from_mapping(raw.get("consent"))
        requested_sources = _load_source_ids(raw.get("sources") or raw.get("source_ids"))
        return cls(
            enabled=bool(raw.get("enabled", False)),
            source_ids=requested_sources,
            consent=consent,
            background_collection=False,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "sources": list(self.source_ids),
            "consent": self.consent.to_dict() if self.consent else None,
            "background_collection": False,
        }


def _load_source_ids(raw: object) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, Mapping):
        return filter_allowed_learning_sources(
            source_id for source_id, enabled in raw.items() if bool(enabled)
        )
    if isinstance(raw, str):
        return filter_allowed_learning_sources((raw,))
    if isinstance(raw, list | tuple | set):
        return filter_allowed_learning_sources(raw)
    return ()


def default_local_learning_config() -> LocalLearningConfig:
    return LocalLearningConfig()


__all__ = [
    "ALLOWED_LEARNING_SOURCE_IDS",
    "LEARNING_CONSENT_VERSION",
    "LearningConsentRecord",
    "LocalLearningConfig",
    "default_local_learning_config",
]
