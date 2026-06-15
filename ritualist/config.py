from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .paths import config_file_path, default_log_file

DEFAULT_OVERLAY_DURATION_MS = 700


@dataclass(frozen=True)
class UIConfig:
    show_action_overlay: bool = True
    overlay_duration_ms: int = DEFAULT_OVERLAY_DURATION_MS
    preview_desktop_clicks: bool = True


@dataclass(frozen=True)
class AppConfig:
    default_browser: str = "chromium"
    log_level: str = "INFO"
    log_file: Path = default_log_file()
    ui: UIConfig = field(default_factory=UIConfig)


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
    log_file = Path(str(raw["log_file"])) if raw.get("log_file") else default_log_file()
    return AppConfig(
        default_browser=str(raw.get("default_browser") or "chromium"),
        log_level=str(raw.get("log_level") or "INFO"),
        log_file=log_file,
        ui=ui,
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
