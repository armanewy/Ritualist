from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from ritualist.home.confirmation import placement_for_dialog
from ritualist.overlay import ScreenRect


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
