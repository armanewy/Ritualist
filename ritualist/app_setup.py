from __future__ import annotations

import shutil
from importlib.resources import files
from pathlib import Path

import yaml

from .paths import config_file, ensure_app_dirs, recipes_dir


def initialize_app(*, overwrite_sample: bool = False) -> dict[str, Path]:
    paths = ensure_app_dirs()
    _ensure_config_file()
    _copy_sample_recipe(overwrite=overwrite_sample)
    return paths


def _ensure_config_file() -> None:
    path = config_file()
    if path.exists():
        return
    config = {
        "version": "0.1",
        "default_recipe": "gaming_mode",
    }
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")


def _copy_sample_recipe(*, overwrite: bool) -> None:
    destination = recipes_dir() / "gaming_mode.yaml"
    if not destination.exists() or overwrite:
        source = files("ritualist.sample_recipes").joinpath("gaming_mode.yaml")
        with source.open("rb") as src, destination.open("wb") as dst:
            shutil.copyfileobj(src, dst)
    _migrate_gaming_mode_sample(destination)


def _migrate_gaming_mode_sample(path: Path) -> None:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return
    if not isinstance(raw, dict) or raw.get("id") != "gaming_mode":
        return

    steps = raw.get("steps")
    if not isinstance(steps, list):
        return

    changed = False
    for step in steps:
        if not isinstance(step, dict) or step.get("action") != "browser.open":
            continue
        if "keep_open" not in step:
            step["keep_open"] = True
            changed = True
        break

    if changed:
        path.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True), encoding="utf-8")
