from __future__ import annotations

from ritualist.errors import UserCancelledError
from ritualist.models import ConfirmAskStep

from .base import ActionContext
from .metadata import ALL_PLATFORMS, ActionMetadata


class ConfirmAskHandler:
    action_type = "confirm.ask"
    metadata = ActionMetadata(
        action=action_type,
        schema_version="0.1",
        required_params=("prompt",),
        optional_params=("name", "optional", "timeout_seconds"),
        required_capabilities=(),
        platform_support=ALL_PLATFORMS,
        side_effect_level="read_only",
        confirmation_policy="always",
        allowed_in_imported_packs=True,
    )

    def run(self, step: ConfirmAskStep, context: ActionContext) -> str:
        if not context.confirm(step.prompt):
            raise UserCancelledError("user declined confirmation")
        return "confirmed"
