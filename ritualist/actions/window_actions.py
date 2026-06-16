from __future__ import annotations

from typing import Any

from ritualist.models import (
    WindowFocusStep,
    WindowMaximizeStep,
    WindowMinimizeStep,
    WindowMoveStep,
    WindowResizeStep,
    WindowRestoreStep,
    WindowSnapBottomStep,
    WindowSnapLeftStep,
    WindowSnapRightStep,
    WindowSnapTopStep,
    WindowWaitStep,
)

from .base import ActionContext, ActionOutcome, target_region_metadata
from .metadata import ActionMetadata, WINDOWS_ONLY


def _layout_metadata(action_type: str, *, required_params: tuple[str, ...]) -> ActionMetadata:
    return ActionMetadata(
        action_name=action_type,
        schema_version="0.1",
        category="window",
        required_params=required_params,
        optional_params=("timeout_seconds", "requires_confirmation", "name", "optional"),
        required_capabilities=("windows_uia", "window_management"),
        supported_platforms=WINDOWS_ONLY,
        side_effect_level="controls_ui",
        confirmation_policy="optional",
        allowed_in_imported_packs=False,
    )


def _layout_target_kwargs(step: Any, timeout_seconds: float) -> dict[str, Any]:
    return {
        "title_contains": step.title_contains,
        "process_name": None,
        "timeout_seconds": timeout_seconds,
    }


class WindowFocusHandler:
    action_type = "window.focus"
    metadata = ActionMetadata(
        action_name=action_type,
        schema_version="0.1",
        category="window",
        required_params=(),
        optional_params=("title_contains", "process_name", "timeout_seconds", "name", "optional"),
        required_capabilities=("windows_uia", "window_management"),
        supported_platforms=WINDOWS_ONLY,
        side_effect_level="controls_ui",
        confirmation_policy="optional",
        allowed_in_imported_packs=False,
    )

    def run(self, step: WindowFocusStep, context: ActionContext) -> ActionOutcome:
        timeout = step.timeout_seconds or 10.0
        region = context.adapters.window.focus(
            title_contains=step.title_contains,
            process_name=step.process_name,
            timeout_seconds=timeout,
        )
        return ActionOutcome(message="focused window", metadata=target_region_metadata(region))


class WindowMinimizeHandler:
    action_type = "window.minimize"
    metadata = ActionMetadata(
        action_name=action_type,
        schema_version="0.1",
        category="window",
        required_params=(),
        optional_params=("title_contains", "process_name", "timeout_seconds", "name", "optional"),
        required_capabilities=("windows_uia", "window_management"),
        supported_platforms=WINDOWS_ONLY,
        side_effect_level="controls_ui",
        confirmation_policy="optional",
        allowed_in_imported_packs=False,
    )

    def run(self, step: WindowMinimizeStep, context: ActionContext) -> ActionOutcome:
        timeout = step.timeout_seconds or 10.0
        region = context.adapters.window.minimize(
            title_contains=step.title_contains,
            process_name=step.process_name,
            timeout_seconds=timeout,
        )
        return ActionOutcome(message="minimized window", metadata=target_region_metadata(region))


class WindowMaximizeHandler:
    action_type = "window.maximize"
    metadata = ActionMetadata(
        action_name=action_type,
        schema_version="0.1",
        category="window",
        required_params=(),
        optional_params=("title_contains", "process_name", "timeout_seconds", "name", "optional"),
        required_capabilities=("windows_uia", "window_management"),
        supported_platforms=WINDOWS_ONLY,
        side_effect_level="controls_ui",
        confirmation_policy="optional",
        allowed_in_imported_packs=False,
    )

    def run(self, step: WindowMaximizeStep, context: ActionContext) -> ActionOutcome:
        timeout = step.timeout_seconds or 10.0
        maximize = getattr(context.adapters.window, "maximize_window", None)
        if maximize is None:
            maximize = context.adapters.window.maximize
        region = maximize(
            title_contains=step.title_contains,
            process_name=step.process_name,
            timeout_seconds=timeout,
        )
        return ActionOutcome(message="maximized window", metadata=target_region_metadata(region))


