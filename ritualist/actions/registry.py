from __future__ import annotations

from dataclasses import dataclass, field

from .base import ActionHandler


@dataclass
class ActionRegistry:
    _handlers: dict[str, ActionHandler] = field(default_factory=dict)

    def register(self, handler: ActionHandler) -> None:
        self._handlers[handler.action_type] = handler

    def get(self, action_type: str) -> ActionHandler:
        try:
            return self._handlers[action_type]
        except KeyError as exc:
            raise KeyError(f"no handler registered for action '{action_type}'") from exc

    def action_types(self) -> list[str]:
        return sorted(self._handlers)


def create_default_registry() -> ActionRegistry:
    from .app_actions import AppLaunchHandler, AppWaitProcessHandler
    from .assert_actions import create_assertion_handlers
    from .browser_actions import BrowserMediaHandler, BrowserOpenHandler
    from .confirm_actions import ConfirmAskHandler
    from .desktop_actions import DesktopClickTextHandler
    from .input_actions import InputHotkeyHandler
    from .window_actions import (
        WindowFocusHandler,
        WindowMaximizeHandler,
        WindowMinimizeHandler,
        WindowWaitHandler,
    )

    registry = ActionRegistry()
    for handler in (
        *create_assertion_handlers(),
        BrowserOpenHandler(),
        BrowserMediaHandler(),
        AppLaunchHandler(),
        AppWaitProcessHandler(),
        WindowFocusHandler(),
        WindowMinimizeHandler(),
        WindowMaximizeHandler(),
        WindowWaitHandler(),
        DesktopClickTextHandler(),
        InputHotkeyHandler(),
        ConfirmAskHandler(),
    ):
        registry.register(handler)
    return registry
