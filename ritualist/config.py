from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .paths import config_file_path, default_log_file

DEFAULT_OVERLAY_DURATION_MS = 700
DEFAULT_HOME_CATEGORIES = (
    "Gaming",
    "Media",
    "Coding",
    "News",
    "Helpdesk",
    "Settings",
)


@dataclass(frozen=True)
class UIConfig:
    show_action_overlay: bool = True
    overlay_duration_ms: int = DEFAULT_OVERLAY_DURATION_MS
    preview_desktop_clicks: bool = True


@dataclass(frozen=True)
class HomeConfig:
    categories: tuple[str, ...] = DEFAULT_HOME_CATEGORIES


@dataclass(frozen=True)
class AppConfig:
    default_browser: str = "chromium"
    log_level: str = "INFO"
    log_file: Path = default_log_file()
    ui: UIConfig = field(default_factory=UIConfig)
    home: HomeConfig = field(default_factory=HomeConfig)


def load_app_config(path: Path | None = None) -> AppConfig:
    source = path or config_file_path()
    try:
        raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raw = {}
    except (OSError, yaml.YAMLError):
        raw = {}
    if not isinstance(raw, dict):
        raw = {}

    ui_raw = raw.get("ui")
    ui = _load_ui_config(ui_raw if isinstance(ui_raw, dict) else {})
    home_raw = raw.get("home")
    home = _load_home_config(home_raw if isinstance(home_raw, dict) else {})
    log_file = Path(str(raw["log_file"])) if raw.get("log_file") else default_log_file()
    return AppConfig(
        default_browser=str(raw.get("default_browser") or "chromium"),
        log_level=str(raw.get("log_level") or "INFO"),
        log_file=log_file,
        ui=ui,
        home=home,
    )


def _load_ui_config(raw: dict[str, Any]) -> UIConfig:
    duration = raw.get("overlay_duration_ms", DEFAULT_OVERLAY_DURATION_MS)
    try:
        duration_int = int(duration)
    except (TypeError, ValueError):
        duration_int = DEFAULT_OVERLAY_DURATION_MS
    return UIConfig(
        show_action_overlay=bool(raw.get("show_action_overlay", True)),
        overlay_duration_ms=max(0, duration_int),
        preview_desktop_clicks=bool(raw.get("preview_desktop_clicks", True)),
    )


def _load_home_config(raw: dict[str, Any]) -> HomeConfig:
    return HomeConfig(categories=_load_home_categories(raw.get("categories")))


def _load_home_categories(raw: object) -> tuple[str, ...]:
    if not isinstance(raw, list | tuple):
        return DEFAULT_HOME_CATEGORIES

    labels: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if item is None:
            continue
        label = str(item).strip()
        if not label:
            continue
        key = label.casefold()
        if key in seen:
            continue
        seen.add(key)
        labels.append(label)

    return tuple(labels) or DEFAULT_HOME_CATEGORIES
