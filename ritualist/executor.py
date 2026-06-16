from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from .actions.base import (
    ActionOutcome,
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
from .models import (
    DesktopClickTextStep,
    ExecutableStep,
    Recipe,
    WindowMatchMixin,
    WindowTitleScopeMixin,
    WindowWaitStep,
)
from .overlay import (
    ActionPreview,
    BestEffortOverlayController,
    ConfirmationRequest,
    NullOverlayController,
    OverlayController,
    TargetRegion,
)
from .runtime_control import RuntimeControl, RuntimeStoppedError
from .runtime_models import (
    Heartbeat,
    LogMessage,
    RunFinished,
    RunStarted,
    RunState,
    RunStateChanged,
    RuntimeEvent,
    StepFinished,
    StepStarted,
    StepState,
)


RuntimeEventCallback = Callable[[RuntimeEvent], None]

WINDOW_LAYOUT_ACTIONS = {
    "window.move",
    "window.resize",
    "window.maximize",
    "window.restore",
    "window.snap_left",
    "window.snap_right",
    "window.snap_top",
    "window.snap_bottom",
}
WINDOW_PREVIEW_ACTIONS = {
    "window.focus",
    "window.minimize",
    *WINDOW_LAYOUT_ACTIONS,
}


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
        runtime_control: RuntimeControl | None = None,
        runtime_event_callback: RuntimeEventCallback | None = None,
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
        self.runtime_control = runtime_control or RuntimeControl()
        self.runtime_event_callback = runtime_event_callback
        self.strict = strict
        self.config = config or load_app_config()
        self._overlay_available = overlay is not None and not isinstance(overlay, NullOverlayController)
        self.overlay = BestEffortOverlayController(overlay or NullOverlayController())
        self._run_id: str | None = None
        self._event_sequence = 0
        self._run_started_at: datetime | None = None
        self._run_state = RunState.IDLE

    def run(self, recipe: Recipe) -> RunSummary:
        results: list[StepResult] = []
        steps = recipe.execution_steps
        total = len(steps)
        if self.run_logger is not None:
            self.run_logger.start(recipe, dry_run=self.dry_run)
        self._start_runtime_run(recipe, total)
        context = ActionContext(
            adapters=self.adapters,
            dry_run=self.dry_run,
            logger=self.logger,
            confirm=self.confirmer,
            recipe=recipe,
            config=self.config,
            overlay=self.overlay,
            runtime_control=self.runtime_control,
        )

        for index, step in enumerate(steps, start=1):
            self._heartbeat(index, step.display_name, step_state=StepState.PENDING)
            try:
                self._checkpoint_control()
            except RuntimeStoppedError as exc:
                self._change_run_state(RunState.STOPPING, message=str(exc))
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
                self._emit_step_finished(result, step)
                self._emit(index, total, step, "cancelled", result.message)
                break
            started_at = _now()
            self._start_step(index, step)
            self._emit(index, total, step, "running", step_started_at=started_at)
            status = "success"
            message = ""
            result_metadata: dict[str, Any] = {}
            dry_run_step = False

            if self.dry_run:
                status = "dry-run"
                message = _dry_run_message(step)
                dry_run_step = True
                self.logger.info("dry-run step %s/%s: %s", index, total, step.display_name)
                self._emit_log_message(
                    "info",
                    f"dry-run step {index}/{total}: {step.display_name}",
                    step_index=index,
                )
            else:
                wait_overlay = None
                try:
                    wait_overlay = self._start_wait_overlay(step)
                    preview_region = self._find_preview_region(step)
                    self._show_action_preview(step, preview_region)
                    if step.requires_confirmation:
                        prompt = self._confirmation_request(recipe, step, preview_region)
                        self._heartbeat(index, step.display_name)
                        if not self.confirmer(prompt):
                            raise UserCancelledError("user declined confirmation")

                    self._checkpoint_control()
                    handler = self.registry.get(step.action)
                    context.heartbeat = (
                        lambda step_id=index, step_name=step.display_name, active_step=step: self._heartbeat(
                            step_id,
                            step_name,
                            run_state=_active_run_state_for_step(active_step),
                            step_state=_active_step_state_for_step(active_step),
                            step=active_step,
                            step_started_at=started_at,
                        )
                    )
                    self.logger.info("starting step %s/%s: %s", index, total, step.display_name)
                    self._emit_log_message(
                        "info",
                        f"starting step {index}/{total}: {step.display_name}",
                        step_index=index,
                    )
                    outcome = handler.run(step, context)
                    message, result_metadata = _normalize_action_outcome(outcome)
                    self._checkpoint_control()
                    self.logger.info("finished step %s/%s: %s", index, total, step.display_name)
                    self._emit_log_message(
                        "info",
                        f"finished step {index}/{total}: {step.display_name}",
                        step_index=index,
                    )
                except RuntimeStoppedError as exc:
                    status = "cancelled"
                    message = str(exc)
                    self._change_run_state(RunState.STOPPING, message=message)
                except UserCancelledError as exc:
                    status = "cancelled"
                    message = str(exc)
                except Exception as exc:  # noqa: BLE001 - convert adapter failures to run results.
                    if step.optional:
                        status = "skipped"
                        message = f"optional step failed: {exc}"
                        self.logger.warning(message)
                        self._emit_log_message(
                            "warning",
                            f"optional step failed: {step.display_name}",
                            step_index=index,
                        )
                    else:
                        status = "failed"
                        message = str(exc)
                        self.logger.exception("step failed: %s", step.display_name)
                        self._emit_log_message(
                            "error",
                            f"step failed: {step.display_name}",
                            step_index=index,
                        )
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
                metadata=result_metadata,
            )
            results.append(result)
            if self.run_logger is not None:
                self.run_logger.write_step(result)
            self._emit_step_finished(result, step)
            self._emit(index, total, step, status, message, step_started_at=started_at)

            if status in {"failed", "cancelled"}:
                break

        summary = RunSummary(
            recipe_id=recipe.id,
            recipe_name=recipe.name,
            results=results,
            run_dir=getattr(self.run_logger, "run_dir", None),
        )
        final_state = _final_run_state(
            summary,
            steps_total=total,
            stop_requested=self.runtime_control.is_stopping(),
        )
        self._change_run_state(final_state, message=_run_finished_message(final_state))
        if self.run_logger is not None:
            self._finish_run_logger(summary=summary, final_state=final_state)
        self._emit_run_finished(summary, final_state)
        if self.strict and not summary.success:
            raise ExecutionStoppedError("workflow stopped before completion", results)
        return summary

    def _emit(
        self,
        index: int,
        total: int,
        step: ExecutableStep,
        status: str,
        message: str = "",
        *,
        step_started_at: datetime | None = None,
    ) -> None:
        if self.status_callback is None:
            return
        wait_fields = _wait_status_fields(step, step_started_at) if status == "running" else {}
        self.status_callback(
            StepEvent(
                index=index,
                total=total,
                step_name=step.display_name,
                action=step.action,
                status=status,
                message=message,
                keep_open_active=status == "success" and _step_requests_keep_open(step),
                **wait_fields,
            )
        )

    def _start_runtime_run(self, recipe: Recipe, steps_total: int) -> None:
        self._run_id = self._runtime_run_id(recipe)
        self._event_sequence = 0
        self._run_started_at = _now()
        self._run_state = RunState.RUNNING
        self._emit_runtime_event(
            RunStarted(
                **self._runtime_event_fields(),
                occurred_at=self._run_started_at,
                recipe_id=recipe.id,
                recipe_name=recipe.name,
                steps_total=steps_total,
                dry_run=self.dry_run,
            )
        )

    def _runtime_run_id(self, recipe: Recipe) -> str:
        run_dir = getattr(self.run_logger, "run_dir", None)
        run_dir_name = getattr(run_dir, "name", None)
        if run_dir_name:
            return str(run_dir_name)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return f"{timestamp}_{recipe.id}_{uuid.uuid4().hex[:8]}"

    def _checkpoint_control(self) -> None:
        if self.stop_requested():
            self.runtime_control.stop()
        if self.runtime_control.is_paused() and not self.runtime_control.is_stopping():
            self._change_run_state(RunState.PAUSED, message="run paused")
        self.runtime_control.wait_if_paused()
        if self._run_state == RunState.PAUSED:
            self._change_run_state(RunState.RUNNING, message="run resumed")
        if self.stop_requested():
            self.runtime_control.stop()
        self.runtime_control.raise_if_stopped()

    def _start_step(self, index: int, step: ExecutableStep) -> None:
        if self._run_state not in {RunState.RUNNING, RunState.CONFIRMING, RunState.WAITING}:
            self._change_run_state(RunState.RUNNING)
        record_step_state = getattr(self.run_logger, "record_step_state", None)
        if record_step_state is not None:
            record_step_state(
                "running",
                step_id=index,
                step_name=step.display_name,
                action=step.action,
            )
        self._emit_runtime_event(
            StepStarted(
                **self._runtime_event_fields(),
                step_index=index,
                step_name=step.display_name,
                action=step.action,
            )
        )

    def _emit_step_finished(self, result: StepResult, step: ExecutableStep) -> None:
        self._emit_runtime_event(
            StepFinished(
                **self._runtime_event_fields(),
                step_index=result.index,
                step_name=result.step_name,
                action=result.action,
                state=_runtime_step_state(result.status),
                message=_runtime_result_message(result),
                duration_seconds=_duration_seconds(result.started_at, result.ended_at),
                metadata=result.metadata,
            )
        )

    def _change_run_state(self, state: RunState, *, message: str | None = None) -> None:
        if state == self._run_state:
            return
        previous_state = self._run_state
        self._run_state = state
        self._emit_runtime_event(
            RunStateChanged(
                **self._runtime_event_fields(),
                previous_state=previous_state,
                state=state,
                message=message,
            )
        )

    def _emit_run_finished(self, summary: RunSummary, final_state: RunState) -> None:
        ended_at = _now()
        self._emit_runtime_event(
            RunFinished(
                **self._runtime_event_fields(),
                occurred_at=ended_at,
                state=final_state,
                success=summary.success,
                message=_run_finished_message(final_state),
                duration_seconds=_duration_seconds(self._run_started_at, ended_at),
            )
        )

    def _emit_log_message(
        self,
        level: str,
        message: str,
        *,
        step_index: int | None = None,
    ) -> None:
        self._emit_runtime_event(
            LogMessage(
                **self._runtime_event_fields(),
                level=level,
                message=message,
                step_index=step_index,
            )
        )

    def _heartbeat(
        self,
        step_id: int,
        step_name: str,
        *,
        run_state: RunState | None = None,
        step_state: StepState = StepState.RUNNING,
        step: ExecutableStep | None = None,
        step_started_at: datetime | None = None,
    ) -> None:
        if self.run_logger is None:
            self._emit_heartbeat(
                step_id,
                step_name=step_name,
                run_state=run_state,
                step_state=step_state,
                step=step,
                step_started_at=step_started_at,
            )
            return
        heartbeat = getattr(self.run_logger, "heartbeat", None)
        if heartbeat is not None:
            try:
                heartbeat(
                    step_id=step_id,
                    step_name=step_name,
                    run_state=(run_state or self._run_state).value,
                    step_state=step_state.value,
                )
            except TypeError:
                heartbeat(step_id=step_id, step_name=step_name)
        self._emit_heartbeat(
            step_id,
            step_name=step_name,
            run_state=run_state,
            step_state=step_state,
            step=step,
            step_started_at=step_started_at,
        )

    def _emit_heartbeat(
        self,
        step_id: int,
        *,
        step_name: str | None = None,
        run_state: RunState | None,
        step_state: StepState,
        step: ExecutableStep | None = None,
        step_started_at: datetime | None = None,
    ) -> None:
        if self._run_id is None:
            return
        wait_fields = _heartbeat_wait_fields(step, step_started_at)
        self._emit_runtime_event(
            Heartbeat(
                **self._runtime_event_fields(),
                run_state=run_state or self._run_state,
                step_index=step_id,
                step_name=step_name,
                action=getattr(step, "action", None),
                step_state=step_state,
                **wait_fields,
            )
        )

    def _runtime_event_fields(self) -> dict[str, Any]:
        if self._run_id is None:
            raise RuntimeError("runtime run id is not initialized")
        sequence = self._event_sequence
        self._event_sequence += 1
        return {"run_id": self._run_id, "sequence": sequence}

    def _emit_runtime_event(self, event: RuntimeEvent) -> None:
        if self.runtime_event_callback is not None:
            self.runtime_event_callback(event)

    def _finish_run_logger(self, *, summary: RunSummary, final_state: RunState) -> None:
        finish = getattr(self.run_logger, "finish", None)
        if finish is None:
            return
        try:
            finish(success=summary.success, final_state=final_state.value)
        except TypeError:
            finish(success=summary.success)

    def _start_wait_overlay(self, step: ExecutableStep) -> Any:
        if not self._visual_trust_enabled or not isinstance(step, WindowWaitStep):
            return None
        label = f"Waiting for {_window_match_label(step)}..."
        return self.overlay.start_wait(label)

    def _find_preview_region(self, step: ExecutableStep) -> TargetRegion | None:
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
            if step.action in WINDOW_PREVIEW_ACTIONS and isinstance(
                step, (WindowMatchMixin, WindowTitleScopeMixin)
            ):
                finder = getattr(self.adapters.window, "find_window_region", None)
                if finder is None:
                    return TargetRegion(window_title=_window_scope_label(step))
                timeout = min(step.timeout_seconds or 10.0, 2.0)
                return finder(
                    title_contains=getattr(step, "title_contains", None),
                    process_name=getattr(step, "process_name", None),
                    timeout_seconds=timeout,
                )
        except Exception as exc:  # noqa: BLE001 - preview is best-effort only.
            self.logger.debug("action preview lookup failed for %s: %s", step.display_name, exc)
            return None
        return None

    def _show_action_preview(self, step: ExecutableStep, region: TargetRegion | None) -> None:
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
        recipe: Recipe,
        step: ExecutableStep,
        region: TargetRegion | None,
    ) -> ConfirmationRequest:
        return ConfirmationRequest(
            prompt=f"Run '{step.display_name}' ({step.action})?",
            action=step.action,
            step_name=step.display_name,
            recipe_name=recipe.name,
            window_title=_confirmation_window_title(step, region),
            target_text=_confirmation_target_text(step, region),
            control_type=region.control_type if region and region.control_type else getattr(step, "control_type", None),
        )


