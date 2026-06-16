from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path

import yaml

from .config import DEFAULT_HOME_CATEGORIES
from .paths import (
    app_data_path,
    browser_profiles_path,
    config_file_path,
    config_path,
    logs_path,
    recipes_path,
    runs_path,
)


@dataclass(frozen=True)
class MigrationResult:
    recipe_path: Path
    changed: bool
    changes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class InitReport:
    paths: dict[str, Path]
    created_dirs: dict[str, Path]
    config_created: bool
    sample_copied: bool
    migration: MigrationResult

    @property
    def changed(self) -> bool:
        return bool(
            self.created_dirs
            or self.config_created
            or self.sample_copied
            or self.migration.changed
        )


def initialize_app(*, overwrite_sample: bool = False) -> InitReport:
    paths = _planned_paths()
    created_dirs = _ensure_dirs(paths)
    config_created = _ensure_config_file()
    sample_copied, migration = _copy_sample_recipe(overwrite=overwrite_sample)
    return InitReport(
        paths=paths,
        created_dirs=created_dirs,
        config_created=config_created,
        sample_copied=sample_copied,
        migration=migration,
    )


def _planned_paths() -> dict[str, Path]:
    return {
        "app_data": app_data_path(),
        "config": config_path(),
        "recipes": recipes_path(),
        "logs": logs_path(),
        "runs": runs_path(),
        "browser_profiles": browser_profiles_path(),
    }


def _ensure_dirs(paths: dict[str, Path]) -> dict[str, Path]:
    created: dict[str, Path] = {}
    for name, path in paths.items():
        existed = path.exists()
        path.mkdir(parents=True, exist_ok=True)
        if not existed:
            created[name] = path
    return created


def _ensure_config_file() -> bool:
    path = config_file_path()
    if path.exists():
        return False
    config = {
        "version": "0.1",
        "default_recipe": "gaming_mode",
        "ui": {
            "show_action_overlay": True,
            "overlay_duration_ms": 700,
            "preview_desktop_clicks": True,
        },
        "home": {
            "categories": list(DEFAULT_HOME_CATEGORIES),
        },
    }
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return True


def _copy_sample_recipe(*, overwrite: bool) -> tuple[bool, MigrationResult]:
    destination = recipes_path() / "gaming_mode.yaml"
    copied = False
    if not destination.exists() or overwrite:
        source = files("ritualist.sample_recipes").joinpath("gaming_mode.yaml")
        with source.open("rb") as src, destination.open("wb") as dst:
            shutil.copyfileobj(src, dst)
        copied = True
    return copied, migrate_gaming_mode_sample(destination)


def migrate_gaming_mode_sample(path: Path) -> MigrationResult:
    changes: list[str] = []
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return MigrationResult(recipe_path=path, changed=False)
    if not isinstance(raw, dict) or raw.get("id") != "gaming_mode":
        return MigrationResult(recipe_path=path, changed=False)

    steps = raw.get("steps")
    if not isinstance(steps, list):
        return MigrationResult(recipe_path=path, changed=False)

    changed = False
    for step in steps:
        if not isinstance(step, dict) or step.get("action") != "browser.open":
            continue
        if "keep_open" not in step:
            step["keep_open"] = True
            changed = True
            changes.append("added keep_open: true to first browser.open step")
        break

    if changed:
        path.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return MigrationResult(recipe_path=path, changed=changed, changes=changes)
