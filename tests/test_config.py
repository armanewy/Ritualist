from __future__ import annotations

from ritualist.config import load_app_config


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
