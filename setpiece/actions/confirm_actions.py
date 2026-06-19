from __future__ import annotations

from setpiece.errors import UserCancelledError
from setpiece.models import ConfirmAskStep
from setpiece.overlay import ConfirmationRequest

from .base import ActionContext
from .metadata import ALL_PLATFORMS, ActionMetadata


class ConfirmAskHandler:
    action_type = "confirm.ask"
    metadata = ActionMetadata(
        action_name=action_type,
        schema_version="0.1",
        category="confirm",
        required_params=("prompt",),
        optional_params=("name", "optional", "timeout_seconds"),
        required_capabilities=(),
        supported_platforms=ALL_PLATFORMS,
        side_effect_level="read_only",
        confirmation_policy="always",
        allowed_in_imported_packs=True,
    )

    def run(self, step: ConfirmAskStep, context: ActionContext) -> str:
        request = ConfirmationRequest(
            prompt=step.prompt,
            action=step.action,
            step_name=step.display_name,
            recipe_name=context.recipe.name,
        )
        if not context.confirm(request):
            raise UserCancelledError("user declined confirmation")
        return "confirmed"
