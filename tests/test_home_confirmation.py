from __future__ import annotations

import subprocess
import sys
from threading import Event
from pathlib import Path
from types import SimpleNamespace

from ritualist.home import confirmation as confirmation_module
from ritualist.home.confirmation import (
    _proceed_label,
    _show_win32_confirmation,
    create_win32_confirmation_presenter,
    placement_for_dialog,
)
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
    assert "ApplicationModal" in source
    assert "WindowStaysOnTopHint" in source
    assert "WindowType.Window" in source
    assert "_place_dialog(dialog, request" in source
    assert "_force_dialog_foreground(dialog)" in source
    assert "QTimer.singleShot(150" in source
    assert "QTimer.singleShot(700" in source
    assert "Skip if supported" in source
    assert "Cancel Ritual" in source
    assert "create_win32_confirmation_presenter" in source
    assert "_show_win32_confirmation(request)" in source
    assert "SetForegroundWindow" in source
    assert "SetWindowPos" in source
    assert "0x00040000" in source
    assert "0x00010000" in source
    assert "0x00000100" in source


def test_win32_fallback_messagebox_is_topmost_and_foreground(monkeypatch):
    import ctypes

    calls: list[tuple[object, str, str, int]] = []

    class User32:
        def MessageBoxW(self, hwnd: object, text: str, title: str, flags: int) -> int:
            calls.append((hwnd, text, title, flags))
            return 1

    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(user32=User32()), raising=False)

    accepted = _show_win32_confirmation(
        ConfirmationRequest(
            prompt="Click Play?",
            recipe_name="Gaming Mode",
            step_name="Ask before clicking Play",
            action="desktop.click_text",
            window_title="Battle.net",
            target_text="Play",
            safety_message="Clicking visible text exactly equal to Play requires explicit confirmation.",
        )
    )

    assert accepted is True
    assert calls
    _, text, title, flags = calls[0]
    assert "Gaming Mode" in text
    assert "Ask before clicking Play" in text
    assert "Window: Battle.net" in text
    assert "Target: Play" in text
    assert title == "Ritualist Confirmation Required"
    assert flags & 0x00040000
    assert flags & 0x00010000
    assert flags & 0x00000100


def test_win32_confirmation_presenter_does_not_block_caller_thread(monkeypatch):
    started = Event()
    release = Event()
    decisions: list[bool] = []

    def fake_show(request: object) -> bool:
        started.set()
        assert release.wait(timeout=2)
        return True

    monkeypatch.setattr(confirmation_module, "_show_win32_confirmation", fake_show)

    presenter = create_win32_confirmation_presenter()
    presenter.request_confirmation("Click Play?", on_decision=decisions.append)

    assert started.wait(timeout=2)
    assert decisions == []
    release.set()
    assert _wait_for(lambda: decisions == [True])


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


def _wait_for(predicate, *, timeout: float = 2.0) -> bool:
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()
