from __future__ import annotations

import pytest

from ritualist.approvals import ConfirmationDecision
from ritualist.actions.base import ActionContext
from ritualist.actions.metadata import ALL_PLATFORMS, ActionMetadata
from ritualist.actions.registry import ActionRegistry
from ritualist.adapters.fake import FakeAdapters
from ritualist.executor import WorkflowExecutor
from ritualist.models import Recipe
from ritualist.overlay import ScreenRect, TargetRegion
from ritualist.runtime_control import RuntimeControl
from ritualist.runtime_models import (
    ConfirmationRequested,
    ConfirmationResolved,
    Heartbeat,
    RunFinished,
    RunState,
    StepFinished,
    StepPaused,
    StepResumed,
    StepState,
    StepWaiting,
)


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


def test_confirmed_desktop_click_absent_target_does_not_request_confirmation():
    recipe = _play_click_recipe()
    fakes = FakeAdapters()
    fakes.desktop.responses["find_text_region"] = None
    confirmations = []
    runtime_events = []

    summary = WorkflowExecutor(
        adapters=fakes.bundle(),
        confirmer=lambda request: confirmations.append(request) or True,
        runtime_event_callback=runtime_events.append,
    ).run(recipe)

    assert not summary.success
    assert summary.results[0].status == "failed"
    assert "target unavailable or blocked before confirmation" in summary.results[0].message
    assert summary.results[0].metadata["target_resolution"] == {
        "status": "unresolved",
        "target": None,
    }
    assert confirmations == []
    assert not any(isinstance(event, ConfirmationRequested) for event in runtime_events)
    assert [call[0] for call in fakes.desktop.calls] == ["find_text_region"]


def test_confirmed_desktop_click_disabled_target_does_not_request_confirmation():
    recipe = _play_click_recipe()
    fakes = FakeAdapters()
    fakes.desktop.responses["find_text_region"] = TargetRegion(
        rect=ScreenRect(30, 40, 120, 36),
        window_title="Battle.net",
        target_text="Play",
        control_type="Button",
        target_identity="battle-net-play",
        visible=True,
        enabled=False,
    )
    confirmations = []
    runtime_events = []

    summary = WorkflowExecutor(
        adapters=fakes.bundle(),
        confirmer=lambda request: confirmations.append(request) or True,
        runtime_event_callback=runtime_events.append,
    ).run(recipe)

    assert not summary.success
    assert summary.results[0].status == "failed"
    assert summary.results[0].metadata["target_resolution"]["status"] == "blocked"
    assert summary.results[0].metadata["target_resolution"]["target"]["enabled"] is False
    assert confirmations == []
    assert not any(isinstance(event, ConfirmationRequested) for event in runtime_events)
    assert [call[0] for call in fakes.desktop.calls] == ["find_text_region"]


def test_confirmed_desktop_click_enabled_target_requests_confirmation_then_invokes():
    recipe = _play_click_recipe()
    fakes = FakeAdapters()
    confirmations = []
    runtime_events = []

    summary = WorkflowExecutor(
        adapters=fakes.bundle(),
        confirmer=lambda request: confirmations.append(request) or True,
        runtime_event_callback=runtime_events.append,
    ).run(recipe)

    assert summary.success
    assert [call[0] for call in fakes.desktop.calls] == [
        "find_text_region",
        "invoke_resolved_text_region",
    ]
    assert confirmations[0].prompt == "Start Diablo IV"
    assert summary.results[0].metadata["target_resolution"]["status"] == "resolved"
    assert summary.results[0].metadata["approval"] == {"status": "approved"}
    assert summary.results[0].metadata["target_invocation"]["status"] == "invoked"
    assert any(isinstance(event, ConfirmationRequested) for event in runtime_events)


