from __future__ import annotations

from ritualist.models import AppLaunchStep, AppWaitProcessStep

from .base import ActionContext


class AppLaunchHandler:
    action_type = "app.launch"

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

    def run(self, step: AppWaitProcessStep, context: ActionContext) -> str:
        timeout = step.timeout_seconds or 30.0
        context.adapters.shell.wait_process(step.process_name, timeout_seconds=timeout)
        return f"found process {step.process_name}"
