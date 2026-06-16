from __future__ import annotations

from ritualist.errors import RitualistError
from ritualist.models import FlowIfStep

from .base import ActionContext
from .metadata import ALL_PLATFORMS, ActionMetadata


class FlowIfHandler:
    action_type = "flow.if"
    metadata = ActionMetadata(
        action_name=action_type,
        schema_version="0.1",
        category="flow",
        required_params=("condition",),
        optional_params=("then", "else", "name", "optional", "when"),
        required_capabilities=(),
        supported_platforms=ALL_PLATFORMS,
        side_effect_level="read_only",
        confirmation_policy="never",
        allowed_in_imported_packs=True,
    )

    def run(self, step: FlowIfStep, context: ActionContext) -> str:
        raise RitualistError("flow.if is executed by the workflow runtime")


def create_flow_handlers():
    return (FlowIfHandler(),)
