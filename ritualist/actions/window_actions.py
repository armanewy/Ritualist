from __future__ import annotations

from ritualist.models import WindowFocusStep, WindowMaximizeStep, WindowMinimizeStep, WindowWaitStep

from .base import ActionContext


class WindowFocusHandler:
    action_type = "window.focus"

    def run(self, step: WindowFocusStep, context: ActionContext) -> str:
        timeout = step.timeout_seconds or 10.0
        context.adapters.window.focus(
            title_contains=step.title_contains,
            process_name=step.process_name,
            timeout_seconds=timeout,
        )
        return "focused window"


class WindowMinimizeHandler:
    action_type = "window.minimize"

    def run(self, step: WindowMinimizeStep, context: ActionContext) -> str:
        timeout = step.timeout_seconds or 10.0
        context.adapters.window.minimize(
            title_contains=step.title_contains,
            process_name=step.process_name,
            timeout_seconds=timeout,
        )
        return "minimized window"


class WindowMaximizeHandler:
    action_type = "window.maximize"

    def run(self, step: WindowMaximizeStep, context: ActionContext) -> str:
        timeout = step.timeout_seconds or 10.0
        context.adapters.window.maximize(
            title_contains=step.title_contains,
            process_name=step.process_name,
            timeout_seconds=timeout,
        )
        return "maximized window"


class WindowWaitHandler:
    action_type = "window.wait"

    def run(self, step: WindowWaitStep, context: ActionContext) -> str:
        timeout = step.timeout_seconds or 30.0
        context.adapters.window.wait(
            title_contains=step.title_contains,
            process_name=step.process_name,
            timeout_seconds=timeout,
        )
        return "window appeared"
