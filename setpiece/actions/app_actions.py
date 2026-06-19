from __future__ import annotations

from setpiece.models import AppLaunchStep, AppWaitProcessStep

from .base import ActionContext
from .metadata import ALL_PLATFORMS, ActionMetadata


class AppLaunchHandler:
    action_type = "app.launch"
    metadata = ActionMetadata(
        action_name=action_type,
        schema_version="0.1",
        category="app",
        required_params=("command",),
        optional_params=("args", "cwd", "wait", "env", "name", "optional", "timeout_seconds"),
        required_capabilities=("app_launch",),
        supported_platforms=ALL_PLATFORMS,
        side_effect_level="launches_app",
        confirmation_policy="optional",
        allowed_in_imported_packs=False,
    )

    def run(self, step: AppLaunchStep, context: ActionContext) -> str:
        context.adapters.shell.launch(
            command=step.command,
            args=step.args,
            cwd=step.cwd,
            wait=step.wait,
            env=step.env,
        )
        return f"launched {step.command}"


class AppWaitProcessHandler:
    action_type = "app.wait_process"
    metadata = ActionMetadata(
        action_name=action_type,
        schema_version="0.1",
        category="app",
        required_params=("process_name",),
        optional_params=("timeout_seconds", "name", "optional"),
        required_capabilities=("process_inspection",),
        supported_platforms=ALL_PLATFORMS,
        side_effect_level="read_only",
        confirmation_policy="never",
        allowed_in_imported_packs=True,
    )

    def run(self, step: AppWaitProcessStep, context: ActionContext) -> str:
        timeout = step.timeout_seconds or 30.0
        context.adapters.shell.wait_process(step.process_name, timeout_seconds=timeout)
        return f"found process {step.process_name}"