def _deny_confirmation(prompt: ConfirmationRequest | str) -> bool:
    return False


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _duration_seconds(started_at: datetime | None, ended_at: datetime) -> float | None:
    if started_at is None:
        return None
    return max((ended_at - started_at).total_seconds(), 0.0)


def _normalize_action_outcome(outcome: str | ActionOutcome) -> tuple[str, dict[str, Any]]:
    if isinstance(outcome, ActionOutcome):
        return outcome.message, dict(outcome.metadata)
    return str(outcome), {}


def _runtime_step_state(status: str) -> StepState:
    return {
        "dry-run": StepState.SUCCESS,
        "success": StepState.SUCCESS,
        "failed": StepState.FAILED,
        "cancelled": StepState.CANCELLED,
        "skipped": StepState.SKIPPED,
    }.get(status, StepState.FAILED)


def _active_run_state_for_step(step: ExecutableStep) -> RunState:
    if _is_wait_step(step):
        return RunState.WAITING
    return RunState.RUNNING


def _active_step_state_for_step(step: ExecutableStep) -> StepState:
    if _is_wait_step(step):
        return StepState.WAITING
    return StepState.RUNNING


def _wait_status_fields(step: ExecutableStep, started_at: datetime | None) -> dict[str, Any]:
    if not _is_wait_step(step) or started_at is None:
        return {}
    return {
        "wait_action": step.action,
        "wait_target": _wait_target_label(step),
        "wait_started_at": started_at,
        "wait_elapsed_seconds": _duration_seconds(started_at, _now()),
        "wait_timeout_seconds": _wait_timeout_seconds(step),
    }


