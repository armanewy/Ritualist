from __future__ import annotations

from ritualist.models import DesktopClickTextStep

from .base import ActionContext


class DesktopClickTextHandler:
    action_type = "desktop.click_text"

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
