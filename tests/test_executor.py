from __future__ import annotations

import pytest

from ritualist.actions.base import ActionContext
from ritualist.actions.metadata import ALL_PLATFORMS, ActionMetadata
from ritualist.actions.registry import ActionRegistry
from ritualist.adapters.fake import FakeAdapters
from ritualist.executor import WorkflowExecutor
from ritualist.models import Recipe
from ritualist.overlay import ScreenRect, TargetRegion
from ritualist.runtime_control import RuntimeControl
from ritualist.runtime_models import Heartbeat, RunFinished, RunState, StepFinished, StepState


def test_executor_runs_steps_in_order():
    recipe = Recipe.model_validate(
        {
            "id": "run",
            "name": "Run",
            "steps": [
                {"action": "browser.open", "url": "https://example.test"},
                {"action": "browser.media", "loop": True, "play": True},
                {"action": "app.launch", "command": "demo.exe"},
            ],
        }
    )
    fakes = FakeAdapters()

    summary = WorkflowExecutor(adapters=fakes.bundle(), confirmer=lambda _: True).run(recipe)

    assert summary.success
    assert [result.status for result in summary.results] == ["success", "success", "success"]
    assert fakes.browser.calls[0][0] == "open_url"
    assert fakes.browser.calls[0][2]["profile"] == "default"
    assert fakes.browser.calls[0][2]["new_window"] is False
    assert fakes.browser.calls[0][2]["keep_open"] is False
    assert fakes.browser.calls[1][0] == "configure_media"
    assert fakes.shell.calls[0][0] == "launch"


def test_executor_stops_on_required_failure():
    recipe = Recipe.model_validate(
        {
            "id": "run",
            "name": "Run",
            "steps": [
                {"action": "browser.open", "url": "https://example.test"},
                {"action": "app.launch", "command": "demo.exe"},
            ],
        }
    )
    fakes = FakeAdapters()
    fakes.browser.failures["open_url"] = RuntimeError("network blocked")

    summary = WorkflowExecutor(adapters=fakes.bundle()).run(recipe)

    assert not summary.success
    assert len(summary.results) == 1
    assert summary.results[0].status == "failed"
    assert fakes.shell.calls == []


def test_executor_continues_after_optional_failure():
    recipe = Recipe.model_validate(
        {
            "id": "run",
            "name": "Run",
            "steps": [
                {
                    "action": "desktop.click_text",
                    "text": "Diablo IV",
                    "window_title_contains": "Battle.net",
                    "optional": True,
                },
                {"action": "app.launch", "command": "demo.exe"},
            ],
        }
    )
    fakes = FakeAdapters()
    fakes.desktop.failures["click_text"] = RuntimeError("not found")

    summary = WorkflowExecutor(adapters=fakes.bundle()).run(recipe)

    assert summary.success
    assert [result.status for result in summary.results] == ["skipped", "success"]
    assert fakes.shell.calls[0][0] == "launch"


def test_executor_cancels_when_confirmation_declined():
    recipe = Recipe.model_validate(
        {
            "id": "run",
            "name": "Run",
            "steps": [
                {
                    "action": "desktop.click_text",
                    "text": "Play",
                    "window_title_contains": "Battle.net",
                    "requires_confirmation": True,
                }
            ],
        }
    )

    summary = WorkflowExecutor(adapters=FakeAdapters().bundle(), confirmer=lambda _: False).run(recipe)

    assert not summary.success
    assert summary.results[0].status == "cancelled"


def test_desktop_click_result_includes_target_preview_metadata_without_overlay():
    recipe = Recipe.model_validate(
        {
            "id": "run",
            "name": "Run",
            "steps": [
                {
                    "action": "desktop.click_text",
                    "text": "Diablo IV",
                    "window_title_contains": "Battle.net",
                    "control_type": "Button",
                }
            ],
        }
    )
    fakes = FakeAdapters()
    fakes.desktop.responses["click_text"] = TargetRegion(
        rect=ScreenRect(101, 202, 80, 40),
        window_title="Battle.net",
        target_text="Diablo IV",
        control_type="Button",
    )
    runtime_events = []

    summary = WorkflowExecutor(
        adapters=fakes.bundle(),
        runtime_event_callback=runtime_events.append,
    ).run(recipe)

    assert summary.success
    assert [call[0] for call in fakes.desktop.calls] == ["click_text"]
    assert summary.results[0].metadata == {
        "target_preview": {
            "window_title": "Battle.net",
            "target_text": "Diablo IV",
            "control_type": "Button",
            "bounds": {"x": 101, "y": 202, "width": 80, "height": 40},
        }
    }
    finished = next(event for event in runtime_events if isinstance(event, StepFinished))
    assert finished.metadata == summary.results[0].metadata