def test_remembered_approval_is_stored_and_reused_after_target_resolution(tmp_path):
    recipe = _play_click_recipe()
    approval_store = tmp_path / "preferences.json"
    first_fakes = FakeAdapters()
    first_confirmations = []

    first = WorkflowExecutor(
        adapters=first_fakes.bundle(),
        confirmer=lambda request: first_confirmations.append(request)
        or ConfirmationDecision.always_allow_local(),
        approval_store_path=approval_store,
    ).run(recipe)

    assert first.success
    assert first_confirmations
    assert first.results[0].metadata["approval"] == {"status": "approved"}
    assert first.results[0].metadata["remembered_approval"]["status"] == "stored"

    second_fakes = FakeAdapters()
    second_confirmations = []
    second = WorkflowExecutor(
        adapters=second_fakes.bundle(),
        confirmer=lambda request: second_confirmations.append(request) or False,
        approval_store_path=approval_store,
    ).run(recipe)

    assert second.success
    assert second_confirmations == []
    assert [call[0] for call in second_fakes.desktop.calls] == [
        "find_text_region",
        "invoke_resolved_text_region",
    ]
    assert second.results[0].metadata["approval"] == {"status": "remembered"}
    assert second.results[0].metadata["remembered_approval"]["status"] == "applied"


def test_remembered_approval_invalidates_when_target_identity_changes(tmp_path):
    recipe = _play_click_recipe()
    approval_store = tmp_path / "preferences.json"

    first_fakes = FakeAdapters()
    WorkflowExecutor(
        adapters=first_fakes.bundle(),
        confirmer=lambda _request: ConfirmationDecision.always_allow_local(),
        approval_store_path=approval_store,
    ).run(recipe)

    changed_fakes = FakeAdapters()
    changed_fakes.desktop.responses["find_text_region"] = TargetRegion(
        rect=ScreenRect(30, 40, 120, 36),
        window_title="Battle.net",
        target_text="Play",
        control_type="Button",
        target_identity="changed-play-target",
        visible=True,
        enabled=True,
    )
    confirmations = []

    summary = WorkflowExecutor(
        adapters=changed_fakes.bundle(),
        confirmer=lambda request: confirmations.append(request) or True,
        approval_store_path=approval_store,
    ).run(recipe)

    assert summary.success
    assert confirmations
    assert summary.results[0].metadata["approval"] == {"status": "approved"}


def test_imported_source_does_not_inherit_local_remembered_approval(tmp_path):
    recipe = _play_click_recipe()
    approval_store = tmp_path / "preferences.json"

    WorkflowExecutor(
        adapters=FakeAdapters().bundle(),
        confirmer=lambda _request: ConfirmationDecision.always_allow_local(),
        approval_store_path=approval_store,
    ).run(recipe)

    confirmations = []
    summary = WorkflowExecutor(
        adapters=FakeAdapters().bundle(),
        confirmer=lambda request: confirmations.append(request) or True,
        approval_store_path=approval_store,
        approval_source_trust="imported_pack",
    ).run(recipe)

    assert summary.success
    assert confirmations
    assert summary.results[0].metadata["approval"] == {"status": "approved"}


def test_ambiguous_target_blocks_before_remembered_approval(tmp_path):
    recipe = _play_click_recipe()
    approval_store = tmp_path / "preferences.json"

    WorkflowExecutor(
        adapters=FakeAdapters().bundle(),
        confirmer=lambda _request: ConfirmationDecision.always_allow_local(),
        approval_store_path=approval_store,
    ).run(recipe)

    fakes = FakeAdapters()
    fakes.desktop.responses["find_text_region"] = TargetRegion(
        rect=ScreenRect(30, 40, 120, 36),
        window_title="Battle.net",
        target_text="Play",
        control_type="Button",
        target_identity="battle-net-play",
        visible=True,
        enabled=True,
        ambiguous=True,
    )
    confirmations = []

    summary = WorkflowExecutor(
        adapters=fakes.bundle(),
        confirmer=lambda request: confirmations.append(request) or True,
        approval_store_path=approval_store,
    ).run(recipe)

    assert not summary.success
    assert confirmations == []
    assert summary.results[0].metadata["target_resolution"]["status"] == "blocked"
    assert summary.results[0].metadata["target_resolution"]["target"]["ambiguous"] is True
    assert [call[0] for call in fakes.desktop.calls] == ["find_text_region"]


