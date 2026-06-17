from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .actions.base import AdapterBundle
from .errors import RitualistError
from .models import SAFE_ID_PATTERN, Recipe
from .paths import watch_me_dir

WATCH_ME_SCHEMA_VERSION = "ritualist.watch_me.v1"
DRAFT_SCHEMA_VERSION = "ritualist.watch_me.draft.v1"

FORBIDDEN_CAPTURE_MARKERS: tuple[str, ...] = (
    "password",
    "passwd",
    "credential",
    "secret",
    "token",
    "cookie",
    "clipboard",
    "screenshot",
    "keystroke",
    "keylog",
    "page_content",
    "page_contents",
    "html",
    "dom",
)


class WatchMeStatus(StrEnum):
    RECORDING = "recording"
    STOPPED = "stopped"
    DRAFT_CREATED = "draft_created"
    DISCARDED = "discarded"


class WatchMeSignalType(StrEnum):
    APP_LAUNCHED = "app_launched"
    FOREGROUND_WINDOW = "foreground_window"
    WINDOW_LAYOUT = "window_layout"
    BROWSER_URL = "browser_url"
    MONITOR_LAYOUT = "monitor_layout"
    NOTE = "note"


class WatchMeProcessSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    path: str | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("process name must not be blank")
        return text


class WatchMeEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: WatchMeSignalType
    timestamp: str
    data: dict[str, Any] = Field(default_factory=dict)


class WatchMeSession(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: str = Field(default=WATCH_ME_SCHEMA_VERSION, alias="schema")
    session_id: str
    status: WatchMeStatus
    started_at: str
    ended_at: str | None = None
    events: tuple[WatchMeEvent, ...] = ()
    baseline_process_keys: tuple[str, ...] = ()
    redaction_summary: tuple[str, ...] = ()
    draft_path: str | None = None

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        if value != WATCH_ME_SCHEMA_VERSION:
            raise ValueError(f"unsupported Watch Me schema: {value}")
        return value

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, value: str) -> str:
        if not SAFE_ID_PATTERN.fullmatch(value):
            raise ValueError("Watch Me session id must be a safe filename-like identifier")
        return value


class WatchMeDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: str = Field(default=DRAFT_SCHEMA_VERSION, alias="schema")
    session_id: str
    enabled: bool = False
    review_required: bool = True
    doctor_recommended: bool = True
    dry_run_recommended: bool = True
    recipe: dict[str, Any]
    intent: dict[str, Any]
    canvas_card: dict[str, Any]
    window_layout_suggestions: list[dict[str, Any]] = Field(default_factory=list)
    todo: list[str] = Field(default_factory=list)
    redaction_summary: list[str] = Field(default_factory=list)
    preview: list[str] = Field(default_factory=list)


ProcessProvider = Callable[[], list[dict[str, Any]]]
Clock = Callable[[], datetime]