class WindowMoveHandler:
    action_type = "window.move"
    metadata = _layout_metadata(action_type, required_params=("title_contains", "x", "y"))

    def run(self, step: WindowMoveStep, context: ActionContext) -> ActionOutcome:
        timeout = step.timeout_seconds or 10.0
        region = context.adapters.window.move_window(
            **_layout_target_kwargs(step, timeout),
            x=step.x,
            y=step.y,
        )
        return ActionOutcome(
            message=f"moved window to {step.x},{step.y}",
            metadata=target_region_metadata(region),
        )


class WindowResizeHandler:
    action_type = "window.resize"
    metadata = _layout_metadata(
        action_type,
        required_params=("title_contains", "width", "height"),
    )

    def run(self, step: WindowResizeStep, context: ActionContext) -> ActionOutcome:
        timeout = step.timeout_seconds or 10.0
        region = context.adapters.window.resize_window(
            **_layout_target_kwargs(step, timeout),
            width=step.width,
            height=step.height,
        )
        return ActionOutcome(
            message=f"resized window to {step.width}x{step.height}",
            metadata=target_region_metadata(region),
        )


class WindowRestoreHandler:
    action_type = "window.restore"
    metadata = _layout_metadata(action_type, required_params=("title_contains",))

    def run(self, step: WindowRestoreStep, context: ActionContext) -> ActionOutcome:
        timeout = step.timeout_seconds or 10.0
        region = context.adapters.window.restore_window(
            **_layout_target_kwargs(step, timeout)
        )
        return ActionOutcome(message="restored window", metadata=target_region_metadata(region))


class WindowSnapLeftHandler:
    action_type = "window.snap_left"
    metadata = _layout_metadata(action_type, required_params=("title_contains",))

    def run(self, step: WindowSnapLeftStep, context: ActionContext) -> ActionOutcome:
        timeout = step.timeout_seconds or 10.0
        region = context.adapters.window.snap_left(**_layout_target_kwargs(step, timeout))
        return ActionOutcome(message="snapped window left", metadata=target_region_metadata(region))


class WindowSnapRightHandler:
    action_type = "window.snap_right"
    metadata = _layout_metadata(action_type, required_params=("title_contains",))

    def run(self, step: WindowSnapRightStep, context: ActionContext) -> ActionOutcome:
        timeout = step.timeout_seconds or 10.0
        region = context.adapters.window.snap_right(**_layout_target_kwargs(step, timeout))
        return ActionOutcome(message="snapped window right", metadata=target_region_metadata(region))


class WindowSnapTopHandler:
    action_type = "window.snap_top"
    metadata = _layout_metadata(action_type, required_params=("title_contains",))

    def run(self, step: WindowSnapTopStep, context: ActionContext) -> ActionOutcome:
        timeout = step.timeout_seconds or 10.0
        region = context.adapters.window.snap_top(**_layout_target_kwargs(step, timeout))
        return ActionOutcome(message="snapped window top", metadata=target_region_metadata(region))


class WindowSnapBottomHandler:
    action_type = "window.snap_bottom"
    metadata = _layout_metadata(action_type, required_params=("title_contains",))

    def run(self, step: WindowSnapBottomStep, context: ActionContext) -> ActionOutcome:
        timeout = step.timeout_seconds or 10.0
        region = context.adapters.window.snap_bottom(**_layout_target_kwargs(step, timeout))
        return ActionOutcome(message="snapped window bottom", metadata=target_region_metadata(region))


class WindowWaitHandler:
    action_type = "window.wait"
    metadata = ActionMetadata(
        action_name=action_type,
        schema_version="0.1",
        category="window",
        required_params=(),
        optional_params=(
            "title_contains",
            "process_name",
            "timeout_seconds",
            "on_timeout",
            "name",
            "optional",
            "when",
        ),
        required_capabilities=("windows_uia", "window_management"),
        supported_platforms=WINDOWS_ONLY,
        side_effect_level="read_only",
        confirmation_policy="never",
        allowed_in_imported_packs=True,
    )

    def run(self, step: WindowWaitStep, context: ActionContext) -> ActionOutcome:
        timeout = step.timeout_seconds or 30.0
        region = context.adapters.window.wait(
            title_contains=step.title_contains,
            process_name=step.process_name,
            timeout_seconds=timeout,
        )
        return ActionOutcome(message="window appeared", metadata=target_region_metadata(region))
