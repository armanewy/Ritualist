from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .models import AgentRoom, AgentRunState, AgentState
from .state import apply_runtime_event, derive_agent_state, initial_agent_state


class AgentStartKind(StrEnum):
    ATTENDED_RITUAL = "attended_ritual"
    SHORTCUT = "shortcut"


class AgentStartDecision(StrEnum):
    STARTED = "started"
    RETURN_TO_ACTIVE = "return_to_active"
    STOP_AND_SWITCH_REQUIRED = "stop_and_switch_required"


_OCCUPIED_ATTENDED_STATES = frozenset(
    {
        AgentRunState.READY,
        AgentRunState.PREFLIGHT,
        AgentRunState.RUNNING,
        AgentRunState.WAITING,
        AgentRunState.CONFIRMATION,
        AgentRunState.PAUSED,
        AgentRunState.FAILURE,
        AgentRunState.RECOVERY,
    }
)


@dataclass(frozen=True)
class AgentStartResult:
    decision: AgentStartDecision
    state: AgentState
    active_ritual_id: str = ""


class AgentRunCoordinator:
    def __init__(self, state: AgentState | None = None) -> None:
        self._state = state or initial_agent_state()

    @property
    def state(self) -> AgentState:
        return self._state

    def request_start(
        self,
        ritual_id: str,
        *,
        ritual_name: str = "",
        room: AgentRoom | None = None,
        step_count: int = 0,
        kind: AgentStartKind | str = AgentStartKind.ATTENDED_RITUAL,
    ) -> AgentStartResult:
        start_kind = AgentStartKind(kind)
        if start_kind is AgentStartKind.SHORTCUT:
            return AgentStartResult(AgentStartDecision.STARTED, self._state)

        normalized_id = ritual_id.strip()
        if self.attended_slot_occupied:
            if normalized_id == self._state.active_ritual_id:
                self._state = derive_agent_state(
                    self._state.model_copy(update={"instrument_visible": True})
                )
                return AgentStartResult(
                    AgentStartDecision.RETURN_TO_ACTIVE,
                    self._state,
                    active_ritual_id=self._state.active_ritual_id,
                )
            return AgentStartResult(
                AgentStartDecision.STOP_AND_SWITCH_REQUIRED,
                self._state,
                active_ritual_id=self._state.active_ritual_id,
            )

        self._state = derive_agent_state(
            self._state.model_copy(
                update={
                    "state": AgentRunState.READY,
                    "active_ritual_id": normalized_id,
                    "active_ritual_name": ritual_name.strip(),
                    "room": room,
                    "step_count": max(0, int(step_count or 0)),
                    "current_step": None,
                    "wait": None,
                    "pending_confirmation": None,
                    "latest_failure": None,
                    "recovery_checkpoint": None,
                    "instrument_visible": True,
                }
            )
        )
        return AgentStartResult(
            AgentStartDecision.STARTED,
            self._state,
            active_ritual_id=normalized_id,
        )

    @property
    def attended_slot_occupied(self) -> bool:
        return (
            bool(self._state.active_ritual_id)
            and self._state.state in _OCCUPIED_ATTENDED_STATES
        )

    def apply_runtime_event(self, event: Any) -> AgentState:
        self._state = apply_runtime_event(self._state, event)
        return self._state

    def hide_instrument(self) -> AgentState:
        self._state = derive_agent_state(
            self._state.model_copy(update={"instrument_visible": False})
        )
        return self._state

    def close_instrument(self) -> AgentState:
        return self.hide_instrument()

    def pin_instrument(self, pinned: bool) -> AgentState:
        self._state = derive_agent_state(
            self._state.model_copy(update={"instrument_pinned": bool(pinned)})
        )
        return self._state
