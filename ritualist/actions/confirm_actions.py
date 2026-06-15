from __future__ import annotations

from ritualist.errors import UserCancelledError
from ritualist.models import ConfirmAskStep

from .base import ActionContext


class ConfirmAskHandler:
    action_type = "confirm.ask"

    def run(self, step: ConfirmAskStep, context: ActionContext) -> str:
        if not context.confirm(step.prompt):
            raise UserCancelledError("user declined confirmation")
        return "confirmed"
