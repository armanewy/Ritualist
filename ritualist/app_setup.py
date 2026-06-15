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
    if destination.exists() and not overwrite:
        return
    source = files("ritualist.sample_recipes").joinpath("gaming_mode.yaml")
    with source.open("rb") as src, destination.open("wb") as dst:
        shutil.copyfileobj(src, dst)
