from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


RITUALIST_JOURNAL_SOURCE_ID = "ritualist_journal"
OPEN_WINDOWS_SOURCE_ID = "open_windows"
RECENT_ITEMS_SOURCE_ID = "recent_items"

JOURNAL_EVENT_KIND = "journal_event"
PROCESS_NAME_KIND = "process_name"
WINDOW_METADATA_KIND = "window_metadata"
RECENT_REFERENCE_KIND = "recent_reference"

ALLOWED_ACTIVITY_SOURCE_IDS = (
    RITUALIST_JOURNAL_SOURCE_ID,
    OPEN_WINDOWS_SOURCE_ID,
    RECENT_ITEMS_SOURCE_ID,
)

ALLOWED_ACTIVITY_SIGNAL_KINDS = (
    JOURNAL_EVENT_KIND,
    PROCESS_NAME_KIND,
    WINDOW_METADATA_KIND,
    RECENT_REFERENCE_KIND,
)

RECENT_REFERENCE_TYPES = ("app", "file", "folder")

FORBIDDEN_ACTIVITY_SOURCE_IDS = frozenset(
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
        "keystrokes",
        "click_coordinates",
        "click-coordinates",
        "coordinates",
        "coordinate_capture",
        "coordinate-capture",
    }
)

FORBIDDEN_ACTIVITY_METADATA_KEYS = frozenset(
    {
        "body",
        "bitmap",
        "browser_history",
        "bounds",
        "click_coordinates",
        "content",
        "contents",
        "coordinate_capture",
        "coordinates",
        "file_content",
        "file_contents",
        "height",
        "href",
        "history",
        "html",
        "image",
        "javascript",
        "js",
        "key_log",
        "key_logger",
        "keyboard_logger",
        "keyboardlogger",
        "keylog",
        "keylogger",
        "keylogging",
        "keys",
        "keystrokes",
        "left",
        "ocr",
        "ocr_text",
        "pixels",
        "powershell",
        "python",
        "raw_browser_history",
        "rect",
        "recorder",
        "recording",
        "right",
        "screen_capture",
        "screen_recorder",
        "screenrecorder",
        "screencapture",
        "screenshot",
        "shell",
        "text_capture",
        "teach_by_watching",
        "teachbywatching",
        "top",
        "url",
        "url_history",
        "urls",
        "watch_me",
        "watchme",
        "width",
        "windows_recall",
        "windowsrecall",
        "x",
        "y",
    }
)
FORBIDDEN_ACTIVITY_METADATA_KEY_TOKENS = frozenset(
    {
        "browser_history",
        "browserhistory",
        "capture",
        "click_coordinate",
        "content",
        "coordinate",
        "history",
        "key_log",
        "key_logger",
        "keyboard_logger",
        "keyboardlogger",
        "keylog",
        "keylogger",
        "keylogging",
        "keystroke",
        "ocr",
        "password",
        "recording",
        "recorder",
        "screenshot",
        "screen_recorder",
        "screenrecorder",
        "screencapture",
        "teach_by_watching",
        "teachbywatching",
        "url",
        "watch_me",
        "watchme",
        "windows_recall",
        "windowsrecall",
    }
)

_KIND_SOURCE_IDS = {
    JOURNAL_EVENT_KIND: frozenset({RITUALIST_JOURNAL_SOURCE_ID}),
    PROCESS_NAME_KIND: frozenset({OPEN_WINDOWS_SOURCE_ID}),
    WINDOW_METADATA_KIND: frozenset({OPEN_WINDOWS_SOURCE_ID}),
    RECENT_REFERENCE_KIND: frozenset({RECENT_ITEMS_SOURCE_ID}),
}

_MAX_TEXT_LENGTH = 512


@dataclass(frozen=True)
class ActivitySignal:
    kind: str
    source_id: str
    label: str
    value: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        kind = normalize_activity_id(self.kind)
        source_id = normalize_activity_id(self.source_id)

        if source_id in _normalized_forbidden_sources():
            raise ValueError(f"forbidden activity source: {self.source_id}")
        if source_id not in ALLOWED_ACTIVITY_SOURCE_IDS:
            raise ValueError(f"unsupported activity source: {self.source_id}")
        if kind not in ALLOWED_ACTIVITY_SIGNAL_KINDS:
            raise ValueError(f"unsupported activity signal kind: {self.kind}")
        if source_id not in _KIND_SOURCE_IDS[kind]:
            raise ValueError(f"activity signal {kind!r} cannot use source {source_id!r}")

        metadata = normalize_activity_metadata(self.metadata)
        if kind == RECENT_REFERENCE_KIND:
            reference_type = normalize_activity_id(metadata.get("reference_type"))
            if reference_type not in RECENT_REFERENCE_TYPES:
                raise ValueError("recent references must be app, file, or folder references")
            metadata = {**metadata, "reference_type": reference_type}

        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "source_id", source_id)
        object.__setattr__(self, "label", _normalize_text(self.label))
        object.__setattr__(self, "value", _normalize_text(self.value))
        object.__setattr__(self, "metadata", metadata)

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "source_id": self.source_id,
            "label": self.label,
            "value": self.value,
            "metadata": _json_ready(self.metadata),
        }


@dataclass(frozen=True)
class ActivityWarning:
    code: str
    message: str
    source_id: str = ""
    severity: str = "warning"

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", normalize_activity_id(self.code))
        object.__setattr__(self, "message", _normalize_text(self.message))
        object.__setattr__(self, "source_id", normalize_activity_id(self.source_id))
        object.__setattr__(self, "severity", normalize_activity_id(self.severity) or "warning")

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
            "source_id": self.source_id,
            "severity": self.severity,
        }


