from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .models import SAFE_ID_PATTERN
from .paths import layouts_dir

LAYOUT_SCHEMA_VERSION = 1


class WindowCaptureAdapter(Protocol):
    def find_window_region(
        self,
        *,
        title_contains: str | None,
        process_name: str | None,
        timeout_seconds: float,
    ) -> Any:
        """Return current window metadata without launching or moving applications."""


class LayoutBounds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: int
    y: int
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class LayoutWindowMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title_contains: str | None = None
    process_name: str | None = None

    @model_validator(mode="after")
    def require_window_matcher(self) -> "LayoutWindowMatch":
        if not self.title_contains and not self.process_name:
            raise ValueError("provide title_contains or process_name")
        return self


class LayoutWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    match: LayoutWindowMatch
    bounds: LayoutBounds | None = None
    monitor_id: str | None = None
    monitor_index: int | None = None
    window_title: str | None = None
    capture_status: Literal["captured", "missing"] = "missing"


class Layout(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[LAYOUT_SCHEMA_VERSION] = LAYOUT_SCHEMA_VERSION
    layout_id: str
    windows: list[LayoutWindow] = Field(default_factory=list)

    @field_validator("layout_id")
    @classmethod
    def validate_layout_id(cls, value: str) -> str:
        if not SAFE_ID_PATTERN.fullmatch(value):
            raise ValueError(
                "layout_id must be a safe filename-like identifier "
                "(letters, numbers, hyphen, underscore)"
            )
        return value


def layout_file_path(layout_id: str, *, base_dir: Path | None = None) -> Path:
    _validate_layout_id(layout_id)
    return (base_dir or layouts_dir()) / f"{layout_id}.json"


def save_layout_snapshot(
    layout_id: str,
    window_matches: Iterable[LayoutWindowMatch | Mapping[str, Any]],
    *,
    window_adapter: WindowCaptureAdapter,
    path: Path | None = None,
    base_dir: Path | None = None,
) -> Layout:
    """Capture visible window bounds and store an inert local layout file.

    Missing windows are recorded as best-effort entries. This function only probes
    currently visible windows with a zero-second timeout; it never launches apps or
    applies layout changes.
    """

    matches = [_coerce_match(match) for match in window_matches]
    layout = Layout(
        layout_id=layout_id,
        windows=[_capture_window(match, window_adapter=window_adapter) for match in matches],
    )
    destination = path or layout_file_path(layout_id, base_dir=base_dir)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(layout.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return layout


def load_layout(layout_id_or_path: str | Path, *, base_dir: Path | None = None) -> Layout | None:
    path = _resolve_layout_reference(layout_id_or_path, base_dir=base_dir)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return Layout.model_validate(raw)
    except (OSError, json.JSONDecodeError, ValidationError):
        return None


def _resolve_layout_reference(layout_id_or_path: str | Path, *, base_dir: Path | None) -> Path:
    raw = Path(layout_id_or_path)
    if raw.exists() or raw.parent != Path(".") or raw.suffix:
        return raw
    return layout_file_path(str(layout_id_or_path), base_dir=base_dir)


def _capture_window(
    match: LayoutWindowMatch,
    *,
    window_adapter: WindowCaptureAdapter,
) -> LayoutWindow:
    try:
        region = window_adapter.find_window_region(
            title_contains=match.title_contains,
            process_name=match.process_name,
            timeout_seconds=0,
        )
    except Exception:  # noqa: BLE001 - missing/inaccessible windows are best-effort.
        return LayoutWindow(match=match, capture_status="missing")

    return LayoutWindow(
        match=match,
        bounds=_bounds_from_region(region),
        monitor_id=_monitor_id_from_region(region),
        monitor_index=_monitor_index_from_region(region),
        window_title=_optional_str(getattr(region, "window_title", None)),
        capture_status="captured",
    )


def _coerce_match(match: LayoutWindowMatch | Mapping[str, Any]) -> LayoutWindowMatch:
    if isinstance(match, LayoutWindowMatch):
        return match
    return LayoutWindowMatch.model_validate(dict(match))


def _bounds_from_region(region: Any) -> LayoutBounds | None:
    rect = getattr(region, "rect", None)
    if rect is None or not getattr(rect, "is_valid", True):
        return None
    try:
        return LayoutBounds(
            x=int(getattr(rect, "x")),
            y=int(getattr(rect, "y")),
            width=int(getattr(rect, "width")),
            height=int(getattr(rect, "height")),
        )
    except (TypeError, ValueError, AttributeError, ValidationError):
        return None


def _monitor_id_from_region(region: Any) -> str | None:
    monitor_id = _optional_str(getattr(region, "monitor_id", None))
    if monitor_id is not None:
        return monitor_id
    monitor = getattr(region, "monitor", None)
    if monitor is None:
        return None
    return _optional_str(getattr(monitor, "id", None) or getattr(monitor, "name", None))


def _monitor_index_from_region(region: Any) -> int | None:
    monitor_index = _optional_int(getattr(region, "monitor_index", None))
    if monitor_index is not None:
        return monitor_index
    monitor = getattr(region, "monitor", None)
    if monitor is None:
        return None
    return _optional_int(getattr(monitor, "index", None))


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _validate_layout_id(layout_id: str) -> None:
    if not SAFE_ID_PATTERN.fullmatch(layout_id):
        raise ValueError(
            "layout_id must be a safe filename-like identifier "
            "(letters, numbers, hyphen, underscore)"
        )
