from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .paths import default_log_file


@dataclass(frozen=True)
class AppConfig:
    default_browser: str = "chromium"
    log_level: str = "INFO"
    log_file: Path = default_log_file()
