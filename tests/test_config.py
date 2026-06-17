from __future__ import annotations

from ritualist.config import DEFAULT_HOME_CATEGORIES, load_app_config
from ritualist.canvas import CanvasPerformanceMode


def test_load_app_config_reads_visual_trust_options(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
version: "0.1"
ui:
  show_action_overlay: false
  overlay_duration_ms: 1200
  preview_desktop_clicks: false
""".lstrip(),
        encoding="utf-8",
    )

    config = load_app_config(path)

    assert config.ui.show_action_overlay is False
    assert config.ui.overlay_duration_ms == 1200
    assert config.ui.preview_desktop_clicks is False


def test_load_app_config_defaults_visual_trust_options_when_missing(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("version: '0.1'\n", encoding="utf-8")

    config = load_app_config(path)

    assert config.ui.show_action_overlay is True
    assert config.ui.overlay_duration_ms == 700
    assert config.ui.preview_desktop_clicks is True


def test_load_app_config_defaults_home_categories_when_missing(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("version: '0.1'\n", encoding="utf-8")

    config = load_app_config(path)

    assert config.home.categories == DEFAULT_HOME_CATEGORIES
    assert config.home.min_status_dwell_ms == 1200


def test_load_app_config_reads_custom_home_categories(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
version: "0.1"
home:
  min_status_dwell_ms: 1800
  categories:
    - Launchers
    - Media
    - Local Admin
""".lstrip(),
        encoding="utf-8",
    )

    config = load_app_config(path)

    assert config.home.categories == ("Launchers", "Media", "Local Admin")
    assert config.home.min_status_dwell_ms == 1800


def test_load_app_config_uses_default_home_categories_when_custom_list_is_empty(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
version: "0.1"
home:
  categories:
    - ""
    - " "
""".lstrip(),
        encoding="utf-8",
    )

    config = load_app_config(path)

    assert config.home.categories == DEFAULT_HOME_CATEGORIES


def test_load_app_config_reads_canvas_performance_options(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
version: "0.1"
canvas:
  performance_mode: low
  show_performance_overlay: true
""".lstrip(),
        encoding="utf-8",
    )

    config = load_app_config(path)
    settings = config.canvas.performance_settings()

    assert config.canvas.performance_mode == "low"
    assert settings.mode is CanvasPerformanceMode.LOW
    assert settings.animations is False
    assert settings.shadows == "none"
    assert settings.live_update_rate_hz == 15
    assert settings.show_performance_overlay is True


def test_load_app_config_defaults_unknown_canvas_performance_mode(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
version: "0.1"
canvas:
  performance_mode: turbo
""".lstrip(),
        encoding="utf-8",
    )

    settings = load_app_config(path).canvas.performance_settings()

    assert settings.mode is CanvasPerformanceMode.BALANCED
