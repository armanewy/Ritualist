from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from setpiece.agent.notification_policy import (
    LONG_HIDDEN_RUN_SECONDS,
    NotificationDecision,
    NotificationEvent,
    NotificationRequest,
    NotificationUrgency,
)
from setpiece.agent.notifications import (
    AgentNotificationAction,
    AgentNotificationButton,
    AgentNotificationMessage,
    AgentNotificationRouter,
    QtTrayNotificationBackend,
    RecordingNotificationBackend,
    build_agent_notification_message,
)


def test_router_does_not_notify_startup_progress_or_short_visible_success() -> None:
    backend = RecordingNotificationBackend()
    router = AgentNotificationRouter(backend)

    requests = [
        NotificationRequest(event=NotificationEvent.STARTUP, ritual_name="Setup"),
        NotificationRequest(event=NotificationEvent.PROGRESS, ritual_name="Setup"),
        NotificationRequest(event=NotificationEvent.SUCCESS, ritual_name="Setup"),
    ]

    deliveries = [router.notify(request) for request in requests]

    assert [delivery.delivered for delivery in deliveries] == [False, False, False]
    assert backend.sent == []


def test_background_confirmation_routes_to_review_only() -> None:
    message = build_agent_notification_message(
        NotificationRequest(
            event=NotificationEvent.CONFIRMATION_REQUIRED,
            ritual_name="Deploy prep",
            decision_prompt="Review browser target",
            app_in_background=True,
        )
    )

    assert message is not None
    assert message.title == "Review needed"
    assert [(action.action, action.label) for action in message.actions] == [
        (AgentNotificationAction.REVIEW, "Review")
    ]
    assert message.default_action == AgentNotificationAction.REVIEW


def test_foreground_confirmation_stays_in_app() -> None:
    message = build_agent_notification_message(
        NotificationRequest(
            event=NotificationEvent.CONFIRMATION_REQUIRED,
            ritual_name="Deploy prep",
            decision_prompt="Review browser target",
            app_in_background=False,
        )
    )

    assert message is None


def test_background_failure_and_recovery_open_setpiece_without_mutating_actions() -> None:
    failure = build_agent_notification_message(
        NotificationRequest(
            event=NotificationEvent.FAILURE,
            ritual_name="Report prep",
            failure_reason="Could not find the app window",
            app_in_background=True,
        )
    )
    recovery = build_agent_notification_message(
        NotificationRequest(
            event=NotificationEvent.RECOVERY_INTERRUPTED,
            ritual_name="Report prep",
            recovery_reason="The run was interrupted",
        )
    )

    assert failure is not None
    assert recovery is not None
    assert [(action.action, action.label) for action in failure.actions] == [
        (AgentNotificationAction.OPEN_SETPIECE, "Open Setpiece")
    ]
    assert [(action.action, action.label) for action in recovery.actions] == [
        (AgentNotificationAction.OPEN_SETPIECE, "Open Setpiece")
    ]
    exposed_actions = {action.value for action in AgentNotificationAction}
    assert exposed_actions == {"review", "open_setpiece", "check_again"}
    assert exposed_actions.isdisjoint(
        {"approve", "approve_r2", "approve_r3", "run_ritual", "stop_ritual"}
    )


def test_foreground_failure_does_not_duplicate_visible_failure() -> None:
    message = build_agent_notification_message(
        NotificationRequest(
            event=NotificationEvent.FAILURE,
            ritual_name="Report prep",
            failure_reason="Could not find the app window",
            app_in_background=False,
        )
    )

    assert message is None


def test_long_hidden_completion_notifies_once_with_open_setpiece_action() -> None:
    backend = RecordingNotificationBackend()
    router = AgentNotificationRouter(backend)

    delivery = router.notify(
        NotificationRequest(
            event=NotificationEvent.SUCCESS,
            ritual_name="Large workspace setup",
            run_was_hidden=True,
            run_duration_seconds=LONG_HIDDEN_RUN_SECONDS,
            quiet_completion_enabled=True,
        )
    )

    assert delivery.delivered
    assert len(backend.sent) == 1
    message = backend.sent[0]
    assert message.title == "Ritual complete"
    assert message.urgency == NotificationUrgency.QUIET
    assert [(action.action, action.label) for action in message.actions] == [
        (AgentNotificationAction.OPEN_SETPIECE, "Open Setpiece")
    ]


def test_check_again_requires_explicit_policy_action() -> None:
    request = NotificationRequest(
        event=NotificationEvent.FAILURE,
        ritual_name="Report prep",
        app_in_background=True,
    )
    base = build_agent_notification_message(
        request,
        policy=lambda _request: NotificationDecision(
            should_notify=True,
            title="Check",
            body="No safe retry was offered",
            actions=("approve", "run_ritual", "stop_ritual"),
        ),
    )
    explicit = build_agent_notification_message(
        request,
        policy=lambda _request: NotificationDecision(
            should_notify=True,
            title="Check",
            body="Re-check is safe",
            actions=("check_again", "approve"),
        ),
    )

    assert base is not None
    assert base.actions == ()
    assert explicit is not None
    assert [(action.action, action.label) for action in explicit.actions] == [
        (AgentNotificationAction.CHECK_AGAIN, "Check again")
    ]


def test_router_dispatches_only_known_notification_actions() -> None:
    routed: list[AgentNotificationAction] = []
    router = AgentNotificationRouter(RecordingNotificationBackend(), on_action=routed.append)

    assert router.dispatch_action(AgentNotificationAction.REVIEW)
    assert router.dispatch_action("open_setpiece")
    assert not router.dispatch_action("run_ritual")
    assert not router.dispatch_action("stop_ritual")
    assert routed == [
        AgentNotificationAction.REVIEW,
        AgentNotificationAction.OPEN_SETPIECE,
    ]


class _Signal:
    def __init__(self) -> None:
        self._callbacks: list[object] = []

    def connect(self, callback: object) -> None:
        self._callbacks.append(callback)

    def emit(self) -> None:
        for callback in list(self._callbacks):
            callback()


class _TrayIcon:
    class MessageIcon:
        Information = "information"
        Warning = "warning"
        Critical = "critical"

    def __init__(self) -> None:
        self.messageClicked = _Signal()
        self.messages: list[tuple[object, ...]] = []

    def showMessage(self, *args: object) -> None:
        self.messages.append(args)


def test_qt_tray_backend_uses_fake_tray_without_gui_imports() -> None:
    tray_icon = _TrayIcon()
    clicked: list[AgentNotificationAction] = []
    backend = QtTrayNotificationBackend(tray_icon, on_action=clicked.append)

    backend.send(
        AgentNotificationMessage(
            title="Review needed",
            body="Deploy prep needs review",
            urgency=NotificationUrgency.REVIEW,
            duration="short",
            actions=(AgentNotificationButton(AgentNotificationAction.REVIEW, "Review"),),
            default_action=AgentNotificationAction.REVIEW,
        )
    )
    tray_icon.messageClicked.emit()

    assert tray_icon.messages == [
        ("Review needed", "Deploy prep needs review", "warning", 6000)
    ]
    assert clicked == [AgentNotificationAction.REVIEW]


def test_agent_notifications_import_without_gui_or_windows_dependencies() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    code = """
import sys
import setpiece.agent.notifications

blocked = ["PySide6", "pywinauto", "win32api", "win32gui", "win32con"]
loaded = [name for name in blocked if name in sys.modules]
if loaded:
    raise SystemExit(f"agent notifications loaded GUI/Windows modules: {loaded}")
"""

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
