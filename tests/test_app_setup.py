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
    assert rows[0][1].steps[0].keep_open is True


def test_initialize_app_migrates_existing_gaming_mode_keep_open(tmp_path, monkeypatch):
    config_path = tmp_path / "config" / "config.yaml"
    recipe_dir = tmp_path / "recipes"
    recipe_dir.mkdir(parents=True)
    (recipe_dir / "gaming_mode.yaml").write_text(
        """
version: "0.1"
id: gaming_mode
name: Gaming Mode
steps:
  - action: browser.open
    url: https://example.test
    profile: gaming_mode
  - action: app.launch
    command: demo.exe
""".lstrip(),
        encoding="utf-8",
    )
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

    initialize_app()
    rows = discover_recipes()
    data = yaml.safe_load((recipe_dir / "gaming_mode.yaml").read_text(encoding="utf-8"))

    assert rows[0][1].steps[0].keep_open is True
    assert data["steps"][0]["keep_open"] is True
    assert data["steps"][1]["action"] == "app.launch"
