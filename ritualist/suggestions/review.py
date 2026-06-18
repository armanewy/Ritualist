from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from typing import Any, Mapping, Sequence

from .models import Suggestion, SuggestionApproval, SuggestionKind, SuggestionStatus
from .storage import SuggestionStore


SUGGESTION_REVIEW_TOKEN_VERSION = "ritualist.suggestion.review.v1"
MAX_PROPOSED_ARTIFACT_SUMMARY_LENGTH = 500

_REVIEWABLE_APPROVAL_STATUSES = frozenset(
    {
        SuggestionStatus.NEW,
        SuggestionStatus.REVIEWING,
    }
)
_ACTION_INTENT_KEYS = frozenset({"action", "component_type", "kind", "type"})
_REVIEW_ONLY_ACTION_VALUES = frozenset(
    {
        "review_cleanup_hint",
        "review_ritual_recipe",
        "review_room_canvas",
        "review_shortcut_component",
    }
)
_REVIEW_ONLY_KIND_TYPE_VALUES = frozenset(
    {
        "cleanup_hint",
        "ritual_recipe",
        "room_canvas",
        "shortcut_app",
        "shortcut_component",
        "shortcut_folder",
        "shortcut_url",
    }
)
_RUNTIME_EXECUTION_KEYS = frozenset(
    {
        "args",
        "browser_history",
        "click",
        "click_coordinate",
        "click_coordinates",
        "cmd",
        "code",
        "command",
        "coordinate",
        "coordinates",
        "exec",
        "execute",
        "executable",
        "global_hook",
        "history",
        "hotkey",
        "html",
        "javascript",
        "js",
        "keylog",
        "keylogger",
        "keylogging",
        "keystroke",
        "ocr",
        "password",
        "powershell",
        "python",
        "qml",
        "record",
        "recording",
        "run",
        "script",
        "screenshot",
        "shell",
        "subprocess",
        "target",
        "uri",
        "url",
        "watch_me",
        "watchme",
    }
)
_TOKEN_RE = re.compile(r"[^a-z0-9]+")


class SuggestionReviewError(ValueError):
    """Base error for review policy failures."""


class SuggestionNotFoundError(SuggestionReviewError):
    """Raised when a requested suggestion is not present in storage."""


class SuggestionReviewStateError(SuggestionReviewError):
    """Raised when a review transition is not allowed for the current status."""


class SuggestionReviewRequiredError(SuggestionReviewError):
    """Raised when a draft is requested without a current approval."""


class SuggestionRuntimeExecutionBlockedError(SuggestionReviewError):
    """Raised when a suggestion proposes runtime execution instead of a draft."""


@dataclass(frozen=True)
class SuggestionReviewSnapshot:
    suggestion_id: str
    review_token: str
    proposed_artifact_summary: str
    status: SuggestionStatus
    approval_current: bool
    can_create_draft: bool


def review_snapshot(suggestion: Suggestion) -> SuggestionReviewSnapshot:
    return SuggestionReviewSnapshot(
        suggestion_id=suggestion.id,
        review_token=review_token_for(suggestion),
        proposed_artifact_summary=proposed_artifact_summary(suggestion),
        status=suggestion.status,
        approval_current=is_approval_current(suggestion),
        can_create_draft=can_create_draft(suggestion),
    )


def review_token_for(suggestion: Suggestion) -> str:
    payload = {
        "review_schema_version": SUGGESTION_REVIEW_TOKEN_VERSION,
        "suggestion": _reviewable_payload(suggestion),
    }
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return sha256(encoded.encode("utf-8")).hexdigest()


def proposed_artifact_summary(suggestion: Suggestion) -> str:
    kind_label = _artifact_kind_label(suggestion.kind)
    title = _compact_review_text(suggestion.title or suggestion.id)
    parts = [f"{kind_label}: {title}"]

    action_summaries = [
        summary
        for action in suggestion.proposed_actions
        if (summary := _summarize_proposed_action(action))
    ]
    if action_summaries:
        parts.append(f"Proposal: {'; '.join(action_summaries[:5])}")
    if suggestion.missing_inputs:
        parts.append(f"Missing inputs: {', '.join(suggestion.missing_inputs[:10])}")

    return _compact_review_text(". ".join(parts), limit=MAX_PROPOSED_ARTIFACT_SUMMARY_LENGTH)


def build_approval_record(
    suggestion: Suggestion,
    *,
    reviewed_by: str,
    approved: bool,
    reviewed_at: str | None = None,
) -> SuggestionApproval:
    if approved:
        _ensure_no_runtime_execution_intent(suggestion)
    return SuggestionApproval(
        reviewed_by=reviewed_by,
        reviewed_at=reviewed_at or _utc_timestamp(),
        review_token=review_token_for(suggestion),
        approved=approved,
        artifact_summary=proposed_artifact_summary(suggestion),
    )


