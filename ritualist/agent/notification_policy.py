from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


LONG_HIDDEN_RUN_SECONDS = 10 * 60


class NotificationEvent(StrEnum):
    STARTUP = "startup"
    PROGRESS = "progress"
    SUCCESS = "success"
    CONFIRMATION_REQUIRED = "confirmation_required"
    FAILURE = "failure"
    RECOVERY_INTERRUPTED = "recovery_interrupted"


class NotificationAction(StrEnum):
    OPEN_REVIEW = "open_review"
    OPEN_RUN_DETAILS = "open_run_details"


class NotificationUrgency(StrEnum):
    QUIET = "quiet"
    NORMAL = "normal"
    REVIEW = "review"
    FAILURE = "failure"
    RECOVERY = "recovery"


@dataclass(frozen=True, slots=True)
class NotificationRequest:
    event: NotificationEvent
    ritual_name: str | None = None
    step_name: str | None = None
    decision_prompt: str | None = None
    failure_reason: str | None = None
    recovery_reason: str | None = None
    app_in_background: bool = False
    run_was_hidden: bool = False
    run_duration_seconds: float = 0.0
    quiet_completion_enabled: bool = False


@dataclass(frozen=True, slots=True)
class NotificationDecision:
    should_notify: bool
    title: str = ""
    body: str = ""
    urgency: NotificationUrgency = NotificationUrgency.NORMAL
    duration: str = "default"
    actions: tuple[NotificationAction, ...] = field(default_factory=tuple)

    @classmethod
    def none(cls) -> "NotificationDecision":
        return cls(should_notify=False, urgency=NotificationUrgency.QUIET, duration="none")


def choose_notification(request: NotificationRequest) -> NotificationDecision:
    if request.event in {NotificationEvent.STARTUP, NotificationEvent.PROGRESS}:
        return NotificationDecision.none()

    if request.event == NotificationEvent.SUCCESS:
        return _success_notification(request)

    if request.event == NotificationEvent.CONFIRMATION_REQUIRED:
        if not request.app_in_background:
            return NotificationDecision.none()
        detail = _first_text(request.decision_prompt, request.step_name, fallback="Review this step")
        return NotificationDecision(
            should_notify=True,
            title="Review needed",
            body=f"{_ritual_name(request.ritual_name)} needs review: {detail}",
            urgency=NotificationUrgency.REVIEW,
            actions=(NotificationAction.OPEN_REVIEW,),
        )

    if request.event == NotificationEvent.FAILURE:
        if not request.app_in_background:
            return NotificationDecision.none()
        detail = _first_text(request.failure_reason, request.step_name, fallback="The run failed")
        return NotificationDecision(
            should_notify=True,
            title="Ritual failed",
            body=f"{_ritual_name(request.ritual_name)} failed: {detail}",
            urgency=NotificationUrgency.FAILURE,
            actions=(NotificationAction.OPEN_RUN_DETAILS,),
        )

    if request.event == NotificationEvent.RECOVERY_INTERRUPTED:
        detail = _first_text(
            request.recovery_reason,
            request.step_name,
            fallback="Recovery needs your attention",
        )
        return NotificationDecision(
            should_notify=True,
            title="Recovery needed",
            body=f"{_ritual_name(request.ritual_name)} needs recovery: {detail}",
            urgency=NotificationUrgency.RECOVERY,
            actions=(NotificationAction.OPEN_RUN_DETAILS,),
        )

    raise ValueError(f"unsupported notification event: {request.event}")


def _success_notification(request: NotificationRequest) -> NotificationDecision:
    quiet_completion = (
        request.quiet_completion_enabled
        and request.run_was_hidden
        and request.run_duration_seconds >= LONG_HIDDEN_RUN_SECONDS
    )
    return NotificationDecision(
        should_notify=True,
        title="Ritual complete",
        body=f"{_ritual_name(request.ritual_name)} finished successfully",
        urgency=NotificationUrgency.QUIET if quiet_completion else NotificationUrgency.NORMAL,
        duration="short",
        actions=(NotificationAction.OPEN_RUN_DETAILS,),
    )


def _ritual_name(ritual_name: str | None) -> str:
    return _first_text(ritual_name, fallback="Ritualist")


def _first_text(*values: str | None, fallback: str) -> str:
    for value in values:
        text = _clean_text(value)
        if text:
            return text
    return fallback


def _clean_text(value: str | None) -> str:
    return " ".join(value.split()) if value else ""
