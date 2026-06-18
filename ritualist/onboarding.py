from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from .learning_sources import (
    ALLOWED_LEARNING_SOURCE_IDS,
    filter_allowed_learning_sources,
)
from .paths import app_data_dir

ONBOARDING_SCHEMA_VERSION = "ritualist.onboarding.v1"
ONBOARDING_FLOW_VERSION = "first-run-v1"
ONBOARDING_STATE_FILENAME = "onboarding-state.json"

LOCAL_LEARNING_UNDECIDED = "undecided"
LOCAL_LEARNING_ENABLED = "enabled"
LOCAL_LEARNING_DISABLED = "disabled"
LOCAL_LEARNING_DECISIONS = frozenset(
    {
        LOCAL_LEARNING_UNDECIDED,
        LOCAL_LEARNING_ENABLED,
        LOCAL_LEARNING_DISABLED,
    }
)


@dataclass(frozen=True)
class OnboardingState:
    completed: bool = False
    version: str = ONBOARDING_FLOW_VERSION
    local_learning_decision: str = LOCAL_LEARNING_UNDECIDED
    selected_recommended_source_ids: tuple[str, ...] = field(default_factory=tuple)
    skipped: bool = False
    reopen_settings_later: bool = False

    @property
    def should_show_first_run(self) -> bool:
        return not self.completed and not self.skipped

    @property
    def local_learning_enabled(self) -> bool:
        return self.local_learning_decision == LOCAL_LEARNING_ENABLED

    @property
    def has_selected_learning_sources(self) -> bool:
        return bool(self.selected_recommended_source_ids)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> "OnboardingState":
        if not isinstance(raw, Mapping):
            return cls()
        if raw.get("schema_version") != ONBOARDING_SCHEMA_VERSION:
            return cls()

        decision = _normalize_decision(raw.get("local_learning_decision"))
        sources = _load_source_ids(
            raw.get("selected_recommended_sources") or raw.get("selected_recommended_source_ids")
        )
        if decision != LOCAL_LEARNING_ENABLED:
            sources = ()

        completed = bool(raw.get("completed", False))
        skipped = bool(raw.get("skipped", False)) and not completed
        return cls(
            completed=completed,
            version=_normalize_version(raw.get("version")),
            local_learning_decision=decision,
            selected_recommended_source_ids=sources,
            skipped=skipped,
            reopen_settings_later=bool(raw.get("reopen_settings_later", False)),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": ONBOARDING_SCHEMA_VERSION,
            "version": self.version,
            "completed": self.completed,
            "skipped": self.skipped,
            "reopen_settings_later": self.reopen_settings_later,
            "local_learning_decision": self.local_learning_decision,
            "selected_recommended_sources": list(self.selected_recommended_source_ids),
        }


def onboarding_state_path(*, base_dir: Path | None = None) -> Path:
    return (base_dir or app_data_dir()) / ONBOARDING_STATE_FILENAME


def load_onboarding_state(*, path: Path | None = None) -> OnboardingState:
    resolved = path or onboarding_state_path()
    if not resolved.exists():
        return OnboardingState()
    try:
        raw = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return OnboardingState()
    return OnboardingState.from_mapping(raw)


def save_onboarding_state(state: OnboardingState, *, path: Path | None = None) -> OnboardingState:
    resolved = path or onboarding_state_path()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(json.dumps(state.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return state


def complete_onboarding(
    *,
    local_learning_decision: str,
    selected_recommended_source_ids: tuple[object, ...] | list[object] = (),
    reopen_settings_later: bool = False,
    version: str = ONBOARDING_FLOW_VERSION,
) -> OnboardingState:
    decision = _normalize_decision(local_learning_decision)
    if decision == LOCAL_LEARNING_UNDECIDED:
        decision = LOCAL_LEARNING_DISABLED
    sources = _normalize_sources_for_decision(decision, selected_recommended_source_ids)
    return OnboardingState(
        completed=True,
        version=_normalize_version(version),
        local_learning_decision=decision,
        selected_recommended_source_ids=sources,
        skipped=False,
        reopen_settings_later=reopen_settings_later,
    )


def skip_onboarding(
    *,
    reopen_settings_later: bool = True,
    version: str = ONBOARDING_FLOW_VERSION,
) -> OnboardingState:
    return OnboardingState(
        completed=False,
        version=_normalize_version(version),
        local_learning_decision=LOCAL_LEARNING_UNDECIDED,
        selected_recommended_source_ids=(),
        skipped=True,
        reopen_settings_later=reopen_settings_later,
    )


def mark_settings_reopened(state: OnboardingState) -> OnboardingState:
    return replace(state, reopen_settings_later=False)


def recommended_learning_source_ids() -> tuple[str, ...]:
    return ALLOWED_LEARNING_SOURCE_IDS


def _normalize_decision(raw: object) -> str:
    if not isinstance(raw, str):
        return LOCAL_LEARNING_UNDECIDED
    decision = str(raw or "").strip().casefold().replace("-", "_")
    if decision in LOCAL_LEARNING_DECISIONS:
        return decision
    return LOCAL_LEARNING_UNDECIDED


def _load_source_ids(raw: object) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str):
        return filter_allowed_learning_sources((raw,))
    if isinstance(raw, Mapping):
        return filter_allowed_learning_sources(
            source_id for source_id, enabled in raw.items() if bool(enabled)
        )
    if isinstance(raw, list | tuple | set):
        return filter_allowed_learning_sources(raw)
    return ()


def _normalize_sources_for_decision(
    decision: str,
    source_ids: tuple[object, ...] | list[object],
) -> tuple[str, ...]:
    if decision != LOCAL_LEARNING_ENABLED:
        return ()
    return filter_allowed_learning_sources(source_ids)


def _normalize_version(raw: object) -> str:
    version = str(raw or "").strip()
    return version or ONBOARDING_FLOW_VERSION


__all__ = [
    "LOCAL_LEARNING_DECISIONS",
    "LOCAL_LEARNING_DISABLED",
    "LOCAL_LEARNING_ENABLED",
    "LOCAL_LEARNING_UNDECIDED",
    "ONBOARDING_FLOW_VERSION",
    "ONBOARDING_SCHEMA_VERSION",
    "ONBOARDING_STATE_FILENAME",
    "OnboardingState",
    "complete_onboarding",
    "load_onboarding_state",
    "mark_settings_reopened",
    "onboarding_state_path",
    "recommended_learning_source_ids",
    "save_onboarding_state",
    "skip_onboarding",
]