@dataclass(frozen=True)
class ActivityCollectionResult:
    signals: tuple[ActivitySignal, ...] = ()
    warnings: tuple[ActivityWarning, ...] = ()
    supported: bool = True
    collector_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "signals", tuple(self.signals))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "collector_id", normalize_activity_id(self.collector_id))

    @classmethod
    def empty(cls, *, collector_id: str = "") -> "ActivityCollectionResult":
        return cls(collector_id=collector_id)

    @classmethod
    def unsupported(
        cls,
        *,
        collector_id: str,
        source_id: str,
        message: str,
        code: str = "unsupported_platform",
    ) -> "ActivityCollectionResult":
        return cls(
            supported=False,
            collector_id=collector_id,
            warnings=(
                ActivityWarning(code=code, message=message, source_id=source_id),
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "collector_id": self.collector_id,
            "supported": self.supported,
            "signals": [signal.to_dict() for signal in self.signals],
            "warnings": [warning.to_dict() for warning in self.warnings],
        }


def journal_event_signal(
    *,
    label: object,
    value: object = "",
    metadata: Mapping[str, Any] | None = None,
) -> ActivitySignal:
    return ActivitySignal(
        kind=JOURNAL_EVENT_KIND,
        source_id=RITUALIST_JOURNAL_SOURCE_ID,
        label=str(label or ""),
        value=str(value or ""),
        metadata=metadata or {},
    )


def process_name_signal(process_name: object) -> ActivitySignal:
    name = _normalize_text(process_name)
    return ActivitySignal(
        kind=PROCESS_NAME_KIND,
        source_id=OPEN_WINDOWS_SOURCE_ID,
        label=name,
        value=name,
        metadata={"process_name": name},
    )


def window_metadata_signal(
    *,
    title: object,
    app_name: object = "",
    process_name: object = "",
    foreground: bool | None = None,
) -> ActivitySignal:
    metadata: dict[str, object] = {
        "title": _normalize_text(title),
        "app_name": _normalize_text(app_name),
        "process_name": _normalize_text(process_name),
    }
    if foreground is not None:
        metadata["foreground"] = bool(foreground)
    return ActivitySignal(
        kind=WINDOW_METADATA_KIND,
        source_id=OPEN_WINDOWS_SOURCE_ID,
        label=_normalize_text(title) or _normalize_text(app_name) or _normalize_text(process_name),
        value=_normalize_text(app_name) or _normalize_text(process_name),
        metadata=metadata,
    )


def recent_reference_signal(
    *,
    reference_type: object,
    label: object,
    target: object,
) -> ActivitySignal:
    resolved_type = normalize_activity_id(reference_type)
    return ActivitySignal(
        kind=RECENT_REFERENCE_KIND,
        source_id=RECENT_ITEMS_SOURCE_ID,
        label=_normalize_text(label),
        value=_normalize_text(target),
        metadata={
            "reference_type": resolved_type,
            "target": _normalize_path_or_text(target),
        },
    )


def normalize_activity_id(value: object) -> str:
    normalized = str(value or "").strip().casefold()
    return normalized.replace("-", "_").replace(" ", "_")


def normalize_activity_metadata(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise TypeError("activity metadata must be a mapping")

    normalized: dict[str, Any] = {}
    for key, value in raw.items():
        normalized_key = normalize_activity_id(key)
        if not normalized_key:
            continue
        if _is_forbidden_metadata_key(normalized_key):
            raise ValueError(f"forbidden activity metadata key: {key}")
        normalized[normalized_key] = _sanitize_metadata_value(value)
    return normalized


def _is_forbidden_metadata_key(normalized_key: str) -> bool:
    if normalized_key in FORBIDDEN_ACTIVITY_METADATA_KEYS:
        return True
    return any(token in normalized_key for token in FORBIDDEN_ACTIVITY_METADATA_KEY_TOKENS)


def _sanitize_metadata_value(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, str):
        return _normalize_text(value)
    if isinstance(value, Mapping):
        return normalize_activity_metadata(value)
    if isinstance(value, list | tuple | set):
        return tuple(_sanitize_metadata_value(item) for item in value)
    return _normalize_text(value)


def _normalize_path_or_text(value: object) -> str:
    if isinstance(value, Path):
        return str(value)
    return _normalize_text(value)


def _normalize_text(value: object) -> str:
    normalized = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    return " ".join(normalized.split())[:_MAX_TEXT_LENGTH]


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, tuple | list | set):
        return [_json_ready(item) for item in value]
    return value


def _normalized_forbidden_sources() -> frozenset[str]:
    return frozenset(normalize_activity_id(source_id) for source_id in FORBIDDEN_ACTIVITY_SOURCE_IDS)


__all__ = [
    "ALLOWED_ACTIVITY_SIGNAL_KINDS",
    "ALLOWED_ACTIVITY_SOURCE_IDS",
    "FORBIDDEN_ACTIVITY_METADATA_KEYS",
    "FORBIDDEN_ACTIVITY_METADATA_KEY_TOKENS",
    "FORBIDDEN_ACTIVITY_SOURCE_IDS",
    "JOURNAL_EVENT_KIND",
    "OPEN_WINDOWS_SOURCE_ID",
    "PROCESS_NAME_KIND",
    "RECENT_ITEMS_SOURCE_ID",
    "RECENT_REFERENCE_KIND",
    "RECENT_REFERENCE_TYPES",
    "RITUALIST_JOURNAL_SOURCE_ID",
    "WINDOW_METADATA_KIND",
    "ActivityCollectionResult",
    "ActivitySignal",
    "ActivityWarning",
    "journal_event_signal",
    "normalize_activity_id",
    "normalize_activity_metadata",
    "process_name_signal",
    "recent_reference_signal",
    "window_metadata_signal",
]
