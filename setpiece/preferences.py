from __future__ import annotations

import json
import os
import platform
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .paths import app_data_dir
from .run_logs import KEEP_SETUP_OPEN

PREFERENCES_SCHEMA_VERSION = "setpiece.preferences.v1"
PREFERENCES_FILENAME = "local-preferences.json"
HIGH_RISK_REMEMBER_TOKENS = frozenset(
    {
        "bank",
        "buy",
        "card",
        "credential",
        "credit card",
        "pay",
        "payment",
        "purchase",
        "checkout",
        "delete",
        "destroy",
        "erase",
        "format",
        "password",
        "passwd",
        "remove",
        "send",
        "publish",
        "uninstall",
        "reset",
        "secret",
        "token",
        "transfer",
        "wipe",
        "confirm order",
    }
)
DISALLOWED_REMEMBER_RISKS = frozenset({"credential", "credentials", "payment", "destructive"})
APPROVAL_SOURCE_TRUSTS = frozenset({"local_user", "private_pack"})


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
    local_device: str = field(default_factory=lambda: _local_device())
    target_scope: str = ""
    target_application: str = ""
    risk_level: str = ""
    target_ambiguous: bool = False
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
            "local_device": self.local_device,
            "target_scope": self.target_scope,
            "target_application": self.target_application,
            "risk_level": self.risk_level,
            "target_ambiguous": "true" if self.target_ambiguous else "false",
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
    if scope.source_trust not in APPROVAL_SOURCE_TRUSTS:
        return False
    if scope.target_ambiguous:
        return False
    required_fields = (
        scope.recipe_or_intent_id,
        scope.content_hash,
        scope.step_id,
        scope.action_or_primitive_id,
        scope.local_user,
        scope.local_device,
        scope.target_scope,
        scope.target_application,
        scope.risk_level,
    )
    if any(not str(value).strip() for value in required_fields):
        return False
    if scope.target_scope in {"browser", "desktop"} and not scope.target_label().strip():
        return False
    if scope.target_scope == "desktop" and not scope.resolved_target_identity.strip():
        return False
    if scope.risk_level.strip().casefold() in DISALLOWED_REMEMBER_RISKS:
        return False
    label = " ".join(
        value
        for value in (
            scope.target_label(),
            scope.action_or_primitive_id,
            scope.target_scope,
            scope.target_application,
            scope.risk_level,
        )
        if value
    ).casefold()
    return not any(token in label for token in HIGH_RISK_REMEMBER_TOKENS)


def remember_approval(
    scope: RememberedApprovalScope,
    *,
    path: Path | None = None,
) -> dict[str, Any]:
    if not can_remember_approval(scope):
        if scope.target_ambiguous:
            raise ValueError("ambiguous confirmation targets cannot be remembered")
        raise ValueError("high-risk confirmation targets cannot be remembered casually")
    preferences = load_preferences(path=path)
    serialized = scope.to_dict()
    approvals = [
        existing
        for existing in preferences["remembered_approvals"]
        if existing.get("scope") != serialized
    ]
    entry = {"id": uuid.uuid4().hex, "scope": serialized, "created_at": _now_iso()}
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
    if (
        not local_user_approved_source
        or scope.source_trust not in APPROVAL_SOURCE_TRUSTS
        or not can_remember_approval(scope)
    ):
        return False
    preferences = load_preferences(path=path)
    target = scope.to_dict()
    return any(entry.get("scope") == target for entry in preferences["remembered_approvals"])


def list_remembered_approvals(*, path: Path | None = None) -> list[dict[str, Any]]:
    preferences = load_preferences(path=path)
    return [
        dict(entry)
        for entry in preferences["remembered_approvals"]
        if isinstance(entry.get("id"), str) and isinstance(entry.get("scope"), dict)
    ]


def revoke_remembered_approval(approval_id: str, *, path: Path | None = None) -> bool:
    preferences = load_preferences(path=path)
    approval_id = approval_id.strip()
    approvals = preferences["remembered_approvals"]
    kept = [entry for entry in approvals if str(entry.get("id") or "") != approval_id]
    if len(kept) == len(approvals):
        return False
    preferences["remembered_approvals"] = kept
    _write_preferences(path or preferences_path(), preferences)
    return True


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


def _local_device() -> str:
    return os.environ.get("COMPUTERNAME") or platform.node() or "local-device"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
