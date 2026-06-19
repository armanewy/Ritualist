from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TrayState(StrEnum):
    READY = "ready"
    RUNNING = "running"
    WAITING = "waiting"
    CONFIRMATION = "confirmation"
    FAILURE = "failure"
    RECOVERY = "recovery"
    PAUSED = "paused"
    STOPPED = "stopped"


class TrayAttention(StrEnum):
    NONE = "none"
    BUSY = "busy"
    NEEDS_REVIEW = "needs_review"
    ERROR = "error"
    RECOVERY = "recovery"


@dataclass(frozen=True, slots=True)
class TrayContext:
    state: TrayState
    ritual_name: str | None = None
    current_step: str | None = None
    required_decision: str | None = None
    failure_reason: str | None = None
    recovery_reason: str | None = None


@dataclass(frozen=True, slots=True)
class TrayModel:
    state: TrayState
    tooltip: str
    attention: TrayAttention = TrayAttention.NONE


def build_tray_model(context: TrayContext) -> TrayModel:
    if context.state == TrayState.READY:
        return TrayModel(
            state=context.state,
            tooltip="Setpiece is ready",
        )

    if context.state == TrayState.RUNNING:
        return TrayModel(
            state=context.state,
            tooltip=_with_step(context.ritual_name, "is running", context.current_step),
            attention=TrayAttention.BUSY,
        )

    if context.state == TrayState.WAITING:
        return TrayModel(
            state=context.state,
            tooltip=_with_step(context.ritual_name, "is waiting", context.current_step),
            attention=TrayAttention.BUSY,
        )

    if context.state == TrayState.CONFIRMATION:
        detail = _first_text(context.required_decision, context.current_step, fallback="Review needed")
        return TrayModel(
            state=context.state,
            tooltip=f"{_ritual_name(context.ritual_name)} needs review: {detail}",
            attention=TrayAttention.NEEDS_REVIEW,
        )

    if context.state == TrayState.FAILURE:
        detail = _first_text(context.failure_reason, context.current_step, fallback="Something went wrong")
        return TrayModel(
            state=context.state,
            tooltip=f"{_ritual_name(context.ritual_name)} failed: {detail}",
            attention=TrayAttention.ERROR,
        )

    if context.state == TrayState.RECOVERY:
        detail = _first_text(
            context.recovery_reason,
            context.required_decision,
            context.current_step,
            fallback="Recovery is needed",
        )
        return TrayModel(
            state=context.state,
            tooltip=f"{_ritual_name(context.ritual_name)} needs recovery: {detail}",
            attention=TrayAttention.RECOVERY,
        )

    if context.state == TrayState.PAUSED:
        return TrayModel(
            state=context.state,
            tooltip=_with_step(context.ritual_name, "is paused", context.current_step),
            attention=TrayAttention.BUSY,
        )

    if context.state == TrayState.STOPPED:
        return TrayModel(
            state=context.state,
            tooltip=_with_step(context.ritual_name, "stopped", context.current_step),
        )

    raise ValueError(f"unsupported tray state: {context.state}")


def _with_step(ritual_name: str | None, status: str, step: str | None) -> str:
    name = _ritual_name(ritual_name)
    step_text = _clean_text(step)
    if step_text:
        return f"{name} {status}: {step_text}"
    return f"{name} {status}"


def _ritual_name(ritual_name: str | None) -> str:
    return _first_text(ritual_name, fallback="Setpiece")


def _first_text(*values: str | None, fallback: str) -> str:
    for value in values:
        text = _clean_text(value)
        if text:
            return text
    return fallback


def _clean_text(value: str | None) -> str:
    return " ".join(value.split()) if value else ""
