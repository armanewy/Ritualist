from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


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
    window_title: str | None = None
    target_text: str | None = None
    control_type: str | None = None


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
    def __init__(self, wrapped: OverlayController | None) -> None:
        self.wrapped = wrapped or NullOverlayController()

    def show_preview(self, preview: ActionPreview, *, duration_ms: int) -> None:
        try:
            self.wrapped.show_preview(preview, duration_ms=duration_ms)
        except Exception:  # noqa: BLE001 - visual trust layer must not break execution.
            return

    def start_wait(self, label: str) -> WaitOverlayHandle:
        try:
            return _BestEffortWaitOverlayHandle(self.wrapped.start_wait(label))
        except Exception:  # noqa: BLE001 - wait HUD failure must not break execution.
            return NullWaitOverlayHandle()


class _BestEffortWaitOverlayHandle:
    def __init__(self, wrapped: WaitOverlayHandle) -> None:
        self.wrapped = wrapped

    def close(self) -> None:
        try:
            self.wrapped.close()
        except Exception:  # noqa: BLE001
            return


def format_confirmation_request(request: ConfirmationRequest | str) -> str:
    if isinstance(request, str):
        return request
    lines = [
        request.prompt,
        f"Step: {request.step_name}",
        f"Action: {request.action}",
    ]
    if request.window_title:
        lines.append(f"Window: {request.window_title}")
    if request.target_text:
        target = request.target_text
        if request.control_type:
            target = f"{target} ({request.control_type})"
        lines.append(f"Target: {target}")
    return "\n".join(lines)
