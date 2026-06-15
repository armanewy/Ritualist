from __future__ import annotations

from pathlib import Path

from platformdirs import user_data_dir, user_log_dir

APP_NAME = "Ritualist"
APP_AUTHOR = "Ritualist"


def app_data_dir() -> Path:
    path = Path(user_data_dir(APP_NAME, APP_AUTHOR))
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_dir() -> Path:
    path = app_data_dir() / "config"
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_file() -> Path:
    return config_dir() / "config.yaml"


def recipes_dir() -> Path:
    path = app_data_dir() / "recipes"
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_dir() -> Path:
    path = Path(user_log_dir(APP_NAME, APP_AUTHOR))
    path.mkdir(parents=True, exist_ok=True)
    return path


def runs_dir() -> Path:
    path = app_data_dir() / "runs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def browser_profiles_dir() -> Path:
    path = app_data_dir() / "browser-profiles"
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_log_file() -> Path:
    return logs_dir() / "ritualist.log"


def ensure_app_dirs() -> dict[str, Path]:
    paths = {
        "app_data": app_data_dir(),
        "config": config_dir(),
        "recipes": recipes_dir(),
        "logs": logs_dir(),
        "runs": runs_dir(),
        "browser_profiles": browser_profiles_dir(),
    }
    return paths
