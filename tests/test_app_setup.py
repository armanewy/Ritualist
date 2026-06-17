from __future__ import annotations

import yaml

from ritualist.app_setup import initialize_app
from ritualist.recipe_loader import discover_recipes


def test_initialize_app_creates_dirs_and_copies_sample(tmp_path, monkeypatch):
    app_data = tmp_path / "app-data"
    config_path = app_data / "config" / "config.yaml"
    recipe_dir = app_data / "recipes"
    created_dirs = {
        "app_data": app_data,
        "config": app_data / "config",
        "recipes": recipe_dir,
        "imported_packs": app_data / "imported-packs",
        "logs": app_data / "logs",
        "runs": app_data / "runs",
        "browser_profiles": app_data / "browser-profiles",
    }
    monkeypatch.setattr("ritualist.app_setup.app_data_path", lambda: created_dirs["app_data"])
    monkeypatch.setattr("ritualist.app_setup.config_path", lambda: created_dirs["config"])
    monkeypatch.setattr("ritualist.app_setup.recipes_path", lambda: recipe_dir)
    monkeypatch.setattr(
        "ritualist.app_setup.imported_packs_path",
        lambda: created_dirs["imported_packs"],
    )
    monkeypatch.setattr("ritualist.app_setup.logs_path", lambda: created_dirs["logs"])
    monkeypatch.setattr("ritualist.app_setup.runs_path", lambda: created_dirs["runs"])
    monkeypatch.setattr(
        "ritualist.app_setup.browser_profiles_path",
        lambda: created_dirs["browser_profiles"],
    )
    monkeypatch.setattr("ritualist.app_setup.config_file_path", lambda: config_path)
    monkeypatch.setattr("ritualist.recipe_loader.recipes_dir", lambda: recipe_dir)

    report = initialize_app()
    rows = discover_recipes()

    assert report.paths == created_dirs
    assert report.created_dirs == created_dirs
    assert report.config_created is True
    assert report.sample_copied is True
    assert report.changed is True
    assert config_path.exists()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert config["default_recipe"] == "gaming_mode"
    assert config["ui"] == {
        "show_action_overlay": True,
        "overlay_duration_ms": 700,
        "preview_desktop_clicks": True,
    }
    assert config["home"] == {
        "categories": [
            "Gaming",
            "Media",
            "Coding",
            "News",
            "Helpdesk",
            "Settings",
        ],
        "min_status_dwell_ms": 1200,
    }
    assert config["canvas"] == {
        "performance_mode": "balanced",
        "show_performance_overlay": False,
    }
    assert (recipe_dir / "gaming_mode.yaml").exists()
    assert rows[0][1].id == "gaming_mode"
    assert rows[0][1].steps[0].keep_open is True
    assert rows[0][1].steps[0].clean_start is True
    assert rows[0][1].steps[0].dismiss_restore_prompt is True
    assert rows[0][1].steps[0].use_dedicated_profile is True


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
        "imported_packs": tmp_path / "imported-packs",
        "logs": tmp_path / "logs",
        "runs": tmp_path / "runs",
        "browser_profiles": tmp_path / "browser-profiles",
    }

    monkeypatch.setattr("ritualist.app_setup.app_data_path", lambda: created_dirs["app_data"])
    monkeypatch.setattr("ritualist.app_setup.config_path", lambda: created_dirs["config"])
    monkeypatch.setattr("ritualist.app_setup.recipes_path", lambda: recipe_dir)
    monkeypatch.setattr(
        "ritualist.app_setup.imported_packs_path",
        lambda: created_dirs["imported_packs"],
    )
    monkeypatch.setattr("ritualist.app_setup.logs_path", lambda: created_dirs["logs"])
    monkeypatch.setattr("ritualist.app_setup.runs_path", lambda: created_dirs["runs"])
    monkeypatch.setattr(
        "ritualist.app_setup.browser_profiles_path",
        lambda: created_dirs["browser_profiles"],
    )
    monkeypatch.setattr("ritualist.app_setup.config_file_path", lambda: config_path)
    monkeypatch.setattr("ritualist.recipe_loader.recipes_dir", lambda: recipe_dir)

    report = initialize_app()
    rows = discover_recipes()
    data = yaml.safe_load((recipe_dir / "gaming_mode.yaml").read_text(encoding="utf-8"))

    assert report.migration.changed is True
    assert report.migration.changes == [
        "added keep_open: true to first browser.open step",
        "added clean_start: true to first browser.open step",
        "added dismiss_restore_prompt: true to first browser.open step",
        "added use_dedicated_profile: true to first browser.open step",
    ]
    assert rows[0][1].steps[0].keep_open is True
    assert rows[0][1].steps[0].clean_start is True
    assert rows[0][1].steps[0].dismiss_restore_prompt is True
    assert rows[0][1].steps[0].use_dedicated_profile is True
    assert data["steps"][0]["keep_open"] is True
    assert data["steps"][0]["clean_start"] is True
    assert data["steps"][0]["dismiss_restore_prompt"] is True
    assert data["steps"][0]["use_dedicated_profile"] is True
    assert data["steps"][1]["action"] == "app.launch"


def test_initialize_app_reports_noop_when_up_to_date(tmp_path, monkeypatch):
    config_path = tmp_path / "config" / "config.yaml"
    recipe_dir = tmp_path / "recipes"
    created_dirs = {
        "app_data": tmp_path,
        "config": tmp_path / "config",
        "recipes": recipe_dir,
        "imported_packs": tmp_path / "imported-packs",
        "logs": tmp_path / "logs",
        "runs": tmp_path / "runs",
        "browser_profiles": tmp_path / "browser-profiles",
    }
    for path in created_dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    config_path.write_text("version: '0.1'\n", encoding="utf-8")
    (recipe_dir / "gaming_mode.yaml").write_text(
        """
version: "0.1"
id: gaming_mode
name: Gaming Mode
steps:
  - action: browser.open
    url: https://example.test
    keep_open: true
    clean_start: true
    dismiss_restore_prompt: true
    use_dedicated_profile: true
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.setattr("ritualist.app_setup.app_data_path", lambda: created_dirs["app_data"])
    monkeypatch.setattr("ritualist.app_setup.config_path", lambda: created_dirs["config"])
    monkeypatch.setattr("ritualist.app_setup.recipes_path", lambda: recipe_dir)
    monkeypatch.setattr(
        "ritualist.app_setup.imported_packs_path",
        lambda: created_dirs["imported_packs"],
    )
    monkeypatch.setattr("ritualist.app_setup.logs_path", lambda: created_dirs["logs"])
    monkeypatch.setattr("ritualist.app_setup.runs_path", lambda: created_dirs["runs"])
    monkeypatch.setattr(
        "ritualist.app_setup.browser_profiles_path",
        lambda: created_dirs["browser_profiles"],
    )
    monkeypatch.setattr("ritualist.app_setup.config_file_path", lambda: config_path)

    report = initialize_app()

    assert report.changed is False
    assert report.created_dirs == {}
    assert report.config_created is False
    assert report.sample_copied is False
    assert report.migration.changed is False
