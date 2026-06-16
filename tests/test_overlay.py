from __future__ import annotations

from dataclasses import dataclass

from ritualist.adapters.fake import FakeAdapters
from ritualist.config import AppConfig, UIConfig
from ritualist.executor import WorkflowExecutor
from ritualist.models import Recipe
from ritualist.overlay import (
    ActionPreview,
    BestEffortOverlayController,
    ConfirmationRequest,
    NullOverlayController,
    TargetRegion,
    format_confirmation_request,
)


@dataclass
class RecordingWaitHandle:
    closed: bool = False

    def close(self) -> None:
        self.closed = True


class RecordingOverlay:
    def __init__(self) -> None:
        self.previews: list[ActionPreview] = []
        self.preview_durations: list[int] = []
        self.waits: list[str] = []
        self.handles: list[RecordingWaitHandle] = []

    def show_preview(self, preview: ActionPreview, *, duration_ms: int) -> None:
        self.previews.append(preview)
        self.preview_durations.append(duration_ms)

    def start_wait(self, label: str) -> RecordingWaitHandle:
        handle = RecordingWaitHandle()
        self.waits.append(label)
        self.handles.append(handle)
        return handle


class FailingOverlay:
    def show_preview(self, preview: ActionPreview, *, duration_ms: int) -> None:
        raise RuntimeError("overlay failed")

    def start_wait(self, label: str) -> RecordingWaitHandle:
        raise RuntimeError("overlay failed")


def test_desktop_click_preview_and_confirmation_include_target_details():
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
                    "control_type": "Button",
                    "requires_confirmation": True,
                }
            ],
        }
    )
    fakes = FakeAdapters()
    overlay = RecordingOverlay()
    requests: list[ConfirmationRequest | str] = []

    summary = WorkflowExecutor(
        adapters=fakes.bundle(),
        confirmer=lambda request: requests.append(request) or False,
        overlay=overlay,
    ).run(recipe)

    assert summary.results[0].status == "cancelled"
    assert [call[0] for call in fakes.desktop.calls] == ["find_text_region"]
    assert overlay.previews[0].label == "Ritualist: clicking Play"
    request = requests[0]
    assert isinstance(request, ConfirmationRequest)
    assert request.action == "desktop.click_text"
    assert request.step_name == "Ask before clicking Play"
    assert request.recipe_name == "Run"
    assert request.window_title == "Battle.net"
    assert request.target_text == "Play"
    assert request.control_type == "Button"
    assert request.target_rect is not None
    assert request.target_rect.x == 30
    assert request.safety_message == "Clicking visible text exactly equal to Play requires explicit confirmation."


def test_window_wait_starts_and_stops_wait_hud():
    recipe = Recipe.model_validate(
        {
            "id": "run",
            "name": "Run",
            "steps": [{"action": "window.wait", "title_contains": "Battle.net"}],
        }
    )
    overlay = RecordingOverlay()

    summary = WorkflowExecutor(adapters=FakeAdapters().bundle(), overlay=overlay).run(recipe)

    assert summary.success
    assert overlay.waits == ["Waiting for Battle.net..."]
    assert overlay.handles[0].closed is True


def test_overlay_failure_does_not_fail_workflow():
    recipe = Recipe.model_validate(
        {
            "id": "run",
            "name": "Run",
            "steps": [{"action": "window.focus", "title_contains": "Battle.net"}],
        }
    )
    fakes = FakeAdapters()

    summary = WorkflowExecutor(adapters=fakes.bundle(), overlay=FailingOverlay()).run(recipe)

    assert summary.success
    assert [call[0] for call in fakes.window.calls] == ["find_window_region", "focus"]


def test_window_layout_actions_show_overlay_preview():
    recipe = Recipe.model_validate(
        {
            "id": "run",
            "name": "Run",
            "steps": [
                {
                    "action": "window.snap_left",
                    "title_contains": "Battle.net",
                }
            ],
        }
    )
    fakes = FakeAdapters()
    overlay = RecordingOverlay()

    summary = WorkflowExecutor(adapters=fakes.bundle(), overlay=overlay).run(recipe)

    assert summary.success
    assert [call[0] for call in fakes.window.calls] == ["find_window_region", "snap_left"]
    assert overlay.previews[0].action == "window.snap_left"
    assert overlay.previews[0].label == "Ritualist: snapping window left"
    assert overlay.previews[0].region is not None
    assert overlay.previews[0].region.window_title == "Battle.net"