def _heartbeat_wait_fields(step: ExecutableStep | None, started_at: datetime | None) -> dict[str, Any]:
    fields = _wait_status_fields(step, started_at) if step is not None else {}
    if not fields:
        return {}
    return {
        "wait_target": fields["wait_target"],
        "wait_started_at": fields["wait_started_at"],
        "wait_elapsed_seconds": fields["wait_elapsed_seconds"],
        "wait_timeout_seconds": fields["wait_timeout_seconds"],
    }


def _is_wait_step(step: ExecutableStep) -> bool:
    return step.action == "window.wait" or step.action.startswith("wait.")


def _step_requests_keep_open(step: ExecutableStep) -> bool:
    return step.action == "browser.open" and bool(getattr(step, "keep_open", False))


def _wait_target_label(step: ExecutableStep) -> str:
    action = step.action
    if action == "wait.seconds":
        return f"{getattr(step, 'seconds', 0):g}s"
    if action == "wait.for_user":
        return str(getattr(step, "prompt", "user confirmation"))
    if action == "wait.for_file":
        return f"file {getattr(step, 'path', '')}"
    if action == "wait.for_process":
        return f"process {getattr(step, 'process_name', '')} to start"
    if action == "wait.for_process_exit":
        return f"process {getattr(step, 'process_name', '')} to exit"
    if action in {"window.wait", "wait.for_window"} and isinstance(step, WindowMatchMixin):
        return f"window {_window_match_label(step)}"
    if action == "wait.for_window_gone" and isinstance(step, WindowMatchMixin):
        return f"window {_window_match_label(step)} to close"
    return step.display_name