def test_confirmed_desktop_click_target_disappears_after_approval_fails_visibly():
    recipe = _play_click_recipe()
    fakes = FakeAdapters()
    fakes.desktop.failures["invoke_resolved_text_region"] = RuntimeError(
        "resolved target changed or disappeared before invocation"
    )
    confirmations = []

    summary = WorkflowExecutor(
        adapters=fakes.bundle(),
        confirmer=lambda request: confirmations.append(request) or True,
    ).run(recipe)

    assert not summary.success
    assert confirmations
    assert summary.results[0].status == "failed"
    assert "resolved target changed or disappeared" in summary.results[0].message
    assert summary.results[0].metadata["approval"] == {"status": "approved"}
    assert summary.results[0].metadata["target_invocation"]["status"] == "failed"
    assert [call[0] for call in fakes.desktop.calls] == [
        "find_text_region",
        "invoke_resolved_text_region",
    ]


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
    waiting_event = next(event for event in runtime_events if isinstance(event, StepWaiting))

    assert summary.success
    assert waiting_status.wait_action == "wait.seconds"
    assert waiting_status.wait_target == "0.01s"
    assert waiting_status.wait_timeout_seconds == 0.2
    assert waiting_status.wait_started_at is not None
    assert waiting_heartbeat.action == "wait.seconds"
    assert waiting_heartbeat.wait_target == "0.01s"
    assert waiting_heartbeat.wait_timeout_seconds == 0.2
    assert waiting_event.action == "wait.seconds"
    assert waiting_event.target == "0.01s"
    assert waiting_event.timeout_seconds == 0.2
    event_types = [event.type for event in runtime_events]
    assert event_types.index("step.started") < event_types.index("step.waiting")
    assert event_types.index("step.waiting") < event_types.index("step.finished")


def test_executor_emits_confirmation_events_when_confirmation_declined():
    recipe = Recipe.model_validate(
        {
            "id": "run",
            "name": "Run",
            "steps": [
                {
                    "name": "Ask before clicking Play",
                    "action": "desktop.click_text",
                    "text": "Play",
                    "window_title_contains": "Battle.net",
                    "requires_confirmation": True,
                }
            ],
        }
    )
    runtime_events = []

    summary = WorkflowExecutor(
        adapters=FakeAdapters().bundle(),
        confirmer=lambda _request: False,
        runtime_event_callback=runtime_events.append,
    ).run(recipe)

    requested = next(event for event in runtime_events if isinstance(event, ConfirmationRequested))
    resolved = next(event for event in runtime_events if isinstance(event, ConfirmationResolved))

    assert not summary.success
    assert requested.step_name == "Ask before clicking Play"
    assert requested.action == "desktop.click_text"
    assert resolved.confirmation_id == requested.confirmation_id
    assert resolved.approved is False
    assert resolved.state is StepState.CANCELLED
    assert runtime_events[-1].state is RunState.STOPPED
    event_types = [event.type for event in runtime_events]
    assert event_types.index("confirmation.requested") < event_types.index(
        "confirmation.resolved"
    )
    assert event_types.index("confirmation.resolved") < event_types.index("step.finished")


def test_executor_emits_wait_for_user_confirmation_events():
    recipe = Recipe.model_validate(
        {
            "id": "run",
            "name": "Run",
            "steps": [{"action": "wait.for_user", "prompt": "Continue?"}],
        }
    )
    runtime_events = []

    summary = WorkflowExecutor(
        adapters=FakeAdapters().bundle(),
        confirmer=lambda _request: True,
        runtime_event_callback=runtime_events.append,
    ).run(recipe)

    assert summary.success
    assert any(isinstance(event, StepWaiting) for event in runtime_events)
    assert any(isinstance(event, ConfirmationRequested) for event in runtime_events)
    assert any(
        isinstance(event, ConfirmationResolved) and event.approved is True
        for event in runtime_events
    )
    event_types = [event.type for event in runtime_events]
    assert event_types.index("step.waiting") < event_types.index("confirmation.requested")
    assert event_types.index("confirmation.requested") < event_types.index(
        "confirmation.resolved"
    )