def test_overlay_can_be_disabled_by_config():
    recipe = Recipe.model_validate(
        {
            "id": "run",
            "name": "Run",
            "steps": [{"action": "window.focus", "title_contains": "Battle.net"}],
        }
    )
    fakes = FakeAdapters()
    overlay = RecordingOverlay()
    config = AppConfig(ui=UIConfig(show_action_overlay=False))

    summary = WorkflowExecutor(adapters=fakes.bundle(), overlay=overlay, config=config).run(recipe)

    assert summary.success
    assert overlay.previews == []
    assert [call[0] for call in fakes.window.calls] == ["focus"]


def test_overlay_duration_uses_config_value():
    recipe = Recipe.model_validate(
        {
            "id": "run",
            "name": "Run",
            "steps": [{"action": "window.focus", "title_contains": "Battle.net"}],
        }
    )
    overlay = RecordingOverlay()
    config = AppConfig(ui=UIConfig(overlay_duration_ms=1234))

    summary = WorkflowExecutor(adapters=FakeAdapters().bundle(), overlay=overlay, config=config).run(recipe)

    assert summary.success
    assert overlay.preview_durations == [1234]


def test_desktop_click_preview_can_be_disabled_without_disabling_confirmation_details():
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
    fakes = FakeAdapters()
    overlay = RecordingOverlay()
    requests: list[ConfirmationRequest | str] = []
    config = AppConfig(ui=UIConfig(preview_desktop_clicks=False))

    summary = WorkflowExecutor(
        adapters=fakes.bundle(),
        confirmer=lambda request: requests.append(request) or False,
        overlay=overlay,
        config=config,
    ).run(recipe)

    assert summary.results[0].status == "cancelled"
    assert overlay.previews == []
    assert fakes.desktop.calls == []
    request = requests[0]
    assert isinstance(request, ConfirmationRequest)
    assert request.window_title == "Battle.net"
    assert request.target_text == "Play"


def test_null_overlay_does_not_trigger_hidden_preview_probe():
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
    fakes = FakeAdapters()
    requests: list[ConfirmationRequest | str] = []

    summary = WorkflowExecutor(
        adapters=fakes.bundle(),
        confirmer=lambda request: requests.append(request) or False,
        overlay=NullOverlayController(),
    ).run(recipe)

    assert summary.results[0].status == "cancelled"
    assert fakes.desktop.calls == []
    request = requests[0]
    assert isinstance(request, ConfirmationRequest)
    assert request.window_title == "Battle.net"
    assert request.target_text == "Play"


def test_best_effort_overlay_swallows_and_logs_rendering_failures(caplog):
    caplog.set_level("WARNING", logger="ritualist.overlay")
    controller = BestEffortOverlayController(FailingOverlay())

    controller.show_preview(
        ActionPreview(
            action="window.focus",
            step_name="Focus",
            label="Ritualist: focusing window",
            region=TargetRegion(),
        ),
        duration_ms=700,
    )
    controller.start_wait("Waiting...").close()

    messages = [record.getMessage() for record in caplog.records]
    assert "Action overlay preview failed: overlay failed" in messages
    assert "Action overlay wait HUD failed: overlay failed" in messages


def test_format_confirmation_request_includes_visual_target_context():
    request = ConfirmationRequest(
        prompt="Run 'Ask before clicking Play' (desktop.click_text)?",
        action="desktop.click_text",
        step_name="Ask before clicking Play",
        recipe_name="Gaming Mode",
        window_title="Battle.net",
        target_text="Play",
        control_type="Button",
    )

    formatted = format_confirmation_request(request)

    assert "Action: desktop.click_text" in formatted
    assert "Recipe: Gaming Mode" in formatted
    assert "Step: Ask before clicking Play" in formatted
    assert "Window: Battle.net" in formatted
    assert "Target: Play (Button)" in formatted
    assert "Safety:" not in formatted


def test_format_confirmation_request_includes_control_without_target_text():
    request = ConfirmationRequest(
        prompt="Run 'Focus' (window.focus)?",
        action="window.focus",
        step_name="Focus",
        recipe_name="Gaming Mode",
        control_type="Window",
    )

    formatted = format_confirmation_request(request)

    assert "Recipe: Gaming Mode" in formatted
    assert "Control: Window" in formatted
