from __future__ import annotations

from ritualist.models import InputHotkeyStep

from .base import ActionContext


class InputHotkeyHandler:
    action_type = "input.hotkey"

    def run(self, step: InputHotkeyStep, context: ActionContext) -> str:
        context.adapters.input.hotkey(step.keys)
        return f"sent hotkey {'+'.join(step.keys)}"
