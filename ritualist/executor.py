from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone

from .actions.base import (
    ActionContext,
    AdapterBundle,
    ConfirmationCallback,
    RunSummary,
    StatusCallback,
    StepEvent,
    StepResult,
)
from .actions.registry import ActionRegistry, create_default_registry
from .errors import ExecutionStoppedError, UserCancelledError
from .models import Recipe, WorkflowStep


class WorkflowExecutor:
    def __init__(
        self,
        *,
        registry: ActionRegistry | None = None,
        adapters: AdapterBundle | None = None,
        dry_run: bool = False,
        confirmer: ConfirmationCallback | None = None,
        status_callback: StatusCallback | None = None,
        logger: logging.Logger | None = None,
        run_logger: object | None = None,
        strict: bool = False,
    ) -> None:
        if adapters is None:
            from .adapters import create_default_adapters

            adapters = create_default_adapters()
        self.registry = registry or create_default_registry()
        self.adapters = adapters
        self.dry_run = dry_run
        self.confirmer = confirmer or _deny_confirmation
        self.status_callback = status_callback
        self.logger = logger or logging.getLogger("ritualist")
        self.run_logger = run_logger
        self.strict = strict

    def run(self, recipe: Recipe) -> RunSummary:
        results: list[StepResult] = []
        total = len(recipe.steps)
        if self.run_logger is not None:
            self.run_logger.start(recipe, dry_run=self.dry_run)
        context = ActionContext(
            adapters=self.adapters,
            dry_run=self.dry_run,
            logger=self.logger,
            confirm=self.confirmer,
            recipe=recipe,
        )

        for index, step in enumerate(recipe.steps, start=1):
            self._emit(index, total, step, "running")
            started_at = _now()
            status = "success"
            message = ""
            dry_run_step = False

            if self.dry_run:
                status = "dry-run"
                message = f"would run {step.action}"
                dry_run_step = True
                self.logger.info("dry-run step %s/%s: %s", index, total, step.display_name)
            else:
                try:
                    if step.requires_confirmation:
                        prompt = f"Run '{step.display_name}' ({step.action})?"
                        if not self.confirmer(prompt):
                            raise UserCancelledError("user declined confirmation")

                    handler = self.registry.get(step.action)
                    self.logger.info("starting step %s/%s: %s", index, total, step.display_name)
                    message = handler.run(step, context)
                    self.logger.info("finished step %s/%s: %s", index, total, step.display_name)
                except UserCancelledError as exc:
                    status = "cancelled"
                    message = str(exc)
                except Exception as exc:  # noqa: BLE001 - convert adapter failures to run results.
                    if step.optional:
                        status = "skipped"
                        message = f"optional step failed: {exc}"
                        self.logger.warning(message)
                    else:
                        status = "failed"
                        message = str(exc)
                        self.logger.exception("step failed: %s", step.display_name)

            result = StepResult(
                index=index,
                step_name=step.display_name,
                action=step.action,
                status=status,
                message=message,
                started_at=started_at,
                ended_at=_now(),
                optional=step.optional,
                dry_run=dry_run_step,
            )
            results.append(result)
            if self.run_logger is not None:
                self.run_logger.write_step(result)
            self._emit(index, total, step, status, message)

            if status in {"failed", "cancelled"}:
                break

        summary = RunSummary(
            recipe_id=recipe.id,
            recipe_name=recipe.name,
            results=results,
            run_dir=getattr(self.run_logger, "run_dir", None),
        )
        if self.run_logger is not None:
            self.run_logger.finish(success=summary.success)
        if self.strict and not summary.success:
            raise ExecutionStoppedError("workflow stopped before completion", results)
        return summary

    def _emit(
        self,
        index: int,
        total: int,
        step: WorkflowStep,
        status: str,
        message: str = "",
    ) -> None:
        if self.status_callback is None:
            return
        self.status_callback(
            StepEvent(
                index=index,
                total=total,
                step_name=step.display_name,
                action=step.action,
                status=status,
                message=message,
            )
        )


def _deny_confirmation(prompt: str) -> bool:
    return False


def _now() -> datetime:
    return datetime.now(timezone.utc)