def _wait_timeout_seconds(step: ExecutableStep) -> float | None:
    timeout = getattr(step, "timeout_seconds", None)
    if timeout is not None:
        return float(timeout)
    if step.action == "wait.seconds":
        return float(getattr(step, "seconds", 0))
    return None


def _runtime_result_message(result: StepResult) -> str | None:
    if result.action == "browser.open":
        if result.dry_run:
            return "would open URL"
        if result.status == "success":
            return "opened URL"
        return "browser.open did not complete"
    return result.message or None


def _final_run_state(
    summary: RunSummary,
    *,
    steps_total: int,
    stop_requested: bool,
) -> RunState:
    if any(result.status == "failed" for result in summary.results):
        return RunState.FAILED
    if stop_requested or any(result.status == "cancelled" for result in summary.results):
        return RunState.STOPPED
    if len(summary.results) < steps_total:
        return RunState.STOPPED
    if summary.success:
        return RunState.SUCCESS
    return RunState.STOPPED


def _run_finished_message(state: RunState) -> str:
    if state == RunState.SUCCESS:
        return "run completed"
    if state == RunState.FAILED:
        return "run failed"
    if state == RunState.STOPPED:
        return "run stopped"
    if state == RunState.INTERRUPTED:
        return "run interrupted"
    return f"run ended with state {state.value}"