def approve_suggestion(
    store: SuggestionStore,
    suggestion_id: str,
    *,
    reviewed_by: str,
    reviewed_at: str | None = None,
) -> Suggestion:
    suggestion = _get_required(store, suggestion_id)
    _ensure_approval_transition_allowed(suggestion)
    approval = build_approval_record(
        suggestion,
        reviewed_by=reviewed_by,
        reviewed_at=reviewed_at,
        approved=True,
    )
    updated = suggestion.with_status(
        SuggestionStatus.APPROVED,
        approval=approval,
        drafted_artifact_ref="",
    )
    return store.save(updated)


def dismiss_suggestion(
    store: SuggestionStore,
    suggestion_id: str,
    *,
    reviewed_by: str,
    reviewed_at: str | None = None,
) -> Suggestion:
    suggestion = _get_required(store, suggestion_id)
    approval = build_approval_record(
        suggestion,
        reviewed_by=reviewed_by,
        reviewed_at=reviewed_at,
        approved=False,
    )
    updated = suggestion.with_status(
        SuggestionStatus.DISMISSED,
        approval=approval,
        drafted_artifact_ref="",
    )
    return store.save(updated)


def cancel_suggestion(
    store: SuggestionStore,
    suggestion_id: str,
    *,
    reviewed_by: str,
    reviewed_at: str | None = None,
) -> Suggestion:
    suggestion = _get_required(store, suggestion_id)
    approval = build_approval_record(
        suggestion,
        reviewed_by=reviewed_by,
        reviewed_at=reviewed_at,
        approved=False,
    )
    updated = suggestion.with_status(
        SuggestionStatus.CANCELLED,
        approval=approval,
        drafted_artifact_ref="",
    )
    return store.save(updated)


def is_approval_current(suggestion: Suggestion) -> bool:
    approval = suggestion.approval
    if (
        suggestion.status is not SuggestionStatus.APPROVED
        or approval is None
        or not approval.approved
        or not approval.review_token
    ):
        return False
    try:
        _ensure_no_runtime_execution_intent(suggestion)
    except SuggestionRuntimeExecutionBlockedError:
        return False
    return approval.review_token == review_token_for(suggestion)


def can_create_draft(suggestion: Suggestion) -> bool:
    return is_approval_current(suggestion)


def require_approval_for_draft(suggestion: Suggestion) -> Suggestion:
    if not can_create_draft(suggestion):
        raise SuggestionReviewRequiredError(
            "Suggestion draft creation requires a current explicit approval."
        )
    return suggestion


def _get_required(store: SuggestionStore, suggestion_id: str) -> Suggestion:
    suggestion = store.get(suggestion_id)
    if suggestion is None:
        raise SuggestionNotFoundError(f"Suggestion not found: {suggestion_id}")
    return suggestion


def _ensure_approval_transition_allowed(suggestion: Suggestion) -> None:
    if suggestion.status not in _REVIEWABLE_APPROVAL_STATUSES:
        if suggestion.status is SuggestionStatus.APPROVED and not is_approval_current(suggestion):
            return
        raise SuggestionReviewStateError(
            f"Cannot approve suggestion {suggestion.id!r} from {suggestion.status.value!r}."
        )


def _ensure_no_runtime_execution_intent(suggestion: Suggestion) -> None:
    if not suggestion.proposed_actions:
        raise SuggestionRuntimeExecutionBlockedError(
            f"Suggestion {suggestion.id!r} has no review-only proposed actions."
        )
    for index, action in enumerate(suggestion.proposed_actions):
        top_level_action = action.get("action")
        if not isinstance(top_level_action, str) or (
            _normalize_token(top_level_action) not in _REVIEW_ONLY_ACTION_VALUES
        ):
            raise SuggestionRuntimeExecutionBlockedError(
                f"Suggestion {suggestion.id!r} is missing a review-only action "
                f"at proposed_actions[{index}]."
            )
        for path, key, value in _walk_mapping(action):
            normalized_key = _normalize_token(key)
            if _token_matches_any(normalized_key, _RUNTIME_EXECUTION_KEYS):
                raise SuggestionRuntimeExecutionBlockedError(
                    f"Suggestion {suggestion.id!r} contains runtime execution key "
                    f"{'.'.join(path)!r}."
                )
            if normalized_key in _ACTION_INTENT_KEYS:
                if not isinstance(value, str):
                    raise SuggestionRuntimeExecutionBlockedError(
                        f"Suggestion {suggestion.id!r} contains non-string review intent "
                        f"at proposed_actions[{index}].{'.'.join(path)}."
                    )
                normalized_value = _normalize_token(value)
                if normalized_key == "action" and normalized_value not in _REVIEW_ONLY_ACTION_VALUES:
                    raise SuggestionRuntimeExecutionBlockedError(
                        f"Suggestion {suggestion.id!r} proposes non-review action "
                        f"{value!r} at proposed_actions[{index}].{'.'.join(path)}."
                    )
                if (
                    normalized_key != "action"
                    and normalized_value not in _REVIEW_ONLY_KIND_TYPE_VALUES
                ):
                    raise SuggestionRuntimeExecutionBlockedError(
                        f"Suggestion {suggestion.id!r} proposes non-review taxonomy "
                        f"{value!r} at proposed_actions[{index}].{'.'.join(path)}."
                    )


def _walk_mapping(
    value: Mapping[str, Any],
    path: tuple[str, ...] = (),
) -> list[tuple[tuple[str, ...], str, Any]]:
    rows: list[tuple[tuple[str, ...], str, Any]] = []
    for key, item in value.items():
        key_text = str(key)
        item_path = (*path, key_text)
        rows.append((item_path, key_text, item))
        if isinstance(item, Mapping):
            rows.extend(_walk_mapping(item, item_path))
        elif isinstance(item, Sequence) and not isinstance(item, str | bytes | bytearray):
            rows.extend(_walk_sequence(item, item_path))
    return rows


def _walk_sequence(
    value: Sequence[Any],
    path: tuple[str, ...],
) -> list[tuple[tuple[str, ...], str, Any]]:
    rows: list[tuple[tuple[str, ...], str, Any]] = []
    for offset, child in enumerate(value):
        child_path = (*path, f"[{offset}]")
        if isinstance(child, Mapping):
            rows.extend(_walk_mapping(child, child_path))
        elif isinstance(child, Sequence) and not isinstance(child, str | bytes | bytearray):
            rows.extend(_walk_sequence(child, child_path))
    return rows


def _reviewable_payload(suggestion: Suggestion) -> dict[str, object]:
    payload = suggestion.to_dict()
    for transient_key in ("schema_version", "status", "approval", "drafted_artifact_ref"):
        payload.pop(transient_key, None)
    return payload


def _artifact_kind_label(kind: SuggestionKind) -> str:
    return {
        SuggestionKind.SHORTCUT_COMPONENT: "Shortcut component draft",
        SuggestionKind.RITUAL_RECIPE: "Ritual recipe draft",
        SuggestionKind.ROOM_CANVAS: "Room canvas draft",
        SuggestionKind.CLEANUP_HINT: "Cleanup hint draft",
    }[kind]


def _summarize_proposed_action(action: Mapping[str, Any]) -> str:
    fields: list[str] = []
    for key in (
        "kind",
        "component_type",
        "type",
        "action",
        "label",
        "title",
        "recipe_id",
        "room_id",
        "domain_label",
        "missing_input",
        "input_id",
        "source_id",
    ):
        value = action.get(key)
        if value in (None, ""):
            continue
        fields.append(f"{key}={_compact_review_text(value, limit=80)}")
    return ", ".join(fields[:5])


def _compact_review_text(value: object, *, limit: int = 160) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    return " ".join(text.split())[:limit]


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_token(value: object) -> str:
    text = str(value or "")
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", text)
    text = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", "_", text)
    text = text.casefold()
    return _TOKEN_RE.sub("_", text).strip("_")


def _token_matches_any(value: str, tokens: frozenset[str]) -> bool:
    compact_value = value.replace("_", "")
    for token in tokens:
        if (
            value == token
            or value.startswith(f"{token}_")
            or value.endswith(f"_{token}")
            or f"_{token}_" in value
        ):
            return True
        if "_" in token and compact_value:
            compact_token = token.replace("_", "")
            if (
                compact_value == compact_token
                or compact_value.startswith(compact_token)
                or compact_value.endswith(compact_token)
                or compact_token in compact_value
            ):
                return True
    return False


__all__ = [
    "MAX_PROPOSED_ARTIFACT_SUMMARY_LENGTH",
    "SUGGESTION_REVIEW_TOKEN_VERSION",
    "SuggestionNotFoundError",
    "SuggestionReviewError",
    "SuggestionReviewRequiredError",
    "SuggestionReviewSnapshot",
    "SuggestionReviewStateError",
    "SuggestionRuntimeExecutionBlockedError",
    "approve_suggestion",
    "build_approval_record",
    "can_create_draft",
    "cancel_suggestion",
    "dismiss_suggestion",
    "is_approval_current",
    "proposed_artifact_summary",
    "require_approval_for_draft",
    "review_snapshot",
    "review_token_for",
]
