from __future__ import annotations

from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
import uuid

from .paths import app_data_path


JOURNAL_SCHEMA_VERSION = "setpiece.activity_journal.v1"
JOURNAL_FILENAME = "activity-journal.jsonl"
MAX_READ_LIMIT = 500

ALLOWED_EVENT_TYPES = frozenset(
    {
        "room_opened",
        "component_clicked",
        "shortcut_opened",
        "recipe_run_started",
        "recipe_run_finished",
        "recipe_doctor_run",
        "recipe_dry_run",
    }
)

_FORBIDDEN_FIELD_NAMES = frozenset(
    {
        "browser_history",
        "bounds",
        "capture",
        "click_x",
        "click_y",
        "coordinate",
        "coordinates",
        "image",
        "key",
        "keys",
        "keystroke",
        "keystrokes",
        "mouse_x",
        "mouse_y",
        "ocr",
        "password",
        "pixels",
        "point",
        "position",
        "rect",
        "recording",
        "screenshot",
        "typed_text",
        "x",
        "y",
    }
)
_SENSITIVE_KEY_TOKENS = (
    "coordinate",
    "history",
    "keystroke",
    "password",
    "recording",
    "screenshot",
)
_PATH_KEY_TOKENS = ("path", "file", "folder", "directory", "command")
_URL_KEY_TOKENS = ("url", "uri", "link", "href")
_WINDOWS_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]")


EnabledPredicate = Callable[[], bool]


@dataclass(frozen=True)
class JournalEvent:
    event_type: str
    payload: dict[str, Any]


class ActivityJournal:
    def __init__(
        self,
        *,
        path: Path | None = None,
        enabled: bool | EnabledPredicate = False,
    ) -> None:
        self.path = path or default_journal_path()
        self._enabled = enabled

    def write(self, event_type: str, **payload: Any) -> bool:
        if not self.enabled:
            return False
        if event_type not in ALLOWED_EVENT_TYPES:
            return False
        entry = _journal_entry(event_type, payload)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
        except (OSError, TypeError, ValueError):
            return False
        return True

    def read(self, *, limit: int = 100) -> list[JournalEvent]:
        return read_journal(self.path, limit=limit)

    def delete(self) -> bool:
        return delete_journal(self.path)

    @property
    def enabled(self) -> bool:
        enabled = self._enabled
        if callable(enabled):
            try:
                return bool(enabled())
            except Exception:  # noqa: BLE001 - opt-in checks must not break callers.
                return False
        return bool(enabled)


def default_journal_path() -> Path:
    return app_data_path() / JOURNAL_FILENAME


def read_journal(path: Path, *, limit: int = 100) -> list[JournalEvent]:
    limit = _bounded_limit(limit)
    if limit <= 0 or not path.exists():
        return []
    events: deque[JournalEvent] = deque(maxlen=limit)
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                event = _parse_event_line(line)
                if event is not None:
                    events.append(event)
    except OSError:
        return []
    return list(events)


def delete_journal(path: Path) -> bool:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return False
    return True


def _journal_entry(event_type: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": JOURNAL_SCHEMA_VERSION,
        "id": uuid.uuid4().hex,
        "at": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "payload": _sanitize_payload(payload),
    }


def _sanitize_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in payload.items():
        key_text = str(key).strip()
        if not key_text or _is_forbidden_key(key_text):
            continue
        sanitized[key_text] = _sanitize_value(key_text, value)
    return sanitized


def _sanitize_value(key: str, value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return _sanitize_text(key, value)
    if isinstance(value, Path):
        return _path_label(value)
    if isinstance(value, Mapping):
        return _sanitize_payload(value)
    if isinstance(value, list | tuple):
        return [_sanitize_value(key, item) for item in value[:50]]
    return str(value)


def _sanitize_text(key: str, value: str) -> str:
    text = value.strip()
    key_lower = key.casefold()
    if _looks_like_url(text) or any(token in key_lower for token in _URL_KEY_TOKENS):
        return _url_label(text)
    if _looks_like_path(text) or any(token in key_lower for token in _PATH_KEY_TOKENS):
        return _path_label(Path(text))
    return text


def _is_forbidden_key(key: str) -> bool:
    normalized = key.strip().casefold()
    if normalized in _FORBIDDEN_FIELD_NAMES:
        return True
    return any(token in normalized for token in _SENSITIVE_KEY_TOKENS)


def _looks_like_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme.casefold() in {"http", "https"} and bool(parsed.netloc)


def _url_label(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme.casefold() in {"http", "https"} and parsed.netloc:
        return parsed.netloc
    return ""


def _looks_like_path(value: str) -> bool:
    if _WINDOWS_PATH_RE.match(value) or value.startswith(("/", "\\", "~")):
        return True
    return "\\" in value or "/" in value


def _path_label(path: Path) -> str:
    name = path.name
    if name:
        return name
    text = str(path).strip()
    if text in {"/", "\\"}:
        return text
    return Path(text.rstrip("\\/")).name or "local path"


def _parse_event_line(line: str) -> JournalEvent | None:
    if not line.strip():
        return None
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    if data.get("schema_version") != JOURNAL_SCHEMA_VERSION:
        return None
    event_type = str(data.get("event_type") or "")
    if event_type not in ALLOWED_EVENT_TYPES:
        return None
    payload = data.get("payload")
    if not isinstance(payload, dict):
        payload = {}
    return JournalEvent(event_type=event_type, payload=_sanitize_payload(payload))


def _bounded_limit(limit: int) -> int:
    try:
        value = int(limit)
    except (TypeError, ValueError):
        return 100
    return max(0, min(value, MAX_READ_LIMIT))