@pytest.mark.parametrize(
    ("step_data", "adapter_call"),
    [
        ({"action": "window.focus", "title_contains": "Battle.net"}, "focus"),
        ({"action": "window.minimize", "title_contains": "Battle.net"}, "minimize"),
        ({"action": "window.maximize", "title_contains": "Battle.net"}, "maximize_window"),
        (
            {"action": "window.move", "title_contains": "Battle.net", "x": 10, "y": 20},
            "move_window",
        ),
        (
            {
                "action": "window.resize",
                "title_contains": "Battle.net",
                "width": 800,
                "height": 600,
            },
            "resize_window",
        ),
        ({"action": "window.restore", "title_contains": "Battle.net"}, "restore_window"),
        ({"action": "window.snap_left", "title_contains": "Battle.net"}, "snap_left"),
        ({"action": "window.snap_right", "title_contains": "Battle.net"}, "snap_right"),
        ({"action": "window.snap_top", "title_contains": "Battle.net"}, "snap_top"),
        ({"action": "window.snap_bottom", "title_contains": "Battle.net"}, "snap_bottom"),
        ({"action": "window.wait", "title_contains": "Battle.net"}, "wait"),
    ],
)
def test_window_action_result_includes_bounds_metadata_without_overlay(step_data, adapter_call):
    recipe = Recipe.model_validate(
        {
            "id": "run",
            "name": "Run",
            "steps": [step_data],
        }
    )
    fakes = FakeAdapters()
    fakes.window.responses[adapter_call] = TargetRegion(
        rect=ScreenRect(10, 20, 300, 200),
        window_title="Battle.net",
    )

    summary = WorkflowExecutor(adapters=fakes.bundle()).run(recipe)

    assert summary.success
    assert [call[0] for call in fakes.window.calls] == [adapter_call]
    assert summary.results[0].metadata == {
        "target_preview": {
            "window_title": "Battle.net",
            "bounds": {"x": 10, "y": 20, "width": 300, "height": 200},
        }
    }


def test_window_layout_actions_pass_title_scope_to_adapter():
    recipe = Recipe.model_validate(
        {
            "id": "run",
            "name": "Run",
            "steps": [
                {
                    "action": "window.move",
                    "title_contains": "Battle.net",
                    "x": 100,
                    "y": 200,
                    "timeout_seconds": 3,
                },
                {
                    "action": "window.resize",
                    "title_contains": "Battle.net",
                    "width": 1280,
                    "height": 720,
                },
            ],
        }
    )
    fakes = FakeAdapters()

    summary = WorkflowExecutor(adapters=fakes.bundle()).run(recipe)

    assert summary.success
    assert fakes.window.calls[0] == (
        "move_window",
        (),
        {
            "title_contains": "Battle.net",
            "process_name": None,
            "timeout_seconds": 3.0,
            "x": 100,
            "y": 200,
        },
    )
    assert fakes.window.calls[1] == (
        "resize_window",
        (),
        {
            "title_contains": "Battle.net",
            "process_name": None,
            "timeout_seconds": 10.0,
            "width": 1280,
            "height": 720,
        },
    )


def test_confirm_ask_uses_structured_request_with_recipe_details():
    recipe = Recipe.model_validate(
        {
            "id": "run",
            "name": "Run",
            "steps": [
                {
                    "name": "Pause before launch",
                    "action": "confirm.ask",
                    "prompt": "Continue?",
                }
            ],
        }
    )
    requests = []

    summary = WorkflowExecutor(
        adapters=FakeAdapters().bundle(),
        confirmer=lambda request: requests.append(request) or True,
    ).run(recipe)

    assert summary.success
    request = requests[0]
    assert request.recipe_name == "Run"
    assert request.step_name == "Pause before launch"
    assert request.action == "confirm.ask"
    assert request.prompt == "Continue?"


def test_executor_emits_runtime_events_for_success_and_keeps_step_callback():
    recipe = Recipe.model_validate(
        {
            "id": "run",
            "name": "Run",
            "steps": [{"action": "app.launch", "command": "demo.exe"}],
        }
    )
    runtime_events = []
    step_events = []

    summary = WorkflowExecutor(
        adapters=FakeAdapters().bundle(),
        runtime_event_callback=runtime_events.append,
        status_callback=step_events.append,
    ).run(recipe)

    assert summary.success
    assert [event.sequence for event in runtime_events] == list(range(len(runtime_events)))
    assert [event.type for event in runtime_events] == [
        "run.started",
        "heartbeat",
        "step.started",
        "log.message",
        "log.message",
        "step.finished",
        "run.state_changed",
        "run.finished",
    ]
    assert [event.status for event in step_events] == ["running", "success"]
    assert [event.state for event in runtime_events if isinstance(event, StepFinished)] == [
        StepState.SUCCESS
    ]
    assert isinstance(runtime_events[-1], RunFinished)
    assert runtime_events[-1].state == RunState.SUCCESS


def test_executor_emits_failed_runtime_state_for_required_step_failure():
    recipe = Recipe.model_validate(
        {
            "id": "run",
            "name": "Run",
            "steps": [
                {"action": "browser.open", "url": "https://example.test/?token=secret"},
                {"action": "app.launch", "command": "demo.exe"},
            ],
        }
    )
    fakes = FakeAdapters()
    fakes.browser.failures["open_url"] = RuntimeError("network blocked")
    runtime_events = []

    summary = WorkflowExecutor(
        adapters=fakes.bundle(),
        runtime_event_callback=runtime_events.append,
    ).run(recipe)

    assert not summary.success
    assert fakes.shell.calls == []
    assert [event.state for event in runtime_events if isinstance(event, StepFinished)] == [
        StepState.FAILED
    ]
    assert [event.state for event in runtime_events if event.type == "run.state_changed"] == [
        RunState.FAILED
    ]
    assert runtime_events[-1].state == RunState.FAILED