def test_executor_emits_pause_and_resume_events_during_wait():
    recipe = Recipe.model_validate(
        {
            "id": "run",
            "name": "Run",
            "steps": [{"action": "wait.seconds", "seconds": 0.1}],
        }
    )
    registry = ActionRegistry()
    registry.register(_PauseResumeWaitHandler())
    runtime_events = []

    summary = WorkflowExecutor(
        registry=registry,
        adapters=FakeAdapters().bundle(),
        runtime_event_callback=runtime_events.append,
    ).run(recipe)

    assert summary.success
    assert any(isinstance(event, StepPaused) for event in runtime_events)
    assert any(isinstance(event, StepResumed) for event in runtime_events)
    event_types = [event.type for event in runtime_events]
    assert event_types.index("step.waiting") < event_types.index("step.paused")
    assert event_types.index("step.paused") < event_types.index("step.resumed")
    assert event_types.index("step.resumed") < event_types.index("step.finished")


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


def test_browser_adapter_closes_after_non_keep_open_browser_run():
    recipe = Recipe.model_validate(
        {
            "id": "run",
            "name": "Run",
            "steps": [{"action": "browser.open", "url": "https://example.test"}],
        }
    )
    fakes = FakeAdapters()

    summary = WorkflowExecutor(adapters=fakes.bundle()).run(recipe)

    assert summary.success
    assert fakes.browser.closed is True
    assert [call[0] for call in fakes.browser.calls] == ["open_url", "close"]


def test_browser_adapter_stays_open_after_keep_open_browser_run():
    recipe = Recipe.model_validate(
        {
            "id": "run",
            "name": "Run",
            "steps": [
                {
                    "action": "browser.open",
                    "url": "https://example.test",
                    "keep_open": True,
                }
            ],
        }
    )
    fakes = FakeAdapters()

    summary = WorkflowExecutor(adapters=fakes.bundle()).run(recipe)

    assert summary.success
    assert fakes.browser.closed is False
    assert [call[0] for call in fakes.browser.calls] == ["open_url"]


def test_browser_adapter_stays_open_when_later_step_fails_after_keep_open():
    recipe = Recipe.model_validate(
        {
            "id": "run",
            "name": "Run",
            "steps": [
                {
                    "action": "browser.open",
                    "url": "https://example.test",
                    "keep_open": True,
                },
                {"action": "app.launch", "command": "demo.exe"},
            ],
        }
    )
    fakes = FakeAdapters()
    fakes.shell.failures["launch"] = RuntimeError("missing app")

    summary = WorkflowExecutor(adapters=fakes.bundle()).run(recipe)

    assert not summary.success
    assert fakes.browser.closed is False
    assert [call[0] for call in fakes.browser.calls] == ["open_url"]


def test_browser_adapter_closes_on_explicit_cleanup_after_keep_open():
    recipe = Recipe.model_validate(
        {
            "id": "run",
            "name": "Run",
            "steps": [
                {
                    "action": "browser.open",
                    "url": "https://example.test",
                    "keep_open": True,
                }
            ],
        }
    )
    fakes = FakeAdapters()
    executor = WorkflowExecutor(adapters=fakes.bundle())

    summary = executor.run(recipe)

    assert summary.success
    assert fakes.browser.closed is False
    assert executor.close_browser_state() is True
    assert fakes.browser.closed is True
    assert [call[0] for call in fakes.browser.calls] == ["open_url", "close"]


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


def _play_click_recipe() -> Recipe:
    return Recipe.model_validate(
        {
            "id": "run",
            "name": "Gaming Mode",
            "home": {"card": {"title": "Diablo IV Night"}},
            "steps": [
                {
                    "name": "Ask before clicking Play",
                    "action": "desktop.click_text",
                    "text": "Play",
                    "window_title_contains": "Battle.net",
                    "control_type": "Button",
                    "requires_confirmation": True,
                }
            ],
        }
    )


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


class _PauseResumeWaitHandler:
    action_type = "wait.seconds"
    metadata = ActionMetadata(
        action_name=action_type,
        schema_version="0.1",
        category="wait",
        required_params=("seconds",),
        optional_params=("timeout_seconds", "name", "optional"),
        required_capabilities=(),
        supported_platforms=ALL_PLATFORMS,
        side_effect_level="read_only",
        confirmation_policy="never",
        allowed_in_imported_packs=True,
    )

    def run(self, step, context: ActionContext) -> str:
        context.runtime_control.pause()
        context.heartbeat()
        context.runtime_control.resume()
        context.heartbeat()
        return "paused and resumed"
