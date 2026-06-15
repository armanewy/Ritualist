from __future__ import annotations

import yaml

from ritualist.app_setup import initialize_app
from ritualist.recipe_loader import discover_recipes


def test_initialize_app_creates_dirs_and_copies_sample(tmp_path, monkeypatch):
    config_path = tmp_path / "config" / "config.yaml"
    recipe_dir = tmp_path / "recipes"
    created_dirs = {
        "app_data": tmp_path,
        "config": tmp_path / "config",
        "recipes": recipe_dir,
        "logs": tmp_path / "logs",
        "runs": tmp_path / "runs",
        "browser_profiles": tmp_path / "browser-profiles",
    }

    def ensure_dirs():
        for path in created_dirs.values():
            path.mkdir(parents=True, exist_ok=True)
        return created_dirs

    monkeypatch.setattr("ritualist.app_setup.ensure_app_dirs", ensure_dirs)
    monkeypatch.setattr("ritualist.app_setup.config_file", lambda: config_path)
    monkeypatch.setattr("ritualist.app_setup.recipes_dir", lambda: recipe_dir)
    monkeypatch.setattr("ritualist.recipe_loader.recipes_dir", lambda: recipe_dir)

    paths = initialize_app()
    rows = discover_recipes()

    assert paths == created_dirs
    assert config_path.exists()
    assert yaml.safe_load(config_path.read_text(encoding="utf-8"))["default_recipe"] == "gaming_mode"
    assert (recipe_dir / "gaming_mode.yaml").exists()
    assert rows[0][1].id == "gaming_mode"
