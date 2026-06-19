from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from setpiece.actions.registry import create_default_registry
from setpiece.app_setup import _planned_paths
from setpiece.cli import app
from setpiece.config import load_app_config


REPO_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_SURFACE_TERMS = (
    "Watch Me",
    "watch_me",
    "watch-me",
    "Create from what I do",
    "Stop Watch Me",
    "recording mode",
    "observation session",
    "live observation",
    "teach by watching",
    "macro recording",
    "record/replay",
)


def test_cli_help_does_not_expose_watch_me_command() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    output = result.output.casefold()
    assert "watch-me" not in output
    assert "watch me" not in output


def test_gui_canvas_and_home_visible_text_do_not_expose_watch_me() -> None:
    surface_files = (
        REPO_ROOT / "setpiece" / "canvas" / "qml" / "CanvasUse.qml",
        REPO_ROOT / "setpiece" / "home" / "qml" / "Home.qml",
        REPO_ROOT / "setpiece" / "ui" / "main_window.py",
    )

    for path in surface_files:
        text = path.read_text(encoding="utf-8")
        for term in FORBIDDEN_SURFACE_TERMS:
            assert term not in text, f"{term!r} remains visible in {path}"


def test_action_metadata_does_not_expose_recording_or_replay() -> None:
    registry = create_default_registry()
    forbidden_terms = ("watch_me", "watch-me", "recording", "recorder", "replay", "macro")

    for action_type in registry.action_types():
        metadata = registry.metadata(action_type).to_dict()
        serialized = json.dumps(metadata, sort_keys=True).casefold()
        for term in forbidden_terms:
            assert term not in serialized, f"{term!r} remains in metadata for {action_type}"


def test_app_setup_has_no_watch_me_path_and_old_config_fields_are_ignored(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "watch_me": {"enabled": True, "path": "legacy"},
                "ui": {"show_action_overlay": False},
            }
        ),
        encoding="utf-8",
    )

    config = load_app_config(config_path)

    assert "watch_me" not in _planned_paths()
    assert not hasattr(config, "watch_me")
    assert config.ui.show_action_overlay is False
