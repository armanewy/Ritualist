from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


class SetpieceError(Exception):
    """Base class for user-facing Setpiece errors."""


class RecipeValidationError(SetpieceError):
    """Raised when a recipe file cannot be parsed or validated."""


class TemplateError(SetpieceError):
    """Raised when recipe templating fails."""


class SafetyError(SetpieceError):
    """Raised when a recipe asks for an unsafe or disabled action."""


class PlatformUnsupportedError(SetpieceError):
    """Raised when a platform-specific adapter is used on the wrong OS."""


class DependencyMissingError(SetpieceError):
    """Raised when an optional runtime dependency is missing."""


class UserCancelledError(SetpieceError):
    """Raised when a user declines a confirmation prompt."""


@dataclass
class ExecutionStoppedError(SetpieceError):
    """Raised by strict callers when a workflow stops before completion."""

    message: str
    results: Sequence[object]

    def __str__(self) -> str:
        return self.message
