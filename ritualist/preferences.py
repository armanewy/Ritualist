from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .paths import app_data_dir
from .run_logs import KEEP_SETUP_OPEN

PREFERENCES_SCHEMA_VERSION = "ritualist.preferences.v1"
PREFERENCES_FILENAME = "local-preferences.json"
HIGH_RISK_REMEMBER_TOKENS = frozenset(
    {
        "buy",
        "pay",
        "purchase",
        "checkout",
        "delete",
        "send",
        "publish",
        "uninstall",
        "reset",
        "confirm order",
    }
)


@dataclass(frozen=True)
class CleanupPreferenceScope:
    recipe_or_intent_id: str
    stop_reason: str
    local_user: str = field(default_factory=lambda: _local_user())

    def to_dict(self) -> dict[str, str]:
        return {
            "recipe_or_intent_id": self.recipe_or_intent_id,
            "stop_reason": self.stop_reason,
            "local_user": self.local_user,
        }


@dataclass(frozen=True)
class RememberedApprovalScope:
    recipe_or_intent_id: str
    content_hash: str
    step_id: str
    action_or_primitive_id: str
    resolved_target_identity: str
    target_context: str
    target_text: str = ""
    target_control: str = ""
    target_role: str = ""
    target_test_id: str = ""
    local_user: str = field(default_factory=lambda: _local_user())
    source_trust: str = "local_user"

    def to_dict(self) -> dict[str, str]:
        return {
            "recipe_or_intent_id": self.recipe_or_intent_id,
            "content_hash": self.content_hash,
            "step_id": self.step_id,
            "action_or_primitive_id": self.action_or_primitive_id,
            "resolved_target_identity": self.resolved_target_identity,
            "target_context": self.target_context,
            "target_text": self.target_text,
            "target_control": self.target_control,
            "target_role": self.target_role,
            "target_test_id": self.target_test_id,
            "local_user": self.local_user,
            "source_trust": self.source_trust,
        }

    def target_label(self) -> str:
        return " ".join(
            part
            for part in (
                self.target_text,
                self.target_control,
                self.target_role,
                self.target_test_id,
            )
            if part
        )


def preferences_path(*, base_dir: Path | None = None) -> Path:
    return (base_dir or app_data_dir()) / PREFERENCES_FILENAME


def load_preferences(*, path: Path | None = None) -> dict[str, Any]:
    resolved = path or preferences_path()
    if not resolved.exists():
        return _empty_preferences()
    try:
        data = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_preferences()
    if not isinstance(data, dict):
        return _empty_preferences()
    return _normalize_preferences(data)


def remember_cleanup_choice(
    scope: CleanupPreferenceScope,
    choice: str,
    *,
    path: Path | None = None,
) -> dict[str, Any]:
    preferences = load_preferences(path=path)
    entry = {
        "id": uuid.uuid4().hex,
        "scope": scope.to_dict(),
        "choice": choice or KEEP_SETUP_OPEN,
    }
    cleanup = [
        existing
        for existing in preferences["cleanup_preferences"]
        if existing.get("scope") != scope.to_dict()
    ]
    cleanup.append(entry)
    preferences["cleanup_preferences"] = cleanup
    _write_preferences(path or preferences_path(), preferences)
    return entry


def cleanup_choice_for(
    scope: CleanupPreferenceScope,
    *,
    path: Path | None = None,
) -> str | None:
    preferences = load_preferences(path=path)
    target = scope.to_dict()
    for entry in reversed(preferences["cleanup_preferences"]):
        if entry.get("scope") == target:
            return str(entry.get("choice") or KEEP_SETUP_OPEN)
    return None


def can_remember_approval(scope: RememberedApprovalScope) -> bool:
    if scope.source_trust not in {"local_user", "private_pack"}:
        return False
    label = f"{scope.target_label()} {scope.action_or_primitive_id}".casefold()
    return not any(token in label for token in HIGH_RISK_REMEMBER_TOKENS)


def remember_approval(
    scope: RememberedApprovalScope,
    *,
    path: Path | None = None,
) -> dict[str, Any]:
    if not can_remember_approval(scope):
        raise ValueError("high-risk confirmation targets cannot be remembered casually")
    preferences = load_preferences(path=path)
    serialized = scope.to_dict()
    approvals = [
        existing
        for existing in preferences["remembered_approvals"]
        if existing.get("scope") != serialized
    ]
    entry = {"id": uuid.uuid4().hex, "scope": serialized}
    approvals.append(entry)
    preferences["remembered_approvals"] = approvals
    _write_preferences(path or preferences_path(), preferences)
    return entry


def approval_matches(
    scope: RememberedApprovalScope,
    *,
    path: Path | None = None,
    local_user_approved_source: bool = False,
) -> bool:
    if not local_user_approved_source or scope.source_trust not in {"local_user", "private_pack"}:
        return False
    preferences = load_preferences(path=path)
    target = scope.to_dict()
    return any(entry.get("scope") == target for entry in preferences["remembered_approvals"])


def _empty_preferences() -> dict[str, Any]:
    return {
        "schema_version": PREFERENCES_SCHEMA_VERSION,
        "cleanup_preferences": [],
        "remembered_approvals": [],
    }


def _normalize_preferences(data: dict[str, Any]) -> dict[str, Any]:
    normalized = _empty_preferences()
    for key in ("cleanup_preferences", "remembered_approvals"):
        value = data.get(key)
        if isinstance(value, list):
            normalized[key] = [entry for entry in value if isinstance(entry, dict)]
    return normalized


def _write_preferences(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _local_user() -> str:
    return os.environ.get("USERNAME") or os.environ.get("USER") or "local"
