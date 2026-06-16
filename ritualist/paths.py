from __future__ import annotations

from pathlib import Path

from platformdirs import user_data_dir, user_log_dir

APP_NAME = "Ritualist"
APP_AUTHOR = "Ritualist"


def app_data_dir() -> Path:
    path = app_data_path()
    path.mkdir(parents=True, exist_ok=True)
    return path


def app_data_path() -> Path:
    return Path(user_data_dir(APP_NAME, APP_AUTHOR))


def config_dir() -> Path:
    path = config_path()
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    return app_data_path() / "config"


def config_file() -> Path:
    return config_dir() / "config.yaml"


def config_file_path() -> Path:
    return config_path() / "config.yaml"


def recipes_dir() -> Path:
    path = recipes_path()
    path.mkdir(parents=True, exist_ok=True)
    return path


def recipes_path() -> Path:
    return app_data_path() / "recipes"


def imported_packs_dir() -> Path:
    path = imported_packs_path()
    path.mkdir(parents=True, exist_ok=True)
    return path


def imported_packs_path() -> Path:
    return app_data_path() / "imported-packs"


def logs_dir() -> Path:
    path = logs_path()
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_path() -> Path:
    return Path(user_log_dir(APP_NAME, APP_AUTHOR))


def runs_dir() -> Path:
    path = runs_path()
    path.mkdir(parents=True, exist_ok=True)
    return path


def runs_path() -> Path:
    return app_data_path() / "runs"


def layouts_dir() -> Path:
    path = layouts_path()
    path.mkdir(parents=True, exist_ok=True)
    return path


def layouts_path() -> Path:
    return app_data_path() / "layouts"


def browser_profiles_dir() -> Path:
    path = browser_profiles_path()
    path.mkdir(parents=True, exist_ok=True)
    return path


def browser_profiles_path() -> Path:
    return app_data_path() / "browser-profiles"


def default_log_file() -> Path:
    return logs_dir() / "ritualist.log"


def ensure_app_dirs() -> dict[str, Path]:
    paths = {
        "app_data": app_data_dir(),
        "config": config_dir(),
        "recipes": recipes_dir(),
        "imported_packs": imported_packs_dir(),
        "logs": logs_dir(),
        "runs": runs_dir(),
        "browser_profiles": browser_profiles_dir(),
    }
    return paths
