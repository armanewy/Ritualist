from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from .notification_policy import (
    LONG_HIDDEN_RUN_SECONDS,
    NotificationAction,
    NotificationDecision,
    NotificationEvent,
    NotificationRequest,
    NotificationUrgency,
    choose_notification,
)


class AgentNotificationAction(StrEnum):
    REVIEW = "review"
    OPEN_RITUALIST = "open_ritualist"
    CHECK_AGAIN = "check_again"


NotificationPolicy = Callable[[NotificationRequest], NotificationDecision]
NotificationActionHandler = Callable[[AgentNotificationAction], None]


@dataclass(frozen=True, slots=True)
class AgentNotificationButton:
    action: AgentNotificationAction
    label: str


@dataclass(frozen=True, slots=True)
class AgentNotificationMessage:
    title: str
    body: str
    urgency: NotificationUrgency
    duration: str
    actions: tuple[AgentNotificationButton, ...] = ()
    default_action: AgentNotificationAction | None = None


@dataclass(frozen=True, slots=True)
class AgentNotificationDelivery:
    delivered: bool
    message: AgentNotificationMessage | None = None


class AgentNotificationBackend(Protocol):
    def send(self, message: AgentNotificationMessage) -> None:
        """Display a notification message."""


@dataclass
class RecordingNotificationBackend:
    sent: list[AgentNotificationMessage] = field(default_factory=list)

    def send(self, message: AgentNotificationMessage) -> None:
        self.sent.append(message)


@dataclass
class AgentNotificationRouter:
    backend: AgentNotificationBackend
    on_action: NotificationActionHandler | None = None
    policy: NotificationPolicy = choose_notification

    def notify(self, request: NotificationRequest) -> AgentNotificationDelivery:
        message = build_agent_notification_message(request, policy=self.policy)
        if message is None:
            return AgentNotificationDelivery(delivered=False)
        self.backend.send(message)
        return AgentNotificationDelivery(delivered=True, message=message)

    def dispatch_action(self, action: AgentNotificationAction | str) -> bool:
        normalized = _router_action(action)
        if normalized is None:
            return False
        if self.on_action is not None:
            self.on_action(normalized)
        return True


@dataclass
class QtTrayNotificationBackend:
    """Qt tray notification adapter.

    This adapter expects an existing QSystemTrayIcon-like object from the resident
    agent tray. It imports no Qt modules and is therefore safe to exercise with
    fakes on non-Windows test hosts.
    """

    tray_icon: Any
    on_action: NotificationActionHandler | None = None
    _message_clicked_action: AgentNotificationAction | None = field(default=None, init=False)
    _message_clicked_connected: bool = field(default=False, init=False)

    def send(self, message: AgentNotificationMessage) -> None:
        self._message_clicked_action = message.default_action
        self._connect_message_clicked()
        self._show_message(message)

    def _connect_message_clicked(self) -> None:
        if self._message_clicked_connected:
            return
        signal = getattr(self.tray_icon, "messageClicked", None)
        connect = getattr(signal, "connect", None)
        if callable(connect):
            connect(self._handle_message_clicked)
            self._message_clicked_connected = True

    def _handle_message_clicked(self, *_args: object) -> None:
        if self._message_clicked_action is None or self.on_action is None:
            return
        self.on_action(self._message_clicked_action)

    def _show_message(self, message: AgentNotificationMessage) -> None:
        show_message = getattr(self.tray_icon, "showMessage")
        icon = _qt_message_icon(self.tray_icon, message.urgency)
        duration_msecs = _duration_msecs(message.duration)
        if icon is None:
            show_message(message.title, message.body)
            return
        try:
            show_message(message.title, message.body, icon, duration_msecs)
        except TypeError:
            show_message(message.title, message.body, icon)


def build_agent_notification_message(
    request: NotificationRequest,
    *,
    policy: NotificationPolicy = choose_notification,
) -> AgentNotificationMessage | None:
    if not _request_is_notifiable(request):
        return None

    decision = policy(request)
    if not decision.should_notify:
        return None

    actions = _buttons_for_decision(decision)
    default_action = actions[0].action if actions else None
    return AgentNotificationMessage(
        title=decision.title,
        body=decision.body,
        urgency=decision.urgency,
        duration=decision.duration,
        actions=actions,
        default_action=default_action,
    )


def _request_is_notifiable(request: NotificationRequest) -> bool:
    if request.event in {NotificationEvent.STARTUP, NotificationEvent.PROGRESS}:
        return False
    if request.event == NotificationEvent.CONFIRMATION_REQUIRED:
        return request.app_in_background
    if request.event == NotificationEvent.FAILURE:
        return request.app_in_background
    if request.event == NotificationEvent.RECOVERY_INTERRUPTED:
        return True
    if request.event == NotificationEvent.SUCCESS:
        return (
            request.run_was_hidden
            and request.run_duration_seconds >= LONG_HIDDEN_RUN_SECONDS
        )
    return False


def _buttons_for_decision(
    decision: NotificationDecision,
) -> tuple[AgentNotificationButton, ...]:
    buttons: list[AgentNotificationButton] = []
    seen: set[AgentNotificationAction] = set()
    for policy_action in decision.actions:
        action = _action_from_policy(policy_action)
        if action is None or action in seen:
            continue
        buttons.append(AgentNotificationButton(action=action, label=_ACTION_LABELS[action]))
        seen.add(action)
    return tuple(buttons)


def _action_from_policy(action: object) -> AgentNotificationAction | None:
    value = str(getattr(action, "value", action))
    if value == NotificationAction.OPEN_REVIEW.value:
        return AgentNotificationAction.REVIEW
    if value == NotificationAction.OPEN_RUN_DETAILS.value:
        return AgentNotificationAction.OPEN_RITUALIST
    if value == AgentNotificationAction.CHECK_AGAIN.value:
        return AgentNotificationAction.CHECK_AGAIN
    return None


def _router_action(action: AgentNotificationAction | str) -> AgentNotificationAction | None:
    try:
        return action if isinstance(action, AgentNotificationAction) else AgentNotificationAction(action)
    except ValueError:
        return None


def _qt_message_icon(tray_icon: Any, urgency: NotificationUrgency) -> object | None:
    tray_type = type(tray_icon)
    icon_type = getattr(tray_type, "MessageIcon", tray_type)
    icon_name = "Information"
    if urgency == NotificationUrgency.FAILURE:
        icon_name = "Critical"
    elif urgency in {NotificationUrgency.RECOVERY, NotificationUrgency.REVIEW}:
        icon_name = "Warning"
    return getattr(icon_type, icon_name, getattr(tray_type, icon_name, None))


def _duration_msecs(duration: str) -> int:
    return {
        "none": 0,
        "short": 6000,
        "default": 10000,
        "long": 15000,
    }.get(duration, 10000)


_ACTION_LABELS = {
    AgentNotificationAction.REVIEW: "Review",
    AgentNotificationAction.OPEN_RITUALIST: "Open Ritualist",
    AgentNotificationAction.CHECK_AGAIN: "Check again",
}


__all__ = [
    "AgentNotificationAction",
    "AgentNotificationBackend",
    "AgentNotificationButton",
    "AgentNotificationDelivery",
    "AgentNotificationMessage",
    "AgentNotificationRouter",
    "QtTrayNotificationBackend",
    "RecordingNotificationBackend",
    "build_agent_notification_message",
]
