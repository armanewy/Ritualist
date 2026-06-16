from __future__ import annotations

import sys
import threading
import time
from types import ModuleType

import pytest

from ritualist.adapters.fake import FakeAdapters
from ritualist.actions.assert_actions import AssertFileExistsHandler, AssertPathExistsHandler
from ritualist.actions.base import ActionContext
from ritualist.actions.metadata import ALL_PLATFORMS, WINDOWS_ONLY
from ritualist.actions.registry import create_default_registry
from ritualist.config import AppConfig
from ritualist.executor import WorkflowExecutor
from ritualist.models import AssertFileExistsStep, AssertPathExistsStep, AssertRegistryValueStep, Recipe
from ritualist.overlay import NullOverlayController
from ritualist.runtime_control import RuntimeControl, RuntimeStoppedError


ASSERTION_METADATA = {
    "assert.file_exists": {
        "capabilities": ("file_read",),
        "platforms": ALL_PLATFORMS,
    },
    "assert.path_exists": {
        "capabilities": ("file_read",),
        "platforms": ALL_PLATFORMS,
    },
    "assert.process_running": {
        "capabilities": ("process_inspection",),
        "platforms": ALL_PLATFORMS,
    },
    "assert.window_exists": {
        "capabilities": ("windows_uia", "window_management"),
        "platforms": WINDOWS_ONLY,
    },
    "assert.window_text_visible": {
        "capabilities": ("windows_uia",),
        "platforms": WINDOWS_ONLY,
    },
    "assert.browser_text_visible": {
        "capabilities": ("playwright", "browser_control"),
        "platforms": ALL_PLATFORMS,
    },
    "assert.registry_value": {
        "capabilities": ("registry_read",),
        "platforms": WINDOWS_ONLY,
    },
}


def test_assertion_metadata_is_read_only_and_platform_gated():
    registry = create_default_registry()

    for action, expected in ASSERTION_METADATA.items():
        metadata = registry.metadata(action)

        assert metadata.side_effect_level == "read_only"
        assert metadata.confirmation_policy == "never"
        assert metadata.allowed_in_imported_packs is True
        assert metadata.required_capabilities == expected["capabilities"]
        assert metadata.supported_platforms == expected["platforms"]


def test_preflight_assertions_run_before_steps(tmp_path):
    marker = tmp_path / "marker.txt"
    marker.write_text("ok", encoding="utf-8")
    recipe = Recipe.model_validate(
        {
            "id": "run",
            "name": "Run",
            "preflight": [{"action": "assert.file_exists", "path": str(marker)}],
            "steps": [{"action": "app.launch", "command": "demo.exe"}],
        }
    )
    fakes = FakeAdapters()

    summary = WorkflowExecutor(adapters=fakes.bundle()).run(recipe)

    assert summary.success
    assert [result.action for result in summary.results] == [
        "assert.file_exists",
        "app.launch",
    ]
    assert fakes.shell.calls[0][0] == "launch"


def test_preflight_assertion_failure_stops_before_steps(tmp_path):
    recipe = Recipe.model_validate(
        {
            "id": "run",
            "name": "Run",
            "preflight": [{"action": "assert.path_exists", "path": str(tmp_path / "missing")}],
            "steps": [{"action": "app.launch", "command": "demo.exe"}],
        }
    )
    fakes = FakeAdapters()

    summary = WorkflowExecutor(adapters=fakes.bundle()).run(recipe)

    assert not summary.success
    assert summary.results[0].action == "assert.path_exists"
    assert summary.results[0].status == "failed"
    assert "path does not exist" in summary.results[0].message
    assert fakes.shell.calls == []


def test_file_exists_assertion_rejects_directories_without_mutating(tmp_path):
    recipe = Recipe.model_validate(
        {
            "id": "run",
            "name": "Run",
            "preflight": [{"action": "assert.file_exists", "path": str(tmp_path)}],
            "steps": [{"action": "app.launch", "command": "demo.exe"}],
        }
    )
    fakes = FakeAdapters()

    summary = WorkflowExecutor(adapters=fakes.bundle()).run(recipe)

    assert not summary.success
    assert summary.results[0].action == "assert.file_exists"
    assert "path is not a file" in summary.results[0].message
    assert fakes.shell.calls == []


