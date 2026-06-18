from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from .learning_config import LocalLearningConfig
from .paths import config_file_path, default_log_file

if TYPE_CHECKING:
    from .canvas.performance import CanvasPerformanceSettings

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
    min_status_dwell_ms: int = 1200


@dataclass(frozen=True)
class CanvasConfig:
    performance_mode: str = "balanced"
    show_performance_overlay: bool = False

    def performance_settings(self) -> "CanvasPerformanceSettings":
        from .canvas.performance import performance_settings_for_mode

        return performance_settings_for_mode(
            self.performance_mode,
            show_performance_overlay=self.show_performance_overlay,
        )


@dataclass(frozen=True)
class AppConfig:
    default_browser: str = "chromium"
    log_level: str = "INFO"
    log_file: Path = field(default_factory=default_log_file)
    ui: UIConfig = field(default_factory=UIConfig)
    home: HomeConfig = field(default_factory=HomeConfig)
    canvas: CanvasConfig = field(default_factory=CanvasConfig)
    learning: LocalLearningConfig = field(default_factory=LocalLearningConfig)


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
    canvas_raw = raw.get("canvas")
    canvas = _load_canvas_config(canvas_raw if isinstance(canvas_raw, dict) else {})
    learning_raw = raw.get("learning")
    learning = LocalLearningConfig.from_mapping(
        learning_raw if isinstance(learning_raw, dict) else {}
    )
    log_file = Path(str(raw["log_file"])) if raw.get("log_file") else default_log_file()
    return AppConfig(
        default_browser=str(raw.get("default_browser") or "chromium"),
        log_level=str(raw.get("log_level") or "INFO"),
        log_file=log_file,
        ui=ui,
        home=home,
        canvas=canvas,
        learning=learning,
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
    dwell = raw.get("min_status_dwell_ms", 1200)
    try:
        dwell_int = int(dwell)
    except (TypeError, ValueError):
        dwell_int = 1200
    return HomeConfig(
        categories=_load_home_categories(raw.get("categories")),
        min_status_dwell_ms=max(0, dwell_int),
    )


def _load_canvas_config(raw: dict[str, Any]) -> CanvasConfig:
    return CanvasConfig(
        performance_mode=str(raw.get("performance_mode") or "balanced").strip().casefold()
        or "balanced",
        show_performance_overlay=bool(raw.get("show_performance_overlay", False)),
    )


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
