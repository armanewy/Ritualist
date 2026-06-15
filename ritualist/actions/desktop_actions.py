from __future__ import annotations

from ritualist.models import DesktopClickTextStep

from .base import ActionContext
from .metadata import ActionMetadata, WINDOWS_ONLY


class DesktopClickTextHandler:
    action_type = "desktop.click_text"
    metadata = ActionMetadata(
        action_name=action_type,
        schema_version="0.1",
        category="desktop",
        required_params=("text", "window_title_contains"),
        optional_params=(
            "control_type",
            "exact",
            "button",
            "requires_confirmation",
            "timeout_seconds",
            "name",
            "optional",
        ),
        required_capabilities=("windows_uia",),
        supported_platforms=WINDOWS_ONLY,
        side_effect_level="risky",
        confirmation_policy="required_for_play",
        allowed_in_imported_packs=False,
    )

    def run(self, step: DesktopClickTextStep, context: ActionContext) -> str:
        timeout = step.timeout_seconds or 10.0
        context.adapters.desktop.click_text(
            text=step.text,
            window_title_contains=step.window_title_contains,
            control_type=step.control_type,
            exact=step.exact,
            button=step.button,
            timeout_seconds=timeout,
        )
        return f"clicked visible text '{step.text}'"