def test_executor_emits_wait_status_metadata():
    recipe = Recipe.model_validate(
        {
            "id": "run",
            "name": "Run",
            "steps": [{"action": "wait.seconds", "seconds": 0.01, "timeout_seconds": 0.2}],
        }
    )
    runtime_events = []
    step_events = []

    summary = WorkflowExecutor(
        adapters=FakeAdapters().bundle(),
        runtime_event_callback=runtime_events.append,
        status_callback=step_events.append,
    ).run(recipe)

    waiting_status = next(event for event in step_events if event.status == "running")
    waiting_heartbeat = next(
        event
        for event in runtime_events
        if isinstance(event, Heartbeat) and event.run_state == RunState.WAITING
    )

    assert summary.success
    assert waiting_status.wait_action == "wait.seconds"
    assert waiting_status.wait_target == "0.01s"
    assert waiting_status.wait_timeout_seconds == 0.2
    assert waiting_status.wait_started_at is not None
    assert waiting_heartbeat.action == "wait.seconds"
    assert waiting_heartbeat.wait_target == "0.01s"
    assert waiting_heartbeat.wait_timeout_seconds == 0.2


def test_executor_emits_skipped_runtime_step_for_optional_failure():
    recipe = Recipe.model_validate(
        {
            "id": "run",
            "name": "Run",
            "steps": [
                {
                    "action": "desktop.click_text",
                    "text": "Diablo IV",
                    "window_title_contains": "Battle.net",
                    "optional": True,
                },
                {"action": "app.launch", "command": "demo.exe"},
            ],
        }
    )
    fakes = FakeAdapters()
    fakes.desktop.failures["click_text"] = RuntimeError("not found")
    runtime_events = []

    summary = WorkflowExecutor(
        adapters=fakes.bundle(),
        runtime_event_callback=runtime_events.append,
    ).run(recipe)

    assert summary.success
    assert [event.state for event in runtime_events if isinstance(event, StepFinished)] == [
        StepState.SKIPPED,
        StepState.SUCCESS,
    ]
    assert runtime_events[-1].state == RunState.SUCCESS


def test_executor_stops_before_step_with_runtime_control():
    recipe = Recipe.model_validate(
        {
            "id": "run",
            "name": "Run",
            "steps": [{"action": "app.launch", "command": "demo.exe"}],
        }
    )
    control = RuntimeControl()
    control.stop()
    runtime_events = []

    summary = WorkflowExecutor(
        adapters=FakeAdapters().bundle(),
        runtime_control=control,
        runtime_event_callback=runtime_events.append,
    ).run(recipe)

    assert not summary.success
    assert summary.results[0].status == "cancelled"
    assert [event.type for event in runtime_events] == [
        "run.started",
        "heartbeat",
        "run.state_changed",
        "step.finished",
        "run.state_changed",
        "run.finished",
    ]
    assert [event.state for event in runtime_events if isinstance(event, StepFinished)] == [
        StepState.CANCELLED
    ]
    assert runtime_events[-1].state == RunState.STOPPED


def test_executor_stops_during_cooperative_wait_path():
    recipe = Recipe.model_validate(
        {
            "id": "run",
            "name": "Run",
            "steps": [{"action": "app.launch", "command": "demo.exe"}],
        }
    )
    registry = ActionRegistry()
    registry.register(_StoppingAppLaunchHandler())
    runtime_events = []

    summary = WorkflowExecutor(
        registry=registry,
        adapters=FakeAdapters().bundle(),
        runtime_event_callback=runtime_events.append,
    ).run(recipe)

    assert not summary.success
    assert summary.results[0].status == "cancelled"
    assert [event.state for event in runtime_events if isinstance(event, StepFinished)] == [
        StepState.CANCELLED
    ]
    assert [event.state for event in runtime_events if event.type == "run.state_changed"] == [
        RunState.STOPPING,
        RunState.STOPPED,
    ]
    assert runtime_events[-1].state == RunState.STOPPED


class _StoppingAppLaunchHandler:
    action_type = "app.launch"
    metadata = ActionMetadata(
        action_name=action_type,
        schema_version="0.1",
        category="app",
        required_params=("command",),
        optional_params=("args", "cwd", "wait", "env", "name", "optional", "timeout_seconds"),
        required_capabilities=("app_launch",),
        supported_platforms=ALL_PLATFORMS,
        side_effect_level="launches_app",
        confirmation_policy="optional",
        allowed_in_imported_packs=False,
    )

    def run(self, step, context: ActionContext) -> str:
        context.runtime_control.stop()
        context.runtime_control.heartbeat()
        return "unreachable"
