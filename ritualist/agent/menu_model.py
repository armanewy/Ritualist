from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class MenuAction(StrEnum):
    OPEN_RITUALIST = "open_ritualist"
    SHOW_ACTIVE_RITUAL = "show_active_ritual"
    PAUSE_ACTIVE_RITUAL = "pause_active_ritual"
    RESUME_ACTIVE_RITUAL = "resume_active_ritual"
    STOP_ACTIVE_RITUAL = "stop_active_ritual"
    OPEN_CURRENT_TARGET = "open_current_target"
    VIEW_RUN_DETAILS = "view_run_details"
    OPEN_ROOMS = "open_rooms"
    OPEN_RECENT_RITUALS = "open_recent_rituals"
    OPEN_RUN_LOG = "open_run_log"
    OPEN_SETTINGS = "open_settings"
    EXIT_RITUALIST = "exit_ritualist"


@dataclass(frozen=True, slots=True)
class MenuItem:
    label: str
    action: MenuAction | None = None
    enabled: bool = True
    children: tuple["MenuItem", ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ActiveRitualMenuContext:
    ritual_name: str
    can_pause: bool = False
    can_resume: bool = False
    can_stop: bool = True
    has_current_target: bool = False


@dataclass(frozen=True, slots=True)
class TrayMenuContext:
    active_ritual: ActiveRitualMenuContext | None = None


def build_tray_menu(context: TrayMenuContext | None = None) -> tuple[MenuItem, ...]:
    context = context or TrayMenuContext()
    items = [
        MenuItem("Open Ritualist", MenuAction.OPEN_RITUALIST),
    ]

    if context.active_ritual is not None:
        items.append(
            MenuItem(
                "Active ritual...",
                children=build_active_ritual_menu(context.active_ritual),
            )
        )

    items.extend(
        [
            MenuItem("Rooms...", MenuAction.OPEN_ROOMS),
            MenuItem("Recent rituals...", MenuAction.OPEN_RECENT_RITUALS),
            MenuItem("Run log", MenuAction.OPEN_RUN_LOG),
            MenuItem("Settings", MenuAction.OPEN_SETTINGS),
            MenuItem("Exit Ritualist", MenuAction.EXIT_RITUALIST),
        ]
    )
    return tuple(items)


def build_active_ritual_menu(context: ActiveRitualMenuContext) -> tuple[MenuItem, ...]:
    items = [
        MenuItem("Show ritual", MenuAction.SHOW_ACTIVE_RITUAL),
    ]

    if context.can_resume:
        items.append(MenuItem("Resume ritual", MenuAction.RESUME_ACTIVE_RITUAL))
    elif context.can_pause:
        items.append(MenuItem("Pause ritual", MenuAction.PAUSE_ACTIVE_RITUAL))

    if context.can_stop:
        items.append(MenuItem("Stop ritual...", MenuAction.STOP_ACTIVE_RITUAL))

    if context.has_current_target:
        items.append(MenuItem("Open current target", MenuAction.OPEN_CURRENT_TARGET))

    items.append(MenuItem("View run details", MenuAction.VIEW_RUN_DETAILS))
    return tuple(items)
