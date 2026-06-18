from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from ritualist.agent.menu_model import (
    ActiveRitualMenuContext,
    MenuAction,
    TrayMenuContext,
    build_active_ritual_menu,
    build_tray_menu,
)
from ritualist.agent.tray_model import TrayAttention, TrayContext, TrayState, build_tray_model


def test_tray_state_values_are_stable() -> None:
    assert [state.value for state in TrayState] == [
        "ready",
        "running",
        "waiting",
        "confirmation",
        "failure",
        "recovery",
    ]


def test_ready_tooltip_is_plain_language() -> None:
    model = build_tray_model(TrayContext(state=TrayState.READY))

    assert model.tooltip == "Ritualist is ready"
    assert model.attention == TrayAttention.NONE


def test_running_tooltip_includes_ritual_and_step() -> None:
    model = build_tray_model(
        TrayContext(
            state=TrayState.RUNNING,
            ritual_name="Morning setup",
            current_step="Open planner",
        )
    )

    assert model.tooltip == "Morning setup is running: Open planner"
    assert model.attention == TrayAttention.BUSY


def test_waiting_tooltip_includes_current_step() -> None:
    model = build_tray_model(
        TrayContext(
            state=TrayState.WAITING,
            ritual_name="Build check",
            current_step="Waiting for tests",
        )
    )

    assert model.tooltip == "Build check is waiting: Waiting for tests"


def test_confirmation_tooltip_uses_required_decision() -> None:
    model = build_tray_model(
        TrayContext(
            state=TrayState.CONFIRMATION,
            ritual_name="Deploy prep",
            required_decision="Review browser target",
        )
    )

    assert model.tooltip == "Deploy prep needs review: Review browser target"
    assert model.attention == TrayAttention.NEEDS_REVIEW


def test_failure_and_recovery_tooltips_are_actionable_without_automation_language() -> None:
    failed = build_tray_model(
        TrayContext(
            state=TrayState.FAILURE,
            ritual_name="Daily report",
            failure_reason="Could not find the app window",
        )
    )
    recovery = build_tray_model(
        TrayContext(
            state=TrayState.RECOVERY,
            ritual_name="Daily report",
            recovery_reason="The run was interrupted",
        )
    )

    assert failed.tooltip == "Daily report failed: Could not find the app window"
    assert failed.attention == TrayAttention.ERROR
    assert recovery.tooltip == "Daily report needs recovery: The run was interrupted"
    assert recovery.attention == TrayAttention.RECOVERY


def test_tray_menu_order_is_stable_without_active_ritual() -> None:
    menu = build_tray_menu()

    assert [item.label for item in menu] == [
        "Open Ritualist",
        "Rooms...",
        "Recent rituals...",
        "Run log",
        "Settings",
        "Exit Ritualist",
    ]
    assert [item.action for item in menu] == [
        MenuAction.OPEN_RITUALIST,
        MenuAction.OPEN_ROOMS,
        MenuAction.OPEN_RECENT_RITUALS,
        MenuAction.OPEN_RUN_LOG,
        MenuAction.OPEN_SETTINGS,
        MenuAction.EXIT_RITUALIST,
    ]


def test_tray_menu_includes_active_ritual_submenu_conditionally() -> None:
    menu = build_tray_menu(
        TrayMenuContext(
            active_ritual=ActiveRitualMenuContext(
                ritual_name="Morning setup",
                can_pause=True,
                has_current_target=True,
            )
        )
    )

    assert [item.label for item in menu] == [
        "Open Ritualist",
        "Active ritual...",
        "Rooms...",
        "Recent rituals...",
        "Run log",
        "Settings",
        "Exit Ritualist",
    ]
    active = menu[1]
    assert active.action is None
    assert [item.label for item in active.children] == [
        "Show ritual",
        "Pause ritual",
        "Stop ritual...",
        "Open current target",
        "View run details",
    ]


def test_active_submenu_switches_pause_to_resume_when_supported() -> None:
    menu = build_active_ritual_menu(
        ActiveRitualMenuContext(
            ritual_name="Morning setup",
            can_pause=True,
            can_resume=True,
            has_current_target=False,
        )
    )

    assert [item.label for item in menu] == [
        "Show ritual",
        "Resume ritual",
        "Stop ritual...",
        "View run details",
    ]
    assert [item.action for item in menu] == [
        MenuAction.SHOW_ACTIVE_RITUAL,
        MenuAction.RESUME_ACTIVE_RITUAL,
        MenuAction.STOP_ACTIVE_RITUAL,
        MenuAction.VIEW_RUN_DETAILS,
    ]


def test_agent_models_import_without_gui_or_windows_dependencies() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    code = """
import sys
import ritualist.agent.menu_model
import ritualist.agent.notification_policy
import ritualist.agent.tray_model

blocked = ["PySide6", "pywinauto", "win32api", "win32gui", "win32con"]
loaded = [name for name in blocked if name in sys.modules]
if loaded:
    raise SystemExit(f"agent models loaded GUI/Windows modules: {loaded}")
"""

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