def test_verify_assertions_run_after_steps():
    recipe = Recipe.model_validate(
        {
            "id": "run",
            "name": "Run",
            "steps": [{"action": "app.launch", "command": "demo.exe"}],
            "verify": [
                {
                    "action": "assert.window_text_visible",
                    "window_title_contains": "Vendor App",
                    "text": "Connected",
                }
            ],
        }
    )
    fakes = FakeAdapters()

    summary = WorkflowExecutor(adapters=fakes.bundle()).run(recipe)

    assert summary.success
    assert [result.action for result in summary.results] == [
        "app.launch",
        "assert.window_text_visible",
    ]
    assert fakes.desktop.calls[0][0] == "text_visible"
    assert fakes.desktop.calls[0][2]["text"] == "Connected"


def test_process_window_and_browser_assertions_are_read_only():
    recipe = Recipe.model_validate(
        {
            "id": "run",
            "name": "Run",
            "preflight": [{"action": "assert.process_running", "process_name": "demo.exe"}],
            "steps": [{"action": "browser.open", "url": "https://example.test"}],
            "verify": [
                {"action": "assert.window_exists", "title_contains": "Vendor App"},
                {"action": "assert.browser_text_visible", "text": "Ready"},
            ],
        }
    )
    fakes = FakeAdapters()

    summary = WorkflowExecutor(adapters=fakes.bundle()).run(recipe)

    assert summary.success
    assert [call[0] for call in fakes.shell.calls] == ["process_running"]
    assert [call[0] for call in fakes.window.calls] == ["window_exists"]
    assert [call[0] for call in fakes.browser.calls] == ["open_url", "text_visible", "close"]


def test_file_assertion_timeout_respects_runtime_stop(tmp_path):
    control = RuntimeControl()
    heartbeats = 0

    def heartbeat() -> None:
        nonlocal heartbeats
        heartbeats += 1
        control.stop()

    context = ActionContext(
        adapters=FakeAdapters().bundle(),
        dry_run=False,
        logger=__import__("logging").getLogger("test"),
        confirm=lambda _request: True,
        recipe=Recipe.model_validate(
            {
                "id": "run",
                "name": "Run",
                "steps": [{"action": "wait.seconds", "seconds": 0.1}],
            }
        ),
        config=AppConfig(),
        overlay=NullOverlayController(),
        runtime_control=control,
        heartbeat=heartbeat,
    )
    step = AssertFileExistsStep.model_validate(
        {"action": "assert.file_exists", "path": str(tmp_path / "missing"), "timeout_seconds": 5}
    )

    with pytest.raises(RuntimeStoppedError):
        AssertFileExistsHandler().run(step, context)

    assert heartbeats == 1


def test_path_assertion_timeout_emits_heartbeats(tmp_path):
    control = RuntimeControl()
    heartbeats = 0

    def heartbeat() -> None:
        nonlocal heartbeats
        heartbeats += 1

    context = ActionContext(
        adapters=FakeAdapters().bundle(),
        dry_run=False,
        logger=__import__("logging").getLogger("test"),
        confirm=lambda _request: True,
        recipe=Recipe.model_validate(
            {
                "id": "run",
                "name": "Run",
                "steps": [{"action": "wait.seconds", "seconds": 0.1}],
            }
        ),
        config=AppConfig(),
        overlay=NullOverlayController(),
        runtime_control=control,
        heartbeat=heartbeat,
    )
    step = AssertPathExistsStep.model_validate(
        {"action": "assert.path_exists", "path": str(tmp_path / "missing"), "timeout_seconds": 0.01}
    )

    with pytest.raises(Exception, match="path does not exist"):
        AssertPathExistsHandler().run(step, context)

    assert heartbeats >= 2


