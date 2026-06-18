from __future__ import annotations

from ritualist.agent.notification_policy import (
    LONG_HIDDEN_RUN_SECONDS,
    NotificationAction,
    NotificationEvent,
    NotificationRequest,
    NotificationUrgency,
    choose_notification,
)


def test_startup_and_progress_do_not_notify() -> None:
    for event in (NotificationEvent.STARTUP, NotificationEvent.PROGRESS):
        decision = choose_notification(NotificationRequest(event=event, ritual_name="Setup"))

        assert not decision.should_notify
        assert decision.actions == ()


def test_success_is_short_and_visible() -> None:
    decision = choose_notification(
        NotificationRequest(
            event=NotificationEvent.SUCCESS,
            ritual_name="Morning setup",
        )
    )

    assert decision.should_notify
    assert decision.title == "Ritual complete"
    assert decision.body == "Morning setup finished successfully"
    assert decision.duration == "short"
    assert decision.urgency == NotificationUrgency.NORMAL


def test_background_confirmation_opens_review_without_approval_action() -> None:
    decision = choose_notification(
        NotificationRequest(
            event=NotificationEvent.CONFIRMATION_REQUIRED,
            ritual_name="Deploy prep",
            decision_prompt="Review target before continuing",
            app_in_background=True,
        )
    )

    assert decision.should_notify
    assert decision.urgency == NotificationUrgency.REVIEW
    assert decision.actions == (NotificationAction.OPEN_REVIEW,)
    assert "approve" not in {action.value for action in decision.actions}


def test_foreground_confirmation_stays_in_app() -> None:
    decision = choose_notification(
        NotificationRequest(
            event=NotificationEvent.CONFIRMATION_REQUIRED,
            ritual_name="Deploy prep",
            decision_prompt="Review target before continuing",
            app_in_background=False,
        )
    )

    assert not decision.should_notify


def test_background_failure_notifies_with_run_details_action() -> None:
    decision = choose_notification(
        NotificationRequest(
            event=NotificationEvent.FAILURE,
            ritual_name="Report prep",
            failure_reason="Could not find the app window",
            app_in_background=True,
        )
    )

    assert decision.should_notify
    assert decision.title == "Ritual failed"
    assert decision.body == "Report prep failed: Could not find the app window"
    assert decision.urgency == NotificationUrgency.FAILURE
    assert decision.actions == (NotificationAction.OPEN_RUN_DETAILS,)


def test_foreground_failure_does_not_duplicate_in_app_failure() -> None:
    decision = choose_notification(
        NotificationRequest(
            event=NotificationEvent.FAILURE,
            ritual_name="Report prep",
            failure_reason="Could not find the app window",
        )
    )

    assert not decision.should_notify


def test_interrupted_recovery_notifies() -> None:
    decision = choose_notification(
        NotificationRequest(
            event=NotificationEvent.RECOVERY_INTERRUPTED,
            ritual_name="Report prep",
            recovery_reason="The run was interrupted",
        )
    )

    assert decision.should_notify
    assert decision.title == "Recovery needed"
    assert decision.body == "Report prep needs recovery: The run was interrupted"
    assert decision.urgency == NotificationUrgency.RECOVERY


def test_long_hidden_completion_can_be_quiet() -> None:
    decision = choose_notification(
        NotificationRequest(
            event=NotificationEvent.SUCCESS,
            ritual_name="Large workspace setup",
            run_was_hidden=True,
            run_duration_seconds=LONG_HIDDEN_RUN_SECONDS,
            quiet_completion_enabled=True,
        )
    )

    assert decision.should_notify
    assert decision.duration == "short"
    assert decision.urgency == NotificationUrgency.QUIET


def test_notification_actions_do_not_include_approval() -> None:
    assert [action.value for action in NotificationAction] == [
        "open_review",
        "open_run_details",
    ]
