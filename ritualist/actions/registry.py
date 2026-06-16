from __future__ import annotations

from dataclasses import dataclass, field

from .base import ActionHandler
from .metadata import ActionMetadata


@dataclass
class ActionRegistry:
    _handlers: dict[str, ActionHandler] = field(default_factory=dict)

    def register(self, handler: ActionHandler) -> None:
        metadata = getattr(handler, "metadata", None)
        if not isinstance(metadata, ActionMetadata):
            raise ValueError(f"handler '{handler.action_type}' must declare ActionMetadata")
        if metadata.action_name != handler.action_type:
            raise ValueError(
                f"metadata action '{metadata.action_name}' does not match "
                f"handler action '{handler.action_type}'"
            )
        self._handlers[handler.action_type] = handler

    def get(self, action_type: str) -> ActionHandler:
        try:
            return self._handlers[action_type]
        except KeyError as exc:
            raise KeyError(f"no handler registered for action '{action_type}'") from exc

    def action_types(self) -> list[str]:
        return sorted(self._handlers)

    def metadata(self, action_type: str) -> ActionMetadata:
        return self.get(action_type).metadata

    def metadata_items(self) -> list[ActionMetadata]:
        return [self._handlers[action_type].metadata for action_type in self.action_types()]


def create_default_registry() -> ActionRegistry:
    from .app_actions import AppLaunchHandler, AppWaitProcessHandler
    from .assert_actions import create_assertion_handlers
    from .browser_actions import BrowserMediaHandler, BrowserOpenHandler
    from .confirm_actions import ConfirmAskHandler
    from .desktop_actions import DesktopClickTextHandler
    from .input_actions import InputHotkeyHandler
    from .wait_actions import create_wait_handlers
    from .window_actions import (
        WindowFocusHandler,
        WindowMaximizeHandler,
        WindowMinimizeHandler,
        WindowMoveHandler,
        WindowResizeHandler,
        WindowRestoreHandler,
        WindowSnapBottomHandler,
        WindowSnapLeftHandler,
        WindowSnapRightHandler,
        WindowSnapTopHandler,
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
        WindowMoveHandler(),
        WindowResizeHandler(),
        WindowMaximizeHandler(),
        WindowRestoreHandler(),
        WindowSnapLeftHandler(),
        WindowSnapRightHandler(),
        WindowSnapTopHandler(),
        WindowSnapBottomHandler(),
        WindowWaitHandler(),
        DesktopClickTextHandler(),
        InputHotkeyHandler(),
        ConfirmAskHandler(),
        *create_wait_handlers(),
    ):
        registry.register(handler)
    return registry
