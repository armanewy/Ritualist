from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


AGENT_STATE_SCHEMA_VERSION = "setpiece.agent.state.v1"


class AgentRunState(StrEnum):
    IDLE = "idle"
    READY = "ready"
    PREFLIGHT = "preflight"
    RUNNING = "running"
    WAITING = "waiting"
    CONFIRMATION = "confirmation"
    PAUSED = "paused"
    FAILURE = "failure"
    RECOVERY = "recovery"
    COMPLETED = "completed"
    STOPPED = "stopped"
    INTERRUPTED = "interrupted"


class AgentNotificationRoute(StrEnum):
    NONE = "none"
    OPEN_INSTRUMENT = "open_instrument"
    OPEN_REVIEW = "open_review"


class AgentRoom(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = ""
    name: str = ""
    canvas_id: str = ""


class AgentStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int | None = Field(default=None, ge=1)
    name: str = ""
    action: str = ""
    state: str = ""
    message: str = ""


class AgentWait(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = ""
    target: str = ""
    started_at: datetime | None = None
    elapsed_seconds: float | None = Field(default=None, ge=0)
    timeout_seconds: float | None = Field(default=None, ge=0)


class AgentConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation_id: str = ""
    step_index: int | None = Field(default=None, ge=1)
    step_name: str = ""
    action: str = ""
    prompt: str = ""
    target: str = ""
    target_type: str = ""


class AgentFailure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = ""
    step_index: int | None = Field(default=None, ge=1)
    step_name: str = ""
    action: str = ""
    occurred_at: datetime | None = None


class AgentRecoveryCheckpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = ""
    interrupted: bool = False
    repaired_status: str = ""
    safe_next_actions: tuple[str, ...] = ()
    last_step: AgentStep | None = None


class AgentNotificationRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route: AgentNotificationRoute = AgentNotificationRoute.NONE
    reason: str = ""


class AgentState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = AGENT_STATE_SCHEMA_VERSION
    state: AgentRunState = AgentRunState.IDLE
    run_id: str = ""
    active_ritual_id: str = ""
    active_ritual_name: str = ""
    room: AgentRoom | None = None
    current_step: AgentStep | None = None
    step_count: int = Field(default=0, ge=0)
    wait: AgentWait | None = None
    pending_confirmation: AgentConfirmation | None = None
    latest_failure: AgentFailure | None = None
    recovery_checkpoint: AgentRecoveryCheckpoint | None = None
    tray_tooltip: str = "Setpiece - Ready"
    notification_recommendation: AgentNotificationRecommendation = Field(
        default_factory=AgentNotificationRecommendation
    )
    instrument_visible: bool = False
    instrument_pinned: bool = False
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_ipc_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
