from __future__ import annotations

from pathlib import Path

from platformdirs import user_data_dir, user_log_dir

APP_NAME = "Ritualist"
APP_AUTHOR = "Ritualist"


def app_data_dir() -> Path:
    path = Path(user_data_dir(APP_NAME, APP_AUTHOR))
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_dir() -> Path:
    path = Path(user_log_dir(APP_NAME, APP_AUTHOR))
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_log_file() -> Path:
    return logs_dir() / "ritualist.log"
