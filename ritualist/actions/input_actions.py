from __future__ import annotations

from ritualist.models import InputHotkeyStep

from .base import ActionContext
from .metadata import ActionMetadata, WINDOWS_ONLY


class InputHotkeyHandler:
    action_type = "input.hotkey"
    metadata = ActionMetadata(
        action=action_type,
        schema_version="0.1",
        required_params=("keys",),
        optional_params=("name", "optional", "timeout_seconds"),
        required_capabilities=("windows_uia", "keyboard_input"),
        platform_support=WINDOWS_ONLY,
        side_effect_level="types_input",
        confirmation_policy="optional",
        allowed_in_imported_packs=False,
    )

    def run(self, step: InputHotkeyStep, context: ActionContext) -> str:
        context.adapters.input.hotkey(step.keys)
        return f"sent hotkey {'+'.join(step.keys)}"
