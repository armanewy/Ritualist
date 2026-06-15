from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RunState(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    WAITING = "waiting"
    PAUSED = "paused"
    CONFIRMING = "confirming"
    STOPPING = "stopping"
    SUCCESS = "success"
    STOPPED = "stopped"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class StepState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING = "waiting"
    PAUSED = "paused"
    CONFIRMING = "confirming"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


RUN_TERMINAL_STATES = frozenset(
    {RunState.SUCCESS, RunState.STOPPED, RunState.FAILED, RunState.INTERRUPTED}
)
STEP_TERMINAL_STATES = frozenset(
    {StepState.SUCCESS, StepState.FAILED, StepState.CANCELLED, StepState.SKIPPED}
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RuntimeEventBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    run_id: str
    sequence: int = Field(ge=0)
    occurred_at: datetime = Field(default_factory=_utc_now)


class RunStarted(RuntimeEventBase):
    type: Literal["run.started"] = "run.started"
    recipe_id: str
    recipe_name: str
    steps_total: int = Field(ge=0)
    dry_run: bool = False
    state: RunState = RunState.RUNNING


class RunStateChanged(RuntimeEventBase):
    type: Literal["run.state_changed"] = "run.state_changed"
    previous_state: RunState
    state: RunState
    message: str | None = None


class StepStarted(RuntimeEventBase):
    type: Literal["step.started"] = "step.started"
    step_index: int = Field(ge=1)
    step_name: str
    action: str
    state: StepState = StepState.RUNNING


class StepWaiting(RuntimeEventBase):
    type: Literal["step.waiting"] = "step.waiting"
    step_index: int = Field(ge=1)
    step_name: str
    action: str
    reason: str | None = None
    state: StepState = StepState.WAITING


class StepPaused(RuntimeEventBase):
    type: Literal["step.paused"] = "step.paused"
    step_index: int = Field(ge=1)
    step_name: str
    action: str
    reason: str | None = None
    state: StepState = StepState.PAUSED


class StepResumed(RuntimeEventBase):
    type: Literal["step.resumed"] = "step.resumed"
    step_index: int = Field(ge=1)
    step_name: str
    action: str
    previous_state: StepState = StepState.PAUSED
    state: StepState = StepState.RUNNING


class ConfirmationRequested(RuntimeEventBase):
    type: Literal["confirmation.requested"] = "confirmation.requested"
    confirmation_id: str
    step_index: int = Field(ge=1)
    step_name: str
    action: str
    prompt: str
    state: StepState = StepState.CONFIRMING


class ConfirmationResolved(RuntimeEventBase):
    type: Literal["confirmation.resolved"] = "confirmation.resolved"
    confirmation_id: str
    step_index: int = Field(ge=1)
    step_name: str
    action: str
    approved: bool
    state: StepState
    message: str | None = None


class StepFinished(RuntimeEventBase):
    type: Literal["step.finished"] = "step.finished"
    step_index: int = Field(ge=1)
    step_name: str
    action: str
    state: StepState
    message: str | None = None
    duration_seconds: float | None = Field(default=None, ge=0)

    @field_validator("state")
    @classmethod
    def validate_terminal_state(cls, value: StepState) -> StepState:
        if value not in STEP_TERMINAL_STATES:
            raise ValueError("StepFinished state must be terminal")
        return value


class RunFinished(RuntimeEventBase):
    type: Literal["run.finished"] = "run.finished"
    state: RunState
    success: bool
    message: str | None = None
    duration_seconds: float | None = Field(default=None, ge=0)

    @field_validator("state")
    @classmethod
    def validate_terminal_state(cls, value: RunState) -> RunState:
        if value not in RUN_TERMINAL_STATES:
            raise ValueError("RunFinished state must be terminal")
        return value


class LogMessage(RuntimeEventBase):
    type: Literal["log.message"] = "log.message"
    level: Literal["debug", "info", "warning", "error"]
    message: str
    step_index: int | None = Field(default=None, ge=1)


class Heartbeat(RuntimeEventBase):
    type: Literal["heartbeat"] = "heartbeat"
    run_state: RunState
    step_index: int | None = Field(default=None, ge=1)
    step_state: StepState | None = None


RuntimeEvent = Annotated[
    RunStarted
    | RunStateChanged
    | StepStarted
    | StepWaiting
    | StepPaused
    | StepResumed
    | ConfirmationRequested
    | ConfirmationResolved
    | StepFinished
    | RunFinished
    | LogMessage
    | Heartbeat,
    Field(discriminator="type"),
]

RUNTIME_EVENT_TYPES = (
    RunStarted,
    RunStateChanged,
    StepStarted,
    StepWaiting,
    StepPaused,
    StepResumed,
    ConfirmationRequested,
    ConfirmationResolved,
    StepFinished,
    RunFinished,
    LogMessage,
    Heartbeat,
)
