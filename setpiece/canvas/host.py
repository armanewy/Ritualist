from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from setpiece.errors import SetpieceError

CANVAS_HOST_SCHEMA_VERSION = "setpiece.canvas.host.v1"
CANVAS_FORCE_WINDOWED_ENV = "SETPIECE_CANVAS_FORCE_WINDOWED"


class CanvasHostMode(StrEnum):
    WINDOWED = "windowed"
    DESKTOP_WORK_AREA = "desktop_work_area"
    DESKTOP_FULL_MONITOR_LATER = "desktop_full_monitor_later"
    DESKTOP_ATTACHED_EXPERIMENTAL_LATER = "desktop_attached_experimental_later"
    IMMERSIVE_COUCH_LATER = "immersive_couch_later"
    ADVANCED_SHELL_LATER = "advanced_shell_later"


class CanvasTaskbarPolicy(StrEnum):
    RESPECT = "respect"


class CanvasInputPolicy(StrEnum):
    NORMAL_WINDOW = "normal_window"
    CAPTURE_ALL = "capture_all"


DOCUMENTED_CANVAS_HOST_MODES = tuple(CanvasHostMode)
IMPLEMENTED_CANVAS_HOST_MODES = frozenset(
    {CanvasHostMode.WINDOWED, CanvasHostMode.DESKTOP_WORK_AREA}
)
UNSUPPORTED_TASKBAR_POLICIES = frozenset({"hide", "auto_hide", "replace", "kiosk"})


@dataclass(frozen=True)
class CanvasHostConfig:
    mode: CanvasHostMode = CanvasHostMode.WINDOWED
    taskbar_policy: CanvasTaskbarPolicy = CanvasTaskbarPolicy.RESPECT
    requested_mode: CanvasHostMode | None = None
    forced_windowed: bool = False

    @property
    def effective_requested_mode(self) -> CanvasHostMode:
        return self.requested_mode or self.mode

    @property
    def input_policy(self) -> CanvasInputPolicy:
        if self.mode is CanvasHostMode.DESKTOP_WORK_AREA:
            return CanvasInputPolicy.CAPTURE_ALL
        return CanvasInputPolicy.NORMAL_WINDOW

    @property
    def background_passthrough(self) -> bool:
        return self.mode is CanvasHostMode.DESKTOP_WORK_AREA

    @property
    def blank_area_click_through_status(self) -> str:
        if self.mode is CanvasHostMode.DESKTOP_WORK_AREA:
            return "NEEDS_HUMAN_REVIEW"
        return "NOT_APPLICABLE"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": CANVAS_HOST_SCHEMA_VERSION,
            "mode": self.mode.value,
            "requested_mode": self.effective_requested_mode.value,
            "taskbar_policy": self.taskbar_policy.value,
            "implemented": self.mode in IMPLEMENTED_CANVAS_HOST_MODES,
            "taskbar_visible": self.taskbar_policy is CanvasTaskbarPolicy.RESPECT,
            "forced_windowed": self.forced_windowed,
            "force_windowed_env": CANVAS_FORCE_WINDOWED_ENV,
            "background_passthrough": self.background_passthrough,
            "background_mode": "system_wallpaper" if self.background_passthrough else "setpiece_background",
            "input_policy": self.input_policy.value,
            "blank_area_input": (
                "captured_by_canvas_window"
                if self.input_policy is CanvasInputPolicy.CAPTURE_ALL
                else "normal_window_behavior"
            ),
            "component_input": "clickable",
            "edit_mode_input": "captures_canvas_for_layout_editing",
            "click_through_implemented": False,
            "blank_area_click_through_status": self.blank_area_click_through_status,
            "blank_area_click_through_machine_verified": False,
        }


def resolve_canvas_host_config(
    mode: str | CanvasHostMode | None = None,
    *,
    taskbar_policy: str | CanvasTaskbarPolicy | None = None,
    require_implemented: bool = True,
) -> CanvasHostConfig:
    """Normalize and validate a Canvas host launch request."""

    requested_mode = normalize_canvas_host_mode(mode)
    force_windowed = _force_windowed_enabled()
    config = CanvasHostConfig(
        mode=CanvasHostMode.WINDOWED if force_windowed else requested_mode,
        requested_mode=requested_mode,
        forced_windowed=force_windowed,
        taskbar_policy=normalize_canvas_taskbar_policy(taskbar_policy),
    )
    if require_implemented:
        ensure_canvas_host_is_implemented(config)
    return config


def ensure_canvas_host_is_implemented(config: CanvasHostConfig) -> None:
    if config.taskbar_policy is not CanvasTaskbarPolicy.RESPECT:
        raise SetpieceError("Canvas taskbar policy must be 'respect'.")
    if config.mode not in IMPLEMENTED_CANVAS_HOST_MODES:
        raise SetpieceError(
            "Canvas host mode "
            f"'{config.mode.value}' is documented but not implemented yet; use 'windowed'."
        )


def default_canvas_for_host(canvas: str | None, config: CanvasHostConfig) -> str:
    requested = str(canvas or "").strip()
    if requested:
        return requested
    if config.mode is CanvasHostMode.DESKTOP_WORK_AREA:
        return "minimal_desktop"
    return "gaming_desktop"


def normalize_canvas_host_mode(mode: str | CanvasHostMode | None) -> CanvasHostMode:
    if isinstance(mode, CanvasHostMode):
        return mode
    normalized = _normalize_token(mode, default=CanvasHostMode.WINDOWED.value)
    if normalized in {"desktop_overlay", "overlay"}:
        raise SetpieceError(
            "Canvas host mode 'desktop_overlay' is retired; use 'desktop_work_area' "
            "or '--host desktop-work-area' when that host is implemented."
        )
    try:
        return CanvasHostMode(normalized)
    except ValueError as exc:
        allowed = ", ".join(host.value for host in DOCUMENTED_CANVAS_HOST_MODES)
        raise SetpieceError(f"Unsupported Canvas host mode '{mode}'. Allowed host modes: {allowed}.") from exc


def normalize_canvas_taskbar_policy(
    taskbar_policy: str | CanvasTaskbarPolicy | None,
) -> CanvasTaskbarPolicy:
    if isinstance(taskbar_policy, CanvasTaskbarPolicy):
        return taskbar_policy
    normalized = _normalize_token(taskbar_policy, default=CanvasTaskbarPolicy.RESPECT.value)
    if normalized in UNSUPPORTED_TASKBAR_POLICIES:
        raise SetpieceError(
            "Taskbar policy "
            f"'{normalized}' is not supported; Setpiece currently only supports 'respect'."
        )
    try:
        return CanvasTaskbarPolicy(normalized)
    except ValueError as exc:
        allowed = ", ".join(policy.value for policy in CanvasTaskbarPolicy)
        raise SetpieceError(
            f"Unsupported Canvas taskbar policy '{taskbar_policy}'. Allowed policies: {allowed}."
        ) from exc


def _normalize_token(value: str | None, *, default: str) -> str:
    text = str(value or "").strip().casefold()
    if not text:
        return default
    normalized = text.replace("-", "_").replace(" ", "_")
    return "_".join(part for part in normalized.split("_") if part)


def _force_windowed_enabled() -> bool:
    return os.environ.get(CANVAS_FORCE_WINDOWED_ENV, "").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }
