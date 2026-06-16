from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import yaml

from ritualist.home.pack_review import build_pack_import_review
from ritualist.packs import PACK_SCHEMA_V1, validate_pack


SAFETY = {
    "no_arbitrary_code": True,
    "no_coordinate_clicks": True,
    "no_remote_execution": True,
    "imported_recipes_must_not_run_automatically": True,
}


def test_pack_import_review_derives_policy_and_safety_from_fake_summary() -> None:
    review = build_pack_import_review(
        {
            "pack": {
                "name": "Streamer Setup",
                "version": "1.2.0",
                "author": "Local Lab",
            },
            "actions_requested": ["wait.for_user", "browser.open", "desktop.click_text"],
            "required_variables": {
                "stream_url": "Channel URL",
                "launcher_path": "Local launcher path",
            },
            "readme": "# Streamer Setup\nReview before enabling.",
        }
    )

    assert review.pack_name == "Streamer Setup"
    assert review.pack_version == "1.2.0"
    assert review.author == "Local Lab"
    assert review.action_names == ("wait.for_user", "browser.open", "desktop.click_text")
    assert set(review.side_effect_levels) == {"read_only", "launches_app", "risky"}
    assert review.required_variables == ("stream_url", "launcher_path")
    assert "playwright" in review.required_capabilities
    assert "browser_control" in review.required_capabilities
    assert "windows_uia" in review.required_capabilities
    assert "Always asks for confirmation" in review.safety_warnings
    assert "Clicking text exactly equal to Play requires confirmation" in review.safety_warnings
    assert "Requires window_title_contains" in review.safety_warnings
    assert "Action 'browser.open' is blocked in imported recipe packs." in review.policy_failures
    assert (
        "Action 'desktop.click_text' is blocked in imported recipe packs."
        in review.policy_failures
    )
    assert review.enable_allowed is False
    assert "# Streamer Setup" in review.readme


def test_pack_import_review_allows_safe_valid_summary() -> None:
    review = build_pack_import_review(
        {
            "pack_name": "Wait Pack",
            "pack_version": "0.1.0",
            "author": "Ritualist",
            "actions": [
                {"action": "wait.seconds"},
                {"action": "assert.file_exists"},
            ],
            "required_variables": ["marker_path"],
        }
    )

    assert review.enable_allowed is True
    assert review.enable_blockers == ()
    assert review.required_capabilities == ("file_read",)
    assert review.required_variables == ("marker_path",)
    assert [action.blocked_by_policy for action in review.actions] == [False, False]


def test_pack_import_review_blocks_policy_from_validated_pack(tmp_path: Path) -> None:
    path = tmp_path / "launch.ritualistpack"
    manifest = {
        "schema": PACK_SCHEMA_V1,
        "id": "launch_pack",
        "name": "Launch Pack",
        "version": "1.0.0",
        "required_ritualist_version": ">=0.1.0-alpha.1",
        "supported_os": ["windows", "macos", "linux"],
        "required_capabilities": ["app_launch"],
        "required_actions": ["app.launch"],
        "variables": {},
        "safety": dict(SAFETY),
    }
    recipe = {
        "version": "0.1",
        "id": "launch_recipe",
        "name": "Launch Recipe",
        "steps": [{"action": "app.launch", "command": "demo.exe"}],
    }
    with ZipFile(path, "w") as archive:
        archive.writestr("manifest.yaml", yaml.safe_dump(manifest, sort_keys=False))
        archive.writestr("recipe.yaml", yaml.safe_dump(recipe, sort_keys=False))

    pack = validate_pack(path)
    review = build_pack_import_review(pack)

    assert review.pack_name == "Launch Pack"
    assert review.action_names == ("app.launch",)
    assert "app_launch" in review.required_capabilities
    assert "Action 'app.launch' is blocked in imported recipe packs." in review.policy_failures
    assert review.enable_allowed is False


def test_pack_import_review_blocks_validation_failures_and_unknown_actions() -> None:
    review = build_pack_import_review(
        {
            "pack_name": "Broken Pack",
            "actions": ["wait.seconds", "custom.unknown"],
            "validation_errors": ["manifest version is unsupported"],
        }
    )

    assert review.enable_allowed is False
    assert "manifest version is unsupported" in review.validation_errors
    assert "Action 'custom.unknown' is not registered." in review.validation_errors
    assert review.policy_failures == ()


def test_pack_import_review_payload_is_json_serializable() -> None:
    review = build_pack_import_review({"pack_name": "Safe", "actions": ["wait.seconds"]})

    payload = review.to_qml()

    assert payload["enable_allowed"] is True
    assert payload["actions"][0]["action_name"] == "wait.seconds"
    json.dumps(payload)


def test_pack_review_model_imports_without_gui_or_windows_dependencies() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    code = """
import sys
import ritualist.home.pack_review

blocked = [
    name for name in sys.modules
    if name == "PySide6"
    or name.startswith("PySide6.")
    or name == "pywinauto"
    or name.startswith("win32")
]
if blocked:
    raise SystemExit(f"pack review import loaded GUI/Windows modules: {blocked}")
"""

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
