"""Resident Agent domain models and narrow desktop adapters."""

from __future__ import annotations

from .models import (
    AgentConfirmation,
    AgentFailure,
    AgentNotificationRecommendation,
    AgentNotificationRoute,
    AgentRecoveryCheckpoint,
    AgentRoom,
    AgentState,
    AgentStep,
    AgentRunState,
    AgentWait,
)
from .run_coordinator import (
    AgentRunCoordinator,
    AgentStartDecision,
    AgentStartKind,
    AgentStartResult,
)
from .state import (
    apply_ritual_state,
    apply_runtime_event,
    derive_agent_state,
    initial_agent_state,
)

__all__ = [
    "AgentConfirmation",
    "AgentFailure",
    "AgentNotificationRecommendation",
    "AgentNotificationRoute",
    "AgentRecoveryCheckpoint",
    "AgentRoom",
    "AgentRunCoordinator",
    "AgentRunState",
    "AgentStartDecision",
    "AgentStartKind",
    "AgentStartResult",
    "AgentState",
    "AgentStep",
    "AgentWait",
    "apply_ritual_state",
    "apply_runtime_event",
    "derive_agent_state",
    "initial_agent_state",
]
