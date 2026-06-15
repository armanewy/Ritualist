from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

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
from .config import AppConfig, load_app_config
from .errors import ExecutionStoppedError, UserCancelledError
from .models import DesktopClickTextStep, Recipe, WindowMatchMixin, WindowWaitStep, WorkflowStep
from .overlay import (
    ActionPreview,
    BestEffortOverlayController,
    ConfirmationRequest,
    NullOverlayController,
    OverlayController,
    TargetRegion,
)


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
        stop_requested: Callable[[], bool] | None = None,
        strict: bool = False,
        config: AppConfig | None = None,
        overlay: OverlayController | None = None,
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
        self.stop_requested = stop_requested or (lambda: False)
        self.strict = strict
        self.config = config or load_app_config()
        self._overlay_available = overlay is not None
        self.overlay = BestEffortOverlayController(overlay or NullOverlayController())

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
            config=self.config,
            overlay=self.overlay,
        )

        for index, step in enumerate(recipe.steps, start=1):
            if self.stop_requested():
                self._heartbeat(index, step.display_name)
                result = StepResult(
                    index=index,
                    step_name=step.display_name,
                    action=step.action,
                    status="cancelled",
                    message="run stopped by user before step",
                    started_at=_now(),
                    ended_at=_now(),
                    optional=step.optional,
                    dry_run=self.dry_run,
                )
                results.append(result)
                if self.run_logger is not None:
                    self.run_logger.write_step(result)
                self._emit(index, total, step, "cancelled", result.message)
                break
            self._heartbeat(index, step.display_name)
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
                wait_overlay = None
                try:
                    wait_overlay = self._start_wait_overlay(step)
                    preview_region = self._find_preview_region(step)
                    self._show_action_preview(step, preview_region)
                    if step.requires_confirmation:
                        prompt = self._confirmation_request(step, preview_region)
                        self._heartbeat(index, step.display_name)
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
                finally:
                    if wait_overlay is not None:
                        wait_overlay.close()

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

    def _heartbeat(self, step_id: int, step_name: str) -> None:
        if self.run_logger is None:
            return
        heartbeat = getattr(self.run_logger, "heartbeat", None)
        if heartbeat is not None:
            heartbeat(step_id=step_id, step_name=step_name)

    def _start_wait_overlay(self, step: WorkflowStep) -> Any:
        if not self._visual_trust_enabled or not isinstance(step, WindowWaitStep):
            return None
        label = f"Waiting for {_window_match_label(step)}..."
        return self.overlay.start_wait(label)

    def _find_preview_region(self, step: WorkflowStep) -> TargetRegion | None:
        if not self._visual_trust_enabled:
            return None
        try:
            if isinstance(step, DesktopClickTextStep):
                if not self.config.ui.preview_desktop_clicks:
                    return None
                finder = getattr(self.adapters.desktop, "find_text_region", None)
                if finder is None:
                    return TargetRegion(
                        window_title=step.window_title_contains,
                        target_text=step.text,
                        control_type=step.control_type,
                    )
                timeout = min(step.timeout_seconds or 10.0, 2.0)
                return finder(
                    text=step.text,
                    window_title_contains=step.window_title_contains,
                    control_type=step.control_type,
                    exact=step.exact,
                    timeout_seconds=timeout,
                )
            if step.action in {"window.focus", "window.minimize", "window.maximize"} and isinstance(
                step, WindowMatchMixin
            ):
                finder = getattr(self.adapters.window, "find_window_region", None)
                if finder is None:
                    return TargetRegion(window_title=_window_match_label(step))
                timeout = min(step.timeout_seconds or 10.0, 2.0)
                return finder(
                    title_contains=step.title_contains,
                    process_name=step.process_name,
                    timeout_seconds=timeout,
                )
        except Exception as exc:  # noqa: BLE001 - preview is best-effort only.
            self.logger.debug("action preview lookup failed for %s: %s", step.display_name, exc)
            return None
        return None

    def _show_action_preview(self, step: WorkflowStep, region: TargetRegion | None) -> None:
        if not self._visual_trust_enabled:
            return
        if isinstance(step, DesktopClickTextStep) and not self.config.ui.preview_desktop_clicks:
            return
        label = _preview_label(step)
        if label is None:
            return
        self.overlay.show_preview(
            ActionPreview(
                action=step.action,
                step_name=step.display_name,
                label=label,
                region=region,
            ),
            duration_ms=self.config.ui.overlay_duration_ms,
        )

    @property
    def _visual_trust_enabled(self) -> bool:
        return self._overlay_available and self.config.ui.show_action_overlay

    def _confirmation_request(
        self,
        step: WorkflowStep,
        region: TargetRegion | None,
    ) -> ConfirmationRequest:
        return ConfirmationRequest(
            prompt=f"Run '{step.display_name}' ({step.action})?",
            action=step.action,
            step_name=step.display_name,
            window_title=_confirmation_window_title(step, region),
            target_text=_confirmation_target_text(step, region),
            control_type=region.control_type if region and region.control_type else getattr(step, "control_type", None),
        )


def _deny_confirmation(prompt: str) -> bool:
    return False


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _preview_label(step: WorkflowStep) -> str | None:
    if isinstance(step, DesktopClickTextStep):
        return f"Ritualist: clicking {step.text}"
    if step.action == "window.focus":
        return "Ritualist: focusing window"
    if step.action == "window.minimize":
        return "Ritualist: minimizing window"
    if step.action == "window.maximize":
        return "Ritualist: maximizing window"
    return None


def _window_match_label(step: WindowMatchMixin) -> str:
    if step.title_contains:
        return step.title_contains
    if step.process_name:
        return step.process_name
    return "window"


def _confirmation_window_title(step: WorkflowStep, region: TargetRegion | None) -> str | None:
    if region and region.window_title:
        return region.window_title
    if isinstance(step, DesktopClickTextStep):
        return step.window_title_contains
    if isinstance(step, WindowMatchMixin):
        return _window_match_label(step)
    return None


def _confirmation_target_text(step: WorkflowStep, region: TargetRegion | None) -> str | None:
    if region and region.target_text:
        return region.target_text
    if isinstance(step, DesktopClickTextStep):
        return step.text
    return None
