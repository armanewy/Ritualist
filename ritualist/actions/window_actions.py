from __future__ import annotations

from ritualist.models import WindowFocusStep, WindowMaximizeStep, WindowMinimizeStep, WindowWaitStep

from .base import ActionContext, ActionOutcome, target_region_metadata
from .metadata import ActionMetadata, WINDOWS_ONLY


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
        region = context.adapters.window.maximize(
            title_contains=step.title_contains,
            process_name=step.process_name,
            timeout_seconds=timeout,
        )
        return ActionOutcome(message="maximized window", metadata=target_region_metadata(region))


class WindowWaitHandler:
    action_type = "window.wait"
    metadata = ActionMetadata(
        action_name=action_type,
        schema_version="0.1",
        category="window",
        required_params=(),
        optional_params=("title_contains", "process_name", "timeout_seconds", "name", "optional"),
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