def _preview_label(step: ExecutableStep) -> str | None:
    if isinstance(step, DesktopClickTextStep):
        return f"Ritualist: clicking {step.text}"
    if step.action == "window.focus":
        return "Ritualist: focusing window"
    if step.action == "window.minimize":
        return "Ritualist: minimizing window"
    if step.action == "window.move":
        return "Ritualist: moving window"
    if step.action == "window.resize":
        return "Ritualist: resizing window"
    if step.action == "window.maximize":
        return "Ritualist: maximizing window"
    if step.action == "window.restore":
        return "Ritualist: restoring window"
    if step.action == "window.snap_left":
        return "Ritualist: snapping window left"
    if step.action == "window.snap_right":
        return "Ritualist: snapping window right"
    if step.action == "window.snap_top":
        return "Ritualist: snapping window top"
    if step.action == "window.snap_bottom":
        return "Ritualist: snapping window bottom"
    return None


def _window_match_label(step: WindowMatchMixin) -> str:
    if step.title_contains:
        return step.title_contains
    if step.process_name:
        return step.process_name
    return "window"


def _window_scope_label(step: WindowMatchMixin | WindowTitleScopeMixin) -> str:
    if isinstance(step, WindowMatchMixin):
        return _window_match_label(step)
    return step.title_contains


def _confirmation_window_title(step: ExecutableStep, region: TargetRegion | None) -> str | None:
    if region and region.window_title:
        return region.window_title
    if isinstance(step, DesktopClickTextStep):
        return step.window_title_contains
    if isinstance(step, WindowTitleScopeMixin):
        return step.title_contains
    if isinstance(step, WindowMatchMixin):
        return _window_match_label(step)
    return None


def _confirmation_target_text(step: ExecutableStep, region: TargetRegion | None) -> str | None:
    if region and region.target_text:
        return region.target_text
    if isinstance(step, DesktopClickTextStep):
        return step.text
    return None


def _dry_run_message(step: ExecutableStep) -> str:
    layout_message = _dry_run_layout_message(step)
    if layout_message is not None:
        return layout_message
    return f"would run {step.action}"


def _dry_run_layout_message(step: ExecutableStep) -> str | None:
    if step.action not in WINDOW_LAYOUT_ACTIONS or not isinstance(step, WindowTitleScopeMixin):
        return None

    title = step.title_contains
    if step.action == "window.move":
        return f"would move window '{title}' to {getattr(step, 'x')},{getattr(step, 'y')}"
    if step.action == "window.resize":
        return (
            f"would resize window '{title}' to "
            f"{getattr(step, 'width')}x{getattr(step, 'height')}"
        )
    operation = {
        "window.maximize": "maximize window",
        "window.restore": "restore window",
        "window.snap_left": "snap window left",
        "window.snap_right": "snap window right",
        "window.snap_top": "snap window top",
        "window.snap_bottom": "snap window bottom",
    }.get(step.action)
    if operation is None:
        return None
    return f"would {operation} '{title}'"
