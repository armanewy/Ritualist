from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


class RitualistError(Exception):
    """Base class for user-facing Ritualist errors."""


class RecipeValidationError(RitualistError):
    """Raised when a recipe file cannot be parsed or validated."""


class TemplateError(RitualistError):
    """Raised when recipe templating fails."""


class SafetyError(RitualistError):
    """Raised when a recipe asks for an unsafe or disabled action."""


class PlatformUnsupportedError(RitualistError):
    """Raised when a platform-specific adapter is used on the wrong OS."""


class DependencyMissingError(RitualistError):
    """Raised when an optional runtime dependency is missing."""


class UserCancelledError(RitualistError):
    """Raised when a user declines a confirmation prompt."""


@dataclass
class ExecutionStoppedError(RitualistError):
    """Raised by strict callers when a workflow stops before completion."""

    message: str
    results: Sequence[object]

    def __str__(self) -> str:
        return self.message
