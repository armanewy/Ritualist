from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

from ritualist.cli import app
from ritualist.errors import DependencyMissingError
from ritualist.home import app as home_app
from ritualist.home import (
    FakeHomeStatusEmitter,
    HomeCardStatus,
    HomeEventBridge,
    HomeRuntimeEvent,
    create_mock_home_model,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_home_help_works():
    result = CliRunner().invoke(app, ["home", "--help"])

    assert result.exit_code == 0
    assert "Open the experimental Qt Quick Home surface" in result.output
    assert "--mock" in result.output


def test_home_mock_command_calls_launcher(monkeypatch):
    calls = []
    monkeypatch.setattr(home_app, "run_home", lambda *, mock: calls.append(mock))

    result = CliRunner().invoke(app, ["home", "--mock"])

    assert result.exit_code == 0
    assert calls == [True]


def test_home_dependency_error_preserves_gui_extra(monkeypatch):
    def missing_home(*, mock: bool) -> None:
        raise DependencyMissingError("Home requires PySide6; install ritualist[gui]")

    monkeypatch.setattr(home_app, "run_home", missing_home)

    result = CliRunner().invoke(app, ["home", "--mock"])

    assert result.exit_code == 1
    assert "ritualist[gui]" in result.output


def test_home_command_import_does_not_load_pyside6():
    repo_root = Path(__file__).resolve().parents[1]
    code = """
import sys
from ritualist.cli import app

loaded = [name for name in sys.modules if name == "PySide6" or name.startswith("PySide6.")]
if loaded:
    raise SystemExit(f"CLI import loaded PySide6 modules: {loaded}")
"""

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_fake_events_are_coalesced_to_latest_status():
    clock = FakeClock()
    model = create_mock_home_model()
    bridge = HomeEventBridge(model, target_hz=10, clock=clock)

    first = HomeRuntimeEvent(
        card_id="gaming-001",
        status=HomeCardStatus.RUNNING,
        subtitle="first status",
    )
    latest = HomeRuntimeEvent(
        card_id="gaming-001",
        status=HomeCardStatus.WARNING,
        subtitle="latest status",
    )

    bridge.queue_runtime_event(first)
    bridge.queue_runtime_event(latest)

    assert bridge.apply_due() == []
    clock.advance(bridge.interval_seconds)

    applied = bridge.apply_due()
    card = model.get_card("gaming-001")

    assert applied == [latest]
    assert card.status is HomeCardStatus.WARNING
    assert card.subtitle == "latest status"
    assert bridge.applied_count == 1


def test_fake_emitter_updates_model_through_bridge():
    clock = FakeClock()
    model = create_mock_home_model()
    bridge = HomeEventBridge(model, target_hz=30, clock=clock)
    emitter = FakeHomeStatusEmitter(
        bridge.queue_runtime_event,
        card_ids=["gaming-001"],
        interval_seconds=0.01,
    )

    first = emitter.emit_tick()
    second = emitter.emit_tick()
    clock.advance(bridge.interval_seconds)
    applied = bridge.apply_due()
    card = model.get_card("gaming-001")

    assert first.status is HomeCardStatus.RUNNING
    assert second.status is HomeCardStatus.WARNING
    assert applied == [second]
    assert card.status is HomeCardStatus.WARNING
    assert card.description == "Mock Home event 2"


def test_home_import_does_not_load_runtime_automation():
    repo_root = Path(__file__).resolve().parents[1]
    code = """
import sys
import ritualist.home.app
import ritualist.home.fake_events
import ritualist.home.models

blocked = [
    name for name in sys.modules
    if name == "PySide6"
    or name.startswith("PySide6.")
    or name == "ritualist.executor"
    or name == "ritualist.adapters.windows_uia"
    or name == "ritualist.adapters.browser_playwright"
]
if blocked:
    raise SystemExit(f"Home import loaded blocked modules: {blocked}")
"""

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
