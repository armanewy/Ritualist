from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from ritualist.home.confirmation import _proceed_label, placement_for_dialog
from ritualist.overlay import ConfirmationRequest, ScreenRect


def test_confirmation_dialog_places_near_target_when_room_exists():
    placement = placement_for_dialog(
        dialog_width=300,
        dialog_height=160,
        target_rect=ScreenRect(100, 120, 80, 30),
        screen_left=0,
        screen_top=0,
        screen_width=1000,
        screen_height=800,
    )

    assert placement.x == 196
    assert placement.y == 120


def test_confirmation_dialog_clamps_to_visible_screen_bounds():
    placement = placement_for_dialog(
        dialog_width=420,
        dialog_height=200,
        target_rect=ScreenRect(930, 760, 80, 40),
        screen_left=0,
        screen_top=0,
        screen_width=1000,
        screen_height=800,
    )

    assert 0 <= placement.x <= 580
    assert 0 <= placement.y <= 600


def test_confirmation_dialog_centers_without_target_bounds():
    placement = placement_for_dialog(
        dialog_width=400,
        dialog_height=200,
        target_rect=None,
        screen_left=0,
        screen_top=0,
        screen_width=1200,
        screen_height=800,
    )

    assert placement.x == 400
    assert placement.y == 300


def test_home_confirmation_module_imports_without_pyside6():
    repo_root = Path(__file__).resolve().parents[1]
    code = """
import sys
import ritualist.home.confirmation

loaded = [name for name in sys.modules if name == "PySide6" or name.startswith("PySide6.")]
if loaded:
    raise SystemExit(f"confirmation import loaded PySide6 modules: {loaded}")
"""

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_native_home_confirmation_presenter_uses_top_level_always_on_top_dialog():
    source = (
        Path(__file__).resolve().parents[1] / "ritualist" / "home" / "confirmation.py"
    ).read_text(encoding="utf-8")

    assert "dialog = QDialog()" in source
    assert "dialog.setModal(False)" in source
    assert "WindowStaysOnTopHint" in source
    assert "WindowType.Window" in source
    assert "_place_dialog(dialog, request" in source
    assert "Skip if supported" in source
    assert "Cancel Ritual" in source


def test_home_confirmation_proceed_label_uses_browser_target_metadata():
    request = ConfirmationRequest(
        prompt="Run step?",
        action="browser.click_test_id",
        step_name="Click test id",
        target_scope="browser",
        target_type="test_id",
        target_test_id="confirm-order",
    )

    assert _proceed_label(request) == "Click target"