def test_path_assertion_timeout_respects_runtime_pause_resume(tmp_path):
    control = RuntimeControl()
    heartbeats = 0
    pause_started = threading.Event()

    def resume_soon() -> None:
        pause_started.wait(timeout=1)
        time.sleep(0.02)
        control.resume()

    resume_thread = threading.Thread(target=resume_soon, daemon=True)
    resume_thread.start()

    def heartbeat() -> None:
        nonlocal heartbeats
        heartbeats += 1
        if heartbeats == 1:
            control.pause()
            pause_started.set()

    context = ActionContext(
        adapters=FakeAdapters().bundle(),
        dry_run=False,
        logger=__import__("logging").getLogger("test"),
        confirm=lambda _request: True,
        recipe=Recipe.model_validate(
            {
                "id": "run",
                "name": "Run",
                "steps": [{"action": "wait.seconds", "seconds": 0.1}],
            }
        ),
        config=AppConfig(),
        overlay=NullOverlayController(),
        runtime_control=control,
        heartbeat=heartbeat,
    )
    step = AssertPathExistsStep.model_validate(
        {"action": "assert.path_exists", "path": str(tmp_path / "missing"), "timeout_seconds": 0.05}
    )

    with pytest.raises(Exception, match="path does not exist"):
        AssertPathExistsHandler().run(step, context)

    resume_thread.join(timeout=1)
    assert pause_started.is_set()
    assert control.is_paused() is False
    assert heartbeats >= 2


def test_false_adapter_assertion_result_fails_without_mutating():
    recipe = Recipe.model_validate(
        {
            "id": "run",
            "name": "Run",
            "steps": [{"action": "app.launch", "command": "demo.exe"}],
            "verify": [
                {
                    "action": "assert.window_exists",
                    "title_contains": "Vendor App",
                    "timeout_seconds": 0.01,
                }
            ],
        }
    )
    fakes = FakeAdapters()
    fakes.window.responses["window_exists"] = False

    summary = WorkflowExecutor(adapters=fakes.bundle()).run(recipe)

    assert not summary.success
    assert summary.results[-1].status == "failed"
    assert "window not found" in summary.results[-1].message
    assert [call[0] for call in fakes.window.calls]
    assert {call[0] for call in fakes.window.calls} == {"window_exists"}


def test_registry_assertion_is_windows_only(monkeypatch):
    monkeypatch.setattr("ritualist.actions.assert_actions.sys.platform", "linux")
    step = AssertRegistryValueStep.model_validate(
        {
            "action": "assert.registry_value",
            "key": r"HKCU\\Software\\Vendor",
            "value_name": "Connected",
        }
    )

    summary = WorkflowExecutor(
        adapters=FakeAdapters().bundle(),
        config=AppConfig(),
    ).run(
        Recipe.model_validate(
            {
                "id": "run",
                "name": "Run",
                "steps": [{"action": "app.launch", "command": "demo.exe"}],
                "verify": [step.model_dump()],
            }
        )
    )

    assert not summary.success
    assert "only supported on Windows" in summary.results[-1].message


def test_registry_assertion_reads_value_with_fake_winreg(monkeypatch):
    winreg = ModuleType("winreg")
    winreg.HKEY_CURRENT_USER = object()
    winreg.HKEY_LOCAL_MACHINE = object()
    winreg.HKEY_CLASSES_ROOT = object()
    winreg.HKEY_USERS = object()
    winreg.HKEY_CURRENT_CONFIG = object()
    winreg.KEY_READ = 1
    opened = {}

    class FakeKey:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    def open_key(hive, subkey, _reserved, access):
        opened["hive"] = hive
        opened["subkey"] = subkey
        opened["access"] = access
        return FakeKey()

    def query_value(_handle, value_name):
        assert value_name == "Connected"
        return "yes", 1

    winreg.OpenKey = open_key
    winreg.QueryValueEx = query_value
    monkeypatch.setattr("ritualist.actions.assert_actions.sys.platform", "win32")
    monkeypatch.setitem(sys.modules, "winreg", winreg)
    recipe = Recipe.model_validate(
        {
            "id": "run",
            "name": "Run",
            "steps": [{"action": "app.launch", "command": "demo.exe"}],
            "verify": [
                {
                    "action": "assert.registry_value",
                    "key": r"HKCU\\Software\\Vendor",
                    "value_name": "Connected",
                    "expected_value": "yes",
                }
            ],
        }
    )

    summary = WorkflowExecutor(adapters=FakeAdapters().bundle(), config=AppConfig()).run(recipe)

    assert summary.success
    assert opened["subkey"] == r"Software\\Vendor"
