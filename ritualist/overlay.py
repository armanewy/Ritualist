from __future__ import annotations

import logging
from dataclasses import dataclass
from collections.abc import Callable
from typing import Protocol

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScreenRect:
    x: int
    y: int
    width: int
    height: int

    @property
    def is_valid(self) -> bool:
        return self.width > 0 and self.height > 0


@dataclass(frozen=True)
class TargetRegion:
    rect: ScreenRect | None = None
    window_title: str | None = None
    target_text: str | None = None
    control_type: str | None = None
    target_identity: str | None = None
    visible: bool | None = None
    enabled: bool | None = None


@dataclass(frozen=True)
class ActionPreview:
    action: str
    step_name: str
    label: str
    region: TargetRegion | None = None


@dataclass(frozen=True)
class ConfirmationRequest:
    prompt: str
    action: str
    step_name: str
    recipe_name: str | None = None
    target_scope: str | None = None
    target_type: str | None = None
    window_title: str | None = None
    browser_title: str | None = None
    browser_url: str | None = None
    target_text: str | None = None
    target_role: str | None = None
    target_test_id: str | None = None
    control_type: str | None = None
    target_rect: ScreenRect | None = None
    safety_message: str | None = None


class ConfirmationPresenter(Protocol):
    def request_confirmation(
        self,
        request: ConfirmationRequest | str,
        *,
        on_decision: Callable[[bool], None],
    ) -> None:
        """Present a non-blocking confirmation UI and report the decision."""


class WaitOverlayHandle(Protocol):
    def close(self) -> None:
        """Hide the wait HUD."""


class OverlayController(Protocol):
    def show_preview(self, preview: ActionPreview, *, duration_ms: int) -> None:
        """Show a short-lived action preview."""

    def start_wait(self, label: str) -> WaitOverlayHandle:
        """Show a wait HUD and return a handle that hides it."""


class NullWaitOverlayHandle:
    def close(self) -> None:
        return


class NullOverlayController:
    def show_preview(self, preview: ActionPreview, *, duration_ms: int) -> None:
        return

    def start_wait(self, label: str) -> WaitOverlayHandle:
        return NullWaitOverlayHandle()


class BestEffortOverlayController:
    def __init__(self, wrapped: OverlayController | None, *, logger: logging.Logger | None = None) -> None:
        self.wrapped = wrapped or NullOverlayController()
        self._logger = logger or LOGGER

    def show_preview(self, preview: ActionPreview, *, duration_ms: int) -> None:
        try:
            self.wrapped.show_preview(preview, duration_ms=duration_ms)
        except Exception as exc:  # noqa: BLE001 - visual trust layer must not break execution.
            self._logger.warning("Action overlay preview failed: %s", exc)
            return

    def start_wait(self, label: str) -> WaitOverlayHandle:
        try:
            return _BestEffortWaitOverlayHandle(self.wrapped.start_wait(label), logger=self._logger)
        except Exception as exc:  # noqa: BLE001 - wait HUD failure must not break execution.
            self._logger.warning("Action overlay wait HUD failed: %s", exc)
            return NullWaitOverlayHandle()


class _BestEffortWaitOverlayHandle:
    def __init__(self, wrapped: WaitOverlayHandle, *, logger: logging.Logger) -> None:
        self.wrapped = wrapped
        self._logger = logger

    def close(self) -> None:
        try:
            self.wrapped.close()
        except Exception as exc:  # noqa: BLE001
            self._logger.warning("Action overlay wait HUD close failed: %s", exc)
            return


def format_confirmation_request(request: ConfirmationRequest | str) -> str:
    if isinstance(request, str):
        return request
    lines = [
        request.prompt,
    ]
    if request.recipe_name:
        lines.append(f"Recipe: {request.recipe_name}")
    lines.extend(
        [
            f"Step: {request.step_name}",
            f"Action: {request.action}",
        ]
    )
    if request.window_title:
        lines.append(f"Window: {request.window_title}")
    if request.browser_title:
        lines.append(f"Browser page: {request.browser_title}")
    if request.browser_url:
        lines.append(f"Browser URL: {request.browser_url}")
    if request.target_scope:
        lines.append(f"Target scope: {request.target_scope}")
    if request.target_type:
        lines.append(f"Target type: {request.target_type}")
    if request.target_role:
        lines.append(f"Role: {request.target_role}")
    if request.target_test_id:
        lines.append(f"Test id: {request.target_test_id}")
    if request.target_text:
        target = request.target_text
        if request.control_type:
            target = f"{target} ({request.control_type})"
        lines.append(f"Target: {target}")
    elif request.control_type:
        lines.append(f"Control: {request.control_type}")
    if request.safety_message:
        lines.append(f"Safety: {request.safety_message}")
    return "\n".join(lines)
