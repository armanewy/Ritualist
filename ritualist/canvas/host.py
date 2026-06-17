from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from ritualist.errors import RitualistError

CANVAS_HOST_SCHEMA_VERSION = "ritualist.canvas.host.v1"


class CanvasHostMode(StrEnum):
    WINDOWED = "windowed"
    DESKTOP_WORK_AREA = "desktop_work_area"
    DESKTOP_FULL_MONITOR_LATER = "desktop_full_monitor_later"
    DESKTOP_ATTACHED_EXPERIMENTAL_LATER = "desktop_attached_experimental_later"
    IMMERSIVE_COUCH_LATER = "immersive_couch_later"
    ADVANCED_SHELL_LATER = "advanced_shell_later"


class CanvasTaskbarPolicy(StrEnum):
    RESPECT = "respect"


DOCUMENTED_CANVAS_HOST_MODES = tuple(CanvasHostMode)
IMPLEMENTED_CANVAS_HOST_MODES = frozenset({CanvasHostMode.WINDOWED})
UNSUPPORTED_TASKBAR_POLICIES = frozenset({"hide", "auto_hide", "replace", "kiosk"})


@dataclass(frozen=True)
class CanvasHostConfig:
    mode: CanvasHostMode = CanvasHostMode.WINDOWED
    taskbar_policy: CanvasTaskbarPolicy = CanvasTaskbarPolicy.RESPECT

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": CANVAS_HOST_SCHEMA_VERSION,
            "mode": self.mode.value,
            "taskbar_policy": self.taskbar_policy.value,
            "implemented": self.mode in IMPLEMENTED_CANVAS_HOST_MODES,
            "taskbar_visible": self.taskbar_policy is CanvasTaskbarPolicy.RESPECT,
        }


def resolve_canvas_host_config(
    mode: str | CanvasHostMode | None = None,
    *,
    taskbar_policy: str | CanvasTaskbarPolicy | None = None,
    require_implemented: bool = True,
) -> CanvasHostConfig:
    """Normalize and validate a Canvas host launch request."""

    config = CanvasHostConfig(
        mode=normalize_canvas_host_mode(mode),
        taskbar_policy=normalize_canvas_taskbar_policy(taskbar_policy),
    )
    if require_implemented:
        ensure_canvas_host_is_implemented(config)
    return config


def ensure_canvas_host_is_implemented(config: CanvasHostConfig) -> None:
    if config.taskbar_policy is not CanvasTaskbarPolicy.RESPECT:
        raise RitualistError("Canvas taskbar policy must be 'respect'.")
    if config.mode not in IMPLEMENTED_CANVAS_HOST_MODES:
        raise RitualistError(
            "Canvas host mode "
            f"'{config.mode.value}' is documented but not implemented yet; use 'windowed'."
        )


def normalize_canvas_host_mode(mode: str | CanvasHostMode | None) -> CanvasHostMode:
    if isinstance(mode, CanvasHostMode):
        return mode
    normalized = _normalize_token(mode, default=CanvasHostMode.WINDOWED.value)
    if normalized in {"desktop_overlay", "overlay"}:
        raise RitualistError(
            "Canvas host mode 'desktop_overlay' is retired; use 'desktop_work_area' "
            "or '--host desktop-work-area' when that host is implemented."
        )
    try:
        return CanvasHostMode(normalized)
    except ValueError as exc:
        allowed = ", ".join(host.value for host in DOCUMENTED_CANVAS_HOST_MODES)
        raise RitualistError(f"Unsupported Canvas host mode '{mode}'. Allowed host modes: {allowed}.") from exc


def normalize_canvas_taskbar_policy(
    taskbar_policy: str | CanvasTaskbarPolicy | None,
) -> CanvasTaskbarPolicy:
    if isinstance(taskbar_policy, CanvasTaskbarPolicy):
        return taskbar_policy
    normalized = _normalize_token(taskbar_policy, default=CanvasTaskbarPolicy.RESPECT.value)
    if normalized in UNSUPPORTED_TASKBAR_POLICIES:
        raise RitualistError(
            "Taskbar policy "
            f"'{normalized}' is not supported; Ritualist currently only supports 'respect'."
        )
    try:
        return CanvasTaskbarPolicy(normalized)
    except ValueError as exc:
        allowed = ", ".join(policy.value for policy in CanvasTaskbarPolicy)
        raise RitualistError(
            f"Unsupported Canvas taskbar policy '{taskbar_policy}'. Allowed policies: {allowed}."
        ) from exc


def _normalize_token(value: str | None, *, default: str) -> str:
    text = str(value or "").strip().casefold()
    if not text:
        return default
    normalized = text.replace("-", "_").replace(" ", "_")
    return "_".join(part for part in normalized.split("_") if part)
