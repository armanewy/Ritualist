from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Mapping, Sequence
import uuid
import re

from ritualist.learning_sources import (
    filter_allowed_learning_sources,
    is_forbidden_learning_source,
    normalize_learning_source_id,
)


SUGGESTION_SCHEMA_VERSION = "ritualist.suggestion.v1"
MAX_TEXT_LENGTH = 500
MAX_COLLECTION_ITEMS = 50
SENSITIVE_TEXT_REPLACEMENT = "[redacted]"
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
WINDOWS_ABSOLUTE_PATH_RE = re.compile(r"\b[A-Za-z]:[\\/][^\s,;]+")
POSIX_ABSOLUTE_PATH_RE = re.compile(r"(?<!\w)/(?:[^\s,;]+/)*[^\s,;]+")
COMMAND_TEXT_RE = re.compile(
    r"("
    r"\b[\w.-]+\.(?:bat|cmd|com|exe|js|msi|ps1|py|sh|vbs)\b"
    r"|\b[A-Za-z]+-[A-Za-z]+\b"
    r"|\b(?:bash|bcdedit|cmd|curl|del|diskpart|erase|format|ii|irm|iwr|mkdir|net|netsh|"
    r"ni|node|npm|npx|powershell|pwsh|python|reg|ri|rm|sc|shutdown|sh|taskkill|wget)\b"
    r"|\s-[rf]{1,2}\b"
    r")",
    re.IGNORECASE,
)
FORBIDDEN_VALUE_TOKENS = frozenset(
    {
        "browser_history",
        "click_coordinates",
        "click_coordinate",
        "coordinate_capture",
        "keylogger",
        "keylogging",
        "keystroke",
        "ocr",
        "ocr_result",
        "recording",
        "recording_file",
        "screen_capture",
        "screen_recording",
        "screenshot",
        "screenshot_path",
        "watch_me",
        "watchme",
    }
)
MISSING_INPUT_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
SAFE_SUGGESTION_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,127}$")
SAFE_APPROVAL_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]{0,127}$")
SAFE_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T[0-9:.+-]+Z?$")
SAFE_ARTIFACT_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./-]{0,255}$")
EXECUTABLE_PROPOSED_ACTION_KEYS = frozenset(
    {
        "args",
        "browser_history",
        "code",
        "command",
        "content",
        "coordinate",
        "coordinates",
        "cmd",
        "exec",
        "executable",
        "file_content",
        "file_contents",
        "history",
        "html",
        "javascript",
        "js",
        "keylog",
        "keystroke",
        "ocr",
        "password",
        "powershell",
        "python",
        "qml",
        "recording",
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
PROPOSED_ACTION_ALLOWED_KEYS = frozenset(
    {
        "action",
        "component_type",
        "description",
        "domain_label",
        "input_id",
        "kind",
        "label",
        "missing_input",
        "notes",
        "placeholder",
        "recipe_id",
        "room_id",
        "source_id",
        "title",
        "type",
    }
)


class SuggestionKind(StrEnum):
    SHORTCUT_COMPONENT = "shortcut_component"
    RITUAL_RECIPE = "ritual_recipe"
    ROOM_CANVAS = "room_canvas"
    CLEANUP_HINT = "cleanup_hint"


class SuggestionStatus(StrEnum):
    NEW = "new"
    REVIEWING = "reviewing"
    APPROVED = "approved"
    DISMISSED = "dismissed"
    CANCELLED = "cancelled"
    DRAFTED = "drafted"


class SuggestionPrivacyLevel(StrEnum):
    LOW = "low"
    REVIEW = "review"
    SENSITIVE = "sensitive"


@dataclass(frozen=True)
class SuggestionApproval:
    reviewed_by: str = ""
    reviewed_at: str = ""
    review_token: str = ""
    approved: bool = False
    artifact_summary: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "reviewed_by", _safe_approval_id(self.reviewed_by))
        object.__setattr__(self, "reviewed_at", _safe_timestamp(self.reviewed_at))
        object.__setattr__(self, "review_token", _safe_approval_id(self.review_token))
        object.__setattr__(self, "artifact_summary", _clean_public_text(self.artifact_summary))

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> "SuggestionApproval | None":
        if not isinstance(raw, Mapping):
            return None
        return cls(
            reviewed_by=str(raw.get("reviewed_by") or ""),
            reviewed_at=str(raw.get("reviewed_at") or ""),
            review_token=str(raw.get("review_token") or ""),
            approved=bool(raw.get("approved", False)),
            artifact_summary=str(raw.get("artifact_summary") or ""),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at,
            "review_token": self.review_token,
            "approved": self.approved,
            "artifact_summary": self.artifact_summary,
        }


@dataclass(frozen=True)
class Suggestion:
    id: str
    kind: SuggestionKind
    title: str
    description: str
    confidence: float
    evidence_summary: str
    evidence_count: int
    sources: tuple[str, ...] = field(default_factory=tuple)
    proposed_actions: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    missing_inputs: tuple[str, ...] = field(default_factory=tuple)
    privacy_level: SuggestionPrivacyLevel = SuggestionPrivacyLevel.REVIEW
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: SuggestionStatus = SuggestionStatus.NEW
    approval: SuggestionApproval | None = None
    drafted_artifact_ref: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _safe_suggestion_id(self.id))
        object.__setattr__(self, "title", _clean_public_text(self.title))
        object.__setattr__(self, "description", _clean_public_text(self.description))
        object.__setattr__(self, "confidence", _bounded_confidence(self.confidence))
        object.__setattr__(self, "evidence_summary", _clean_public_text(self.evidence_summary))
        object.__setattr__(self, "evidence_count", max(0, int(self.evidence_count)))
        object.__setattr__(self, "sources", filter_allowed_learning_sources(self.sources))
        object.__setattr__(
            self,
            "proposed_actions",
            tuple(_sanitize_proposed_action(action) for action in self.proposed_actions),
        )
        object.__setattr__(self, "missing_inputs", _clean_missing_inputs(self.missing_inputs))
        object.__setattr__(self, "created_at", _safe_timestamp(self.created_at))
        object.__setattr__(self, "drafted_artifact_ref", _clean_artifact_ref(self.drafted_artifact_ref))

    @classmethod
    def create(
        cls,
        *,
        kind: SuggestionKind | str,
        title: str,
        description: str,
        confidence: float,
        evidence_summary: str,
        evidence_count: int,
        sources: Sequence[str] = (),
        proposed_actions: Sequence[Mapping[str, Any]] = (),
        missing_inputs: Sequence[str] = (),
        privacy_level: SuggestionPrivacyLevel | str = SuggestionPrivacyLevel.REVIEW,
    ) -> "Suggestion":
        return cls(
            id=uuid.uuid4().hex,
            kind=SuggestionKind(kind),
            title=title,
            description=description,
            confidence=confidence,
            evidence_summary=evidence_summary,
            evidence_count=evidence_count,
            sources=tuple(sources),
            proposed_actions=tuple(proposed_actions),
            missing_inputs=tuple(missing_inputs),
            privacy_level=SuggestionPrivacyLevel(privacy_level),
        )

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "Suggestion":
        return cls(
            id=str(raw.get("id") or ""),
            kind=SuggestionKind(str(raw.get("kind") or "")),
            title=str(raw.get("title") or ""),
            description=str(raw.get("description") or ""),
            confidence=float(raw.get("confidence") or 0.0),
            evidence_summary=str(raw.get("evidence_summary") or ""),
            evidence_count=int(raw.get("evidence_count") or 0),
            sources=tuple(_sequence(raw.get("sources"))),
            proposed_actions=tuple(
                item for item in _sequence(raw.get("proposed_actions")) if isinstance(item, Mapping)
            ),
            missing_inputs=tuple(_sequence(raw.get("missing_inputs"))),
            privacy_level=SuggestionPrivacyLevel(str(raw.get("privacy_level") or "review")),
            created_at=str(raw.get("created_at") or ""),
            status=SuggestionStatus(str(raw.get("status") or "new")),
            approval=SuggestionApproval.from_mapping(raw.get("approval")),
            drafted_artifact_ref=str(raw.get("drafted_artifact_ref") or ""),
        )

    def with_status(
        self,
        status: SuggestionStatus | str,
        *,
        approval: SuggestionApproval | None = None,
        drafted_artifact_ref: str | None = None,
    ) -> "Suggestion":
        return Suggestion(
            id=self.id,
            kind=self.kind,
            title=self.title,
            description=self.description,
            confidence=self.confidence,
            evidence_summary=self.evidence_summary,
            evidence_count=self.evidence_count,
            sources=self.sources,
            proposed_actions=self.proposed_actions,
            missing_inputs=self.missing_inputs,
            privacy_level=self.privacy_level,
            created_at=self.created_at,
            status=SuggestionStatus(status),
            approval=approval if approval is not None else self.approval,
            drafted_artifact_ref=(
                self.drafted_artifact_ref
                if drafted_artifact_ref is None
                else _clean_text(drafted_artifact_ref)
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": SUGGESTION_SCHEMA_VERSION,
            "id": self.id,
            "kind": self.kind.value,
            "title": self.title,
            "description": self.description,
            "confidence": self.confidence,
            "evidence_summary": self.evidence_summary,
            "evidence_count": self.evidence_count,
            "sources": list(self.sources),
            "proposed_actions": [_json_ready(action) for action in self.proposed_actions],
            "missing_inputs": list(self.missing_inputs),
            "privacy_level": self.privacy_level.value,
            "created_at": self.created_at,
            "status": self.status.value,
            "approval": self.approval.to_dict() if self.approval else None,
            "drafted_artifact_ref": self.drafted_artifact_ref,
        }


def _sanitize_proposed_action(raw: Mapping[str, Any]) -> Mapping[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in raw.items():
        normalized_key = _clean_id(key)
        if (
            not normalized_key
            or normalized_key not in PROPOSED_ACTION_ALLOWED_KEYS
            or _is_executable_key(normalized_key)
        ):
            continue
        sanitized[normalized_key] = _sanitize_value(value)
    return sanitized


def _sanitize_value(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return _clean_public_text(value)
    if isinstance(value, Mapping):
        return dict(_sanitize_proposed_action(value))
    if isinstance(value, Sequence) and not isinstance(value, str):
        return [_sanitize_value(item) for item in list(value)[:MAX_COLLECTION_ITEMS]]
    return _clean_text(value)


def _is_executable_key(normalized_key: str) -> bool:
    return any(_key_contains_token(normalized_key, token) for token in EXECUTABLE_PROPOSED_ACTION_KEYS)


def _key_contains_token(normalized_key: str, token: str) -> bool:
    return (
        normalized_key == token
        or normalized_key.startswith(f"{token}_")
        or normalized_key.endswith(f"_{token}")
        or f"_{token}_" in normalized_key
    )


def _bounded_confidence(value: float) -> float:
    try:
        resolved = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, resolved))


def _clean_text_tuple(values: Sequence[object]) -> tuple[str, ...]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values[:MAX_COLLECTION_ITEMS]:
        text = _clean_text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        cleaned.append(text)
    return tuple(cleaned)


def _clean_missing_inputs(values: Sequence[object]) -> tuple[str, ...]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values[:MAX_COLLECTION_ITEMS]:
        if _contains_sensitive_text(value) or _contains_forbidden_value_token(value):
            continue
        text = _clean_id(value)
        if not text or text in seen or not MISSING_INPUT_ID_RE.match(text):
            continue
        if (
            _contains_sensitive_text(text)
            or _contains_forbidden_value_token(text)
            or _is_executable_key(text)
        ):
            continue
        seen.add(text)
        cleaned.append(text)
    return tuple(cleaned)


def _clean_public_text(value: object) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    if _contains_forbidden_value_token(text):
        return SENSITIVE_TEXT_REPLACEMENT
    if COMMAND_TEXT_RE.search(text):
        return SENSITIVE_TEXT_REPLACEMENT
    text = URL_RE.sub(SENSITIVE_TEXT_REPLACEMENT, text)
    text = WINDOWS_ABSOLUTE_PATH_RE.sub(SENSITIVE_TEXT_REPLACEMENT, text)
    text = POSIX_ABSOLUTE_PATH_RE.sub(SENSITIVE_TEXT_REPLACEMENT, text)
    if COMMAND_TEXT_RE.search(text):
        return SENSITIVE_TEXT_REPLACEMENT
    return _clean_text(text)


def _contains_sensitive_text(value: object) -> bool:
    text = _clean_text(value)
    return bool(
        URL_RE.search(text)
        or WINDOWS_ABSOLUTE_PATH_RE.search(text)
        or POSIX_ABSOLUTE_PATH_RE.search(text)
        or COMMAND_TEXT_RE.search(text)
    )


def _contains_forbidden_value_token(value: object) -> bool:
    text = _clean_text(value)
    normalized = normalize_learning_source_id(text)
    if is_forbidden_learning_source(normalized):
        return True
    return any(
        normalized == token
        or normalized.startswith(f"{token}_")
        or normalized.endswith(f"_{token}")
        or f"_{token}_" in normalized
        for token in FORBIDDEN_VALUE_TOKENS
    )


def _clean_text(value: object) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    return " ".join(text.split())[:MAX_TEXT_LENGTH]


def _clean_id(value: object) -> str:
    return _clean_text(value).casefold().replace("-", "_").replace(" ", "_")


def _safe_suggestion_id(value: object) -> str:
    text = _clean_text(value).casefold()
    if _contains_sensitive_text(text) or not SAFE_SUGGESTION_ID_RE.match(text):
        return uuid.uuid4().hex
    return text


def _safe_approval_id(value: object) -> str:
    if _contains_sensitive_text(value):
        return ""
    text = _clean_id(value)
    if _contains_sensitive_text(text) or not SAFE_APPROVAL_ID_RE.match(text):
        return ""
    return text


def _safe_timestamp(value: object) -> str:
    text = _clean_text(value)
    if _contains_sensitive_text(text) or not SAFE_TIMESTAMP_RE.match(text):
        return ""
    return text


def _clean_artifact_ref(value: object) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    if (
        URL_RE.search(text)
        or WINDOWS_ABSOLUTE_PATH_RE.search(text)
        or POSIX_ABSOLUTE_PATH_RE.match(text)
        or not SAFE_ARTIFACT_REF_RE.match(text)
        or any(part in {".", ".."} for part in text.replace("\\", "/").split("/"))
    ):
        return ""
    return text


def _sequence(value: object) -> list[Any]:
    if isinstance(value, list | tuple):
        return list(value)
    return []


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_json_ready(item) for item in value]
    return value


__all__ = [
    "EXECUTABLE_PROPOSED_ACTION_KEYS",
    "PROPOSED_ACTION_ALLOWED_KEYS",
    "SUGGESTION_SCHEMA_VERSION",
    "Suggestion",
    "SuggestionApproval",
    "SuggestionKind",
    "SuggestionPrivacyLevel",
    "SuggestionStatus",
]