class WatchMeService:
    def __init__(
        self,
        *,
        store_dir: Path | None = None,
        adapters: AdapterBundle | None = None,
        process_provider: ProcessProvider | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.store_dir = store_dir or watch_me_dir()
        self.adapters = adapters
        self.process_provider = process_provider or _safe_process_snapshot
        self.clock = clock or _utcnow

    def start(self) -> WatchMeSession:
        session_id = self._new_session_id()
        session = WatchMeSession(
            session_id=session_id,
            status=WatchMeStatus.RECORDING,
            started_at=_iso(self.clock()),
            baseline_process_keys=tuple(
                _process_fingerprint(process)
                for process in _processes_from_rows(self.process_provider())
            ),
        )
        session = self._append_safe_snapshot_events(session)
        self._write_session(session)
        return session

    def stop(self, session_id: str) -> WatchMeSession:
        session = self.load(session_id)
        if session.status is not WatchMeStatus.RECORDING:
            raise RitualistError(f"Watch Me session is not recording: {session.status.value}")

        events = list(session.events)
        redactions = list(session.redaction_summary)
        baseline = set(session.baseline_process_keys)
        for process in _processes_from_rows(self.process_provider()):
            if _process_fingerprint(process) not in baseline:
                event, notes = _safe_event(
                    WatchMeSignalType.APP_LAUNCHED,
                    {"name": process.name, "path": process.path},
                    timestamp=_iso(self.clock()),
                )
                if event is not None:
                    events.append(event)
                redactions.extend(notes)

        stopped = session.model_copy(
            update={
                "status": WatchMeStatus.STOPPED,
                "ended_at": _iso(self.clock()),
                "events": tuple(events),
                "redaction_summary": tuple(_dedupe(redactions)),
            }
        )
        stopped = self._append_safe_snapshot_events(stopped)
        self._write_session(stopped)
        return stopped

    def record_event(
        self,
        session_id: str,
        signal_type: WatchMeSignalType | str,
        data: dict[str, Any],
    ) -> WatchMeSession:
        session = self.load(session_id)
        if session.status not in {WatchMeStatus.RECORDING, WatchMeStatus.STOPPED}:
            raise RitualistError(f"cannot add Watch Me events to {session.status.value} session")
        event, notes = _safe_event(
            WatchMeSignalType(signal_type),
            data,
            timestamp=_iso(self.clock()),
        )
        events = list(session.events)
        if event is not None:
            events.append(event)
        updated = session.model_copy(
            update={
                "events": tuple(events),
                "redaction_summary": tuple(_dedupe([*session.redaction_summary, *notes])),
            }
        )
        self._write_session(updated)
        return updated

    def create_draft(self, session_id: str) -> WatchMeDraft:
        session = self.load(session_id)
        if session.status is WatchMeStatus.DISCARDED:
            raise RitualistError("discarded Watch Me sessions cannot create drafts")
        if session.status is not WatchMeStatus.STOPPED:
            raise RitualistError("Watch Me session must be stopped before creating a draft")
        draft = build_watch_me_draft(session)
        session_dir = self._session_dir(session.session_id)
        session_dir.mkdir(parents=True, exist_ok=True)
        draft_json_path = session_dir / "draft.json"
        draft_recipe_path = session_dir / "draft_recipe.yaml"
        draft_json_path.write_text(
            json.dumps(draft.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        draft_recipe_path.write_text(
            yaml.safe_dump(draft.recipe, sort_keys=False),
            encoding="utf-8",
        )
        updated = session.model_copy(
            update={
                "status": WatchMeStatus.DRAFT_CREATED,
                "draft_path": str(draft_json_path),
            }
        )
        self._write_session(updated)
        return draft

    def discard(self, session_id: str) -> WatchMeSession:
        session = self.load(session_id)
        discarded = session.model_copy(update={"status": WatchMeStatus.DISCARDED})
        self._write_session(discarded)
        return discarded

    def load(self, session_id: str) -> WatchMeSession:
        path = self._session_path(session_id)
        if not path.exists():
            raise RitualistError(f"Watch Me session not found: {session_id}")
        return WatchMeSession.model_validate_json(path.read_text(encoding="utf-8"))

    def _append_safe_snapshot_events(self, session: WatchMeSession) -> WatchMeSession:
        if self.adapters is None:
            return session
        events = list(session.events)
        redactions = list(session.redaction_summary)
        for event_type, data in _snapshot_events(self.adapters):
            event, notes = _safe_event(event_type, data, timestamp=_iso(self.clock()))
            if event is not None:
                events.append(event)
            redactions.extend(notes)
        return session.model_copy(
            update={
                "events": tuple(events),
                "redaction_summary": tuple(_dedupe(redactions)),
            }
        )

    def _write_session(self, session: WatchMeSession) -> None:
        path = self._session_path(session.session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(session.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _session_dir(self, session_id: str) -> Path:
        _validate_session_id(session_id)
        return self.store_dir / session_id

    def _session_path(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "session.json"

    def _new_session_id(self) -> str:
        stamp = self.clock().strftime("%Y%m%dT%H%M%SZ")
        return f"{stamp}_{uuid.uuid4().hex[:8]}"


def build_watch_me_draft(session: WatchMeSession) -> WatchMeDraft:
    recipe_id = f"watch_me_{_short_hash(session.session_id)}"
    steps: list[dict[str, Any]] = []
    todo: list[str] = []
    seen_apps: set[str] = set()
    seen_urls: set[str] = set()
    window_suggestions: list[dict[str, Any]] = []

    for event in session.events:
        if event.type is WatchMeSignalType.APP_LAUNCHED:
            name = str(event.data.get("name") or "").strip()
            path = str(event.data.get("path") or "").strip()
            key = path or name
            if not key or key in seen_apps:
                continue
            seen_apps.add(key)
            if path:
                steps.append({"action": "app.launch", "command": path})
            elif name:
                steps.append(
                    {
                        "action": "human.prompt",
                        "prompt": f"TODO: Confirm how Ritualist should launch {name}.",
                    }
                )
                todo.append(f"Confirm launch path for {name}.")
        elif event.type is WatchMeSignalType.BROWSER_URL:
            url = str(event.data.get("url") or "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            steps.append(
                {
                    "action": "browser.open",
                    "url": url,
                    "profile": recipe_id,
                    "clean_start": True,
                    "dismiss_restore_prompt": True,
                    "use_dedicated_profile": True,
                }
            )
        elif event.type is WatchMeSignalType.WINDOW_LAYOUT:
            windows = event.data.get("windows")
            if isinstance(windows, list):
                for window in windows[:10]:
                    if isinstance(window, dict):
                        title = str(window.get("title") or "").strip()
                        bounds = window.get("bounds")
                        if title and isinstance(bounds, dict):
                            window_suggestions.append({"title": title, "bounds": bounds})

    if not steps:
        steps.append(
            {
                "action": "human.prompt",
                "prompt": "TODO: Review this Watch Me session and add safe launch/browser steps.",
            }
        )
        todo.append("No app launches or browser URLs were captured; review the session manually.")

    recipe = {
        "version": "0.1",
        "id": recipe_id,
        "name": "Watch Me Draft",
        "description": (
            "Draft generated from an explicit Watch Me session. Review, run Doctor, "
            "and dry-run before saving as a real ritual."
        ),
        "home": {
            "category": "Drafts",
            "card": {
                "title": "Watch Me Draft",
                "subtitle": "Review before saving",
                "image": "",
                "accent": "",
            },
        },
        "steps": steps,
    }
    Recipe.model_validate(recipe)

    preview = build_watch_me_preview(
        steps=steps,
        window_layout_suggestions=window_suggestions,
        todo=todo,
    )

    return WatchMeDraft(
        session_id=session.session_id,
        recipe=recipe,
        intent={
            "intent_id": recipe_id,
            "kind": "workspace.prepare",
            "display_name": "Watch Me Draft",
            "requested_outcome": "Recreate the observed setup after review.",
            "user_visible_summary": "Review required before this draft can be saved or run.",
        },
        canvas_card={
            "enabled": False,
            "type": "ritual.card",
            "props": {
                "title": "Watch Me Draft",
                "recipe_id": recipe_id,
                "primary_action": "dry_run",
            },
            "note": "Suggested card only; not installed automatically.",
        },
        window_layout_suggestions=window_suggestions,
        todo=todo,
        redaction_summary=list(session.redaction_summary),
        preview=preview,
    )


def build_watch_me_preview(
    *,
    steps: list[dict[str, Any]],
    window_layout_suggestions: list[dict[str, Any]],
    todo: list[str],
) -> list[str]:
    preview: list[str] = []
    for index, step in enumerate(steps[:10], start=1):
        action = str(step.get("action") or "step")
        if action == "app.launch":
            detail = _preview_value(step.get("command"))
        elif action == "browser.open":
            detail = _preview_value(step.get("url"))
        elif action == "human.prompt":
            detail = _preview_value(step.get("prompt"))
        else:
            detail = _preview_value(step.get("name") or step.get("id") or "")
        suffix = f": {detail}" if detail else ""
        preview.append(f"{index}. {action}{suffix}")
    for window in window_layout_suggestions[:5]:
        title = _preview_value(window.get("title"))
        bounds = window.get("bounds")
        if title and isinstance(bounds, dict):
            preview.append(
                "window: "
                f"{title} at {bounds.get('x', '?')},{bounds.get('y', '?')} "
                f"{bounds.get('width', '?')}x{bounds.get('height', '?')}"
            )
    for item in todo[:5]:
        preview.append(f"TODO: {_preview_value(item)}")
    return preview


def _safe_event(
    signal_type: WatchMeSignalType,
    data: dict[str, Any],
    *,
    timestamp: str,
) -> tuple[WatchMeEvent | None, list[str]]:
    notes: list[str] = []
    if signal_type is WatchMeSignalType.BROWSER_URL:
        if _truthy(data.get("private")) or _truthy(data.get("incognito")):
            return None, ["skipped private/incognito browser URL"]
        url = str(data.get("url") or "").strip()
        if not url:
            return None, ["dropped browser URL event without URL"]
        redacted, redaction_notes = redact_url(url)
        notes.extend(redaction_notes)
        return WatchMeEvent(type=signal_type, timestamp=timestamp, data={"url": redacted}), notes

    sanitized: dict[str, Any] = {}
    for key, value in data.items():
        key_text = str(key).strip()
        if not key_text:
            continue
        if _is_forbidden_key(key_text):
            notes.append(f"dropped forbidden field: {key_text}")
            continue
        sanitized[key_text] = _sanitize_value(value, notes)

    return WatchMeEvent(type=signal_type, timestamp=timestamp, data=sanitized), notes


def redact_url(raw_url: str) -> tuple[str, list[str]]:
    notes: list[str] = []
    try:
        parts = urlsplit(raw_url)
    except ValueError:
        return "[unavailable]", ["redacted invalid URL"]
    if not parts.scheme or not parts.netloc:
        return raw_url.split("?", 1)[0].split("#", 1)[0], notes

    if parts.username or parts.password:
        notes.append("removed URL userinfo")
    if parts.query:
        notes.append("removed URL query")
    if parts.fragment:
        notes.append("removed URL fragment")

    host = parts.hostname or ""
    try:
        port = parts.port
    except ValueError:
        return "[unavailable]", ["redacted invalid URL port"]
    netloc = f"{host}:{port}" if port is not None else host
    path = _safe_url_path(parts.path, notes)
    return urlunsplit((parts.scheme, netloc, path, "", "")), notes


def _snapshot_events(adapters: AdapterBundle) -> list[tuple[WatchMeSignalType, dict[str, Any]]]:
    events: list[tuple[WatchMeSignalType, dict[str, Any]]] = []
    try:
        title = adapters.window.foreground_window_title()
        if title:
            events.append((WatchMeSignalType.FOREGROUND_WINDOW, {"title": title}))
    except Exception:  # noqa: BLE001 - Watch Me snapshots are best-effort.
        pass
    try:
        windows = adapters.window.list_windows()
        if windows:
            events.append((WatchMeSignalType.WINDOW_LAYOUT, {"windows": windows[:20]}))
    except Exception:  # noqa: BLE001
        pass
    try:
        monitors = [
            {
                "x": rect.x,
                "y": rect.y,
                "width": rect.width,
                "height": rect.height,
            }
            for rect in adapters.window.list_monitors()
        ]
        if monitors:
            events.append((WatchMeSignalType.MONITOR_LAYOUT, {"monitors": monitors}))
    except Exception:  # noqa: BLE001
        pass
    try:
        page = adapters.browser.page_context()
        url = str(page.get("url") or "").strip()
        if url and url != "about:blank":
            events.append((WatchMeSignalType.BROWSER_URL, {"url": url}))
    except Exception:  # noqa: BLE001
        pass
    return events


def _safe_process_snapshot() -> list[dict[str, Any]]:
    try:
        import psutil
    except ImportError:
        return []
    rows: list[dict[str, Any]] = []
    for process in psutil.process_iter(["name", "exe"]):
        try:
            rows.append(
                {
                    "name": process.info.get("name") or "",
                    "path": process.info.get("exe") or None,
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return rows


def _processes_from_rows(rows: list[dict[str, Any]]) -> list[WatchMeProcessSnapshot]:
    processes: list[WatchMeProcessSnapshot] = []
    for row in rows:
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        path = _safe_local_path(row.get("path"))
        processes.append(WatchMeProcessSnapshot(name=name, path=path))
    return processes


def _safe_local_path(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    lowered = text.casefold()
    if any(marker in lowered for marker in FORBIDDEN_CAPTURE_MARKERS):
        return None
    return text


def _sanitize_value(value: Any, notes: list[str]) -> Any:
    if isinstance(value, str):
        if _looks_like_url(value):
            redacted, redaction_notes = redact_url(value)
            notes.extend(redaction_notes)
            return redacted
        if _contains_forbidden_marker(value):
            notes.append("redacted sensitive text value")
            return "[redacted]"
        return value
    if isinstance(value, bool) or isinstance(value, int) or isinstance(value, float) or value is None:
        return value
    if isinstance(value, list):
        return [_sanitize_value(item, notes) for item in value]
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if _is_forbidden_key(key_text):
                notes.append(f"dropped forbidden field: {key_text}")
                continue
            result[key_text] = _sanitize_value(item, notes)
        return result
    return str(value)


def _safe_url_path(path: str, notes: list[str]) -> str:
    lowered = path.casefold()
    if _contains_forbidden_marker(lowered):
        notes.append("redacted sensitive URL path")
        return "/[redacted]"
    return path


def _preview_value(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if _looks_like_url(text):
        redacted, _notes = redact_url(text)
        return redacted
    if _contains_forbidden_marker(text):
        return "[redacted]"
    return text


def _is_forbidden_key(key: str) -> bool:
    return _contains_forbidden_marker(key)


def _contains_forbidden_marker(value: str) -> bool:
    lowered = value.casefold()
    return any(marker in lowered for marker in FORBIDDEN_CAPTURE_MARKERS)


def _looks_like_url(value: str) -> bool:
    lowered = value.casefold()
    return lowered.startswith("http://") or lowered.startswith("https://")


def _process_key(process: WatchMeProcessSnapshot) -> str:
    return f"{process.name.casefold()}|{(process.path or '').casefold()}"


def _process_fingerprint(process: WatchMeProcessSnapshot) -> str:
    return _short_hash(_process_key(process))


def _short_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:10]


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes", "y"}
    return bool(value)


def _dedupe(values: list[str] | tuple[str, ...]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _validate_session_id(session_id: str) -> None:
    if not SAFE_ID_PATTERN.fullmatch(session_id):
        raise RitualistError("Watch Me session id must be a safe filename-like identifier")
