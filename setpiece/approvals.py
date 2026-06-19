from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ConfirmationDecisionValue(str, Enum):
    ALLOW_ONCE = "allow_once"
    ALWAYS_ALLOW_LOCAL = "always_allow_local"
    CANCEL = "cancel"


@dataclass(frozen=True)
class ConfirmationDecision:
    value: ConfirmationDecisionValue

    @property
    def approved(self) -> bool:
        return self.value in {
            ConfirmationDecisionValue.ALLOW_ONCE,
            ConfirmationDecisionValue.ALWAYS_ALLOW_LOCAL,
        }

    @property
    def remember(self) -> bool:
        return self.value == ConfirmationDecisionValue.ALWAYS_ALLOW_LOCAL

    @classmethod
    def allow_once(cls) -> "ConfirmationDecision":
        return cls(ConfirmationDecisionValue.ALLOW_ONCE)

    @classmethod
    def always_allow_local(cls) -> "ConfirmationDecision":
        return cls(ConfirmationDecisionValue.ALWAYS_ALLOW_LOCAL)

    @classmethod
    def cancel(cls) -> "ConfirmationDecision":
        return cls(ConfirmationDecisionValue.CANCEL)


def normalize_confirmation_decision(value: Any) -> ConfirmationDecision:
    if isinstance(value, ConfirmationDecision):
        return value
    if isinstance(value, bool):
        return ConfirmationDecision.allow_once() if value else ConfirmationDecision.cancel()
    if isinstance(value, str):
        normalized = value.strip().casefold().replace("-", "_").replace(" ", "_")
        if normalized in {"allow", "allow_once", "yes", "y", "true", "1"}:
            return ConfirmationDecision.allow_once()
        if normalized in {
            "always",
            "always_allow",
            "always_allow_local",
            "remember",
            "remember_local",
        }:
            return ConfirmationDecision.always_allow_local()
        if normalized in {"cancel", "no", "n", "false", "0", "decline", "deny"}:
            return ConfirmationDecision.cancel()
    return ConfirmationDecision.cancel()
