from __future__ import annotations

import hashlib
import json
import logging
import re
import shlex
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .approvals import ConfirmationDecision, normalize_confirmation_decision
from .actions.base import (
    ActionOutcome,
    ActionContext,
    AdapterBundle,
    ConfirmationCallback,
    RunSummary,
    StatusCallback,
    StepEvent,
    StepResult,
    target_region_metadata,
)
from .actions.registry import ActionRegistry, create_default_registry
from .config import AppConfig, load_app_config
from .errors import ExecutionStoppedError, UserCancelledError
from .e2e import record_event
from .models import (
    BrowserClickRoleStep,
    BrowserClickTestIdStep,
    BrowserClickTextStep,
    Condition,
    DesktopClickTextStep,
    ExecutableStep,
    FlowIfStep,
    Recipe,
    WindowMatchMixin,
    WindowTitleScopeMixin,
    WindowWaitStep,
    is_risky_browser_click_target,
)
from .overlay import (
    ActionPreview,
    BestEffortOverlayController,
    ConfirmationRequest,
    NullOverlayController,
    OverlayController,
    TargetRegion,
)
from .predicates import PredicateResult, evaluate_condition
from .preferences import (
    APPROVAL_SOURCE_TRUSTS,
    RememberedApprovalScope,
    approval_matches,
    can_remember_approval,
    remember_approval,
)
from .runtime_control import RuntimeControl, RuntimeStoppedError
from .runtime_models import (
    ConfirmationRequested,
    ConfirmationResolved,
    Heartbeat,
    LogMessage,
    RunFinished,
    RunStarted,
    RunState,
    RunStateChanged,
    RuntimeEvent,
    StepFinished,
    StepPaused,
    StepResumed,
    StepStarted,
    StepState,
    StepWaiting,
)
from .run_logs import (
    CLEAN_UP_RITUALIST_OPENED,
    FAILED_REASON,
    INTERRUPTED_REASON,
    KEEP_SETUP_OPEN,
    OPEN_RUN_LOG,
    STOPPED_BY_STOP_BUTTON,
    STOPPED_USER_CANCELLED,
    STOPPED_USER_DECLINED_CONFIRMATION,
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
        approval_store_path: Path | None = None,
        approval_source_trust: str = "local_user",
        recipe_content_hash: str | None = None,
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
        self.approval_store_path = approval_store_path
        self.approval_source_trust = approval_source_trust
        self._configured_recipe_content_hash = recipe_content_hash
        self._active_recipe_content_hash: str | None = None
        self._overlay_available = overlay is not None and not isinstance(overlay, NullOverlayController)
        self.overlay = BestEffortOverlayController(overlay or NullOverlayController())
        self._run_id: str | None = None
        self._event_sequence = 0
        self._run_started_at: datetime | None = None
        self._run_state = RunState.IDLE
        self._paused_step_index: int | None = None
        self._browser_keep_open_active = False
        self._browser_used = False
        self._stopped_reason: str | None = None
        self._declined_target: dict[str, Any] | None = None
        self._ownership_ledger: list[dict[str, Any]] = []
        self._remembered_approval_applied: dict[str, Any] | None = None
        self._last_confirmation_result: dict[str, Any] | None = None

    def run(self, recipe: Recipe) -> RunSummary:
        results: list[StepResult] = []
        execution_plan = _execution_plan(recipe)
        total = _count_plan_steps(execution_plan, include_all_branches=self.dry_run)
        self._browser_keep_open_active = False
        self._browser_used = False
        self._paused_step_index = None
        self._stopped_reason = None
        self._declined_target = None
        self._ownership_ledger = []
        self._remembered_approval_applied = None
        self._last_confirmation_result = None
        self._active_recipe_content_hash = (
            self._configured_recipe_content_hash or _recipe_content_hash(recipe)
        )
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

        self._run_plan(
            execution_plan,
            context=context,
            recipe=recipe,
            results=results,
            total=total,
        )

        summary = RunSummary(
            recipe_id=recipe.id,
            recipe_name=recipe.name,
            results=results,
            run_dir=getattr(self.run_logger, "run_dir", None),
        )
        final_state = _final_run_state(
            summary,
            steps_total=len(results),
            stop_requested=self.runtime_control.is_stopping(),
        )
        self._change_run_state(final_state, message=_run_finished_message(final_state))
        self._finalize_stop_reason(summary, final_state)
        if self.run_logger is not None:
            self._finish_run_logger(summary=summary, final_state=final_state)
        self._emit_run_finished(summary, final_state)
        self._cleanup_browser_adapter()
        if self.strict and not summary.success:
            raise ExecutionStoppedError("workflow stopped before completion", results)
        return summary

    def _run_plan(
        self,
        plan: list[tuple[str, ExecutableStep]],
        *,
        context: ActionContext,
        recipe: Recipe,
        results: list[StepResult],
        total: int,
    ) -> bool:
        for phase, step in plan:
            index = len(results) + 1
            result, branch_steps, timeout_steps = self._run_single_step(
                index,
                total,
                phase,
                step,
                context=context,
                recipe=recipe,
            )
            results.append(result)
            if self.run_logger is not None:
                self.run_logger.write_step(result)
            self._emit_step_finished(result, step)
            self._emit(index, total, step, result.status, result.message, step_started_at=result.started_at)

            if branch_steps and result.status in {"success", "dry-run"}:
                branch_phase = _flow_branch_phase(phase, result.metadata)
                if not self._run_plan(
                    [(branch_phase, branch_step) for branch_step in branch_steps],
                    context=context,
                    recipe=recipe,
                    results=results,
                    total=total,
                ):
                    return False

            dry_run_timeout_path = self.dry_run and result.status == "dry-run"
            if timeout_steps and (result.status in {"failed", "skipped"} or dry_run_timeout_path):
                if not self._run_plan(
                    [(f"{phase}:on_timeout", timeout_step) for timeout_step in timeout_steps],
                    context=context,
                    recipe=recipe,
                    results=results,
                    total=total,
                ):
                    return False

            if result.status in {"failed", "cancelled"}:
                return False
        return True

    def _run_single_step(
        self,
        index: int,
        total: int,
        phase: str,
        step: ExecutableStep,
        *,
        context: ActionContext,
        recipe: Recipe,
    ) -> tuple[StepResult, list[ExecutableStep], list[ExecutableStep]]:
        self._heartbeat(index, step.display_name, step_state=StepState.PENDING)
        try:
            self._checkpoint_control()
        except RuntimeStoppedError as exc:
            self._stopped_reason = STOPPED_BY_STOP_BUTTON
            self._change_run_state(RunState.STOPPING, message=str(exc))
            result = StepResult(
                index=index,
                step_name=step.display_name,
                action=step.action,
                status="cancelled",
                message="run stopped by user before step",
                started_at=_now(),
                ended_at=_now(),
                phase=phase,
                optional=step.optional,
                dry_run=self.dry_run,
            )
            return result, [], []

        started_at = _now()
        self._start_step(index, phase, step)
        self._emit(index, total, step, "running", step_started_at=started_at)
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

        status = "success"
        message = ""
        result_metadata: dict[str, Any] = {}
        dry_run_step = False
        branch_steps: list[ExecutableStep] = []
        timeout_steps: list[ExecutableStep] = []

        try:
            condition = getattr(step, "when", None)
            if self.dry_run:
                if condition is not None:
                    result_metadata["condition"] = {
                        "evaluated": False,
                        "message": "condition is not evaluated during dry-run",
                    }
                dry_run_step = True
                if isinstance(step, FlowIfStep):
                    result_metadata["branch"] = "all"
                    branch_steps = [*step.then, *step.else_]
                    message = "would evaluate condition and dry-run possible branches"
                else:
                    message = _dry_run_message(step)
                    if condition is not None:
                        message = f"{message} if condition matches"
                    if _is_wait_step(step):
                        timeout_steps = list(getattr(step, "on_timeout", []) or [])
                status = "dry-run"
                self.logger.info("dry-run step %s/%s: %s", index, total, step.display_name)
                self._emit_log_message(
                    "info",
                    f"dry-run step {index}/{total}: {step.display_name}",
                    step_index=index,
                )
            elif condition is not None:
                condition_result = evaluate_condition(condition, context)
                result_metadata["condition"] = condition_result.to_metadata()
                if _condition_uses_browser(condition):
                    self._browser_used = True
                if not condition_result.matched:
                    status = "skipped"
                    message = f"condition not matched: {condition_result.message}"
                    return (
                        self._step_result(
                            index,
                            phase,
                            step,
                            status=status,
                            message=message,
                            started_at=started_at,
                            dry_run=dry_run_step,
                            metadata=result_metadata,
                        ),
                        [],
                        [],
                    )

            if self.dry_run:
                pass
            elif isinstance(step, FlowIfStep):
                flow_result, branch_steps = self._evaluate_flow_if(step, context)
                result_metadata["condition"] = flow_result.to_metadata()
                result_metadata["branch"] = "then" if flow_result.matched else "else"
                message = f"condition {'matched' if flow_result.matched else 'did not match'}; running {result_metadata['branch']} branch"
            else:
                wait_overlay = None
                try:
                    wait_overlay = self._start_wait_overlay(step)
                    confirmed_desktop_target: TargetRegion | None = None
                    if _requires_confirmed_desktop_target(step):
                        confirmed_desktop_target = self._resolve_confirmed_desktop_target(step)
                        result_metadata["target_resolution"] = _target_resolution_metadata(
                            confirmed_desktop_target
                        )
                        if not _is_confirmable_region(confirmed_desktop_target):
                            message = _target_unavailable_message(step)
                            raise RuntimeError(message)
                    preview_region = confirmed_desktop_target or self._find_preview_region(step)
                    self._show_action_preview(step, preview_region)
                    context.confirm = (
                        lambda prompt, step_id=index, phase_name=phase, active_step=step: self._confirm(
                            prompt,
                            step_id=step_id,
                            phase=phase_name,
                            step=active_step,
                            recipe=recipe,
                        )
                    )
                    if step.requires_confirmation:
                        prompt = self._confirmation_request(recipe, step, preview_region)
                        self._last_confirmation_result = None
                        approved = self._confirm(
                            prompt,
                            step_id=index,
                            phase=phase,
                            step=step,
                            recipe=recipe,
                        )
                        confirmation_result = self._last_confirmation_result or {}
                        result_metadata["approval"] = confirmation_result.get(
                            "approval",
                            {"status": "approved" if approved else "declined"},
                        )
                        remembered = confirmation_result.get("remembered_approval")
                        if isinstance(remembered, dict):
                            result_metadata["remembered_approval"] = remembered
                        if not approved:
                            raise UserCancelledError("user declined confirmation")

                    self._checkpoint_control()
                    handler = self.registry.get(step.action)
                    if _uses_browser_adapter(step):
                        self._browser_used = True
                    if _is_wait_step(step):
                        self._enter_waiting_step(index, phase, step, started_at=started_at)
                    self.logger.info("starting step %s/%s: %s", index, total, step.display_name)
                    self._emit_log_message(
                        "info",
                        f"starting step {index}/{total}: {step.display_name}",
                        step_index=index,
                    )
                    if _requires_confirmed_desktop_target(step):
                        outcome = self._invoke_confirmed_desktop_target(
                            step,
                            confirmed_desktop_target,
                            result_metadata=result_metadata,
                        )
                    else:
                        outcome = handler.run(step, context)
                    message, action_metadata = _normalize_action_outcome(outcome)
                    result_metadata.update(action_metadata)
                    if _step_requests_keep_open(step):
                        self._browser_keep_open_active = True
                    if status == "success":
                        self._record_owned_resource(step)
                    self._checkpoint_control()
                    self.logger.info("finished step %s/%s: %s", index, total, step.display_name)
                    self._emit_log_message(
                        "info",
                        f"finished step {index}/{total}: {step.display_name}",
                        step_index=index,
                    )
                finally:
                    if wait_overlay is not None:
                        wait_overlay.close()
                    self._clear_transient_step_metadata()
        except RuntimeStoppedError as exc:
            status = "cancelled"
            message = str(exc)
            self._stopped_reason = STOPPED_BY_STOP_BUTTON
            self._change_run_state(RunState.STOPPING, message=message)
        except UserCancelledError as exc:
            status = "cancelled"
            message = str(exc)
            self._stopped_reason = (
                STOPPED_USER_DECLINED_CONFIRMATION
                if _is_declined_confirmation_message(message)
                else STOPPED_USER_CANCELLED
            )
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
                self._stopped_reason = FAILED_REASON
                self.logger.exception("step failed: %s", step.display_name)
                self._emit_log_message(
                    "error",
                    f"step failed: {step.display_name}",
                    step_index=index,
                )
            if _is_timeout_failure(step, message):
                timeout_steps = list(getattr(step, "on_timeout", []) or [])

        return (
            self._step_result(
                index,
                phase,
                step,
                status=status,
                message=message,
                started_at=started_at,
                dry_run=dry_run_step,
                metadata=result_metadata,
            ),
            branch_steps,
            timeout_steps,
        )

    def _step_result(
        self,
        index: int,
        phase: str,
        step: ExecutableStep,
        *,
        status: str,
        message: str,
        started_at: datetime,
        dry_run: bool,
        metadata: dict[str, Any],
    ) -> StepResult:
        return StepResult(
            index=index,
            step_name=step.display_name,
            action=step.action,
            status=status,
            message=message,
            started_at=started_at,
            ended_at=_now(),
            phase=phase,
            optional=step.optional,
            dry_run=dry_run,
            metadata=metadata,
        )

    def _evaluate_flow_if(
        self,
        step: FlowIfStep,
        context: ActionContext,
    ) -> tuple[PredicateResult, list[ExecutableStep]]:
        result = evaluate_condition(step.condition, context)
        if _condition_uses_browser(step.condition):
            self._browser_used = True
        return result, list(step.then if result.matched else step.else_)

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

    def _start_step(self, index: int, phase: str, step: ExecutableStep) -> None:
        if self._run_state not in {RunState.RUNNING, RunState.CONFIRMING, RunState.WAITING}:
            self._change_run_state(RunState.RUNNING)
        record_step_state = getattr(self.run_logger, "record_step_state", None)
        if record_step_state is not None:
            record_step_state(
                "running",
                step_id=index,
                step_name=step.display_name,
                action=step.action,
                phase=phase,
            )
        self._emit_runtime_event(
            StepStarted(
                **self._runtime_event_fields(),
                step_index=index,
                step_name=step.display_name,
                action=step.action,
            )
        )

    def _enter_waiting_step(
        self,
        index: int,
        phase: str,
        step: ExecutableStep,
        *,
        started_at: datetime,
    ) -> None:
        target = _wait_target_label(step)
        timeout = _wait_timeout_seconds(step)
        metadata = {
            "action": step.action,
            "target": target,
            "timeout_seconds": timeout,
            "started_at": started_at.isoformat(),
        }
        self._change_run_state(RunState.WAITING, message=f"waiting for {target}")
        record_step_state = getattr(self.run_logger, "record_step_state", None)
        if record_step_state is not None:
            record_step_state(
                "waiting",
                step_id=index,
                step_name=step.display_name,
                action=step.action,
                phase=phase,
                metadata=metadata,
            )
        set_wait_metadata = getattr(self.run_logger, "set_wait_metadata", None)
        if set_wait_metadata is not None:
            set_wait_metadata(metadata)
        self._emit_runtime_event(
            StepWaiting(
                **self._runtime_event_fields(),
                step_index=index,
                step_name=step.display_name,
                action=step.action,
                reason="waiting",
                target=target,
                timeout_seconds=timeout,
                started_at=started_at,
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
        record_run_state = getattr(self.run_logger, "record_run_state", None)
        if record_run_state is not None:
            record_run_state(state.value, event="run.state_changed", message=message)
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
        self._sync_paused_step(
            step_id,
            step_name=step_name,
            step=step,
            step_state=step_state,
        )
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

    def _sync_paused_step(
        self,
        step_id: int,
        *,
        step_name: str,
        step: ExecutableStep | None,
        step_state: StepState,
    ) -> None:
        if self.runtime_control.is_paused() and not self.runtime_control.is_stopping():
            if self._paused_step_index == step_id:
                return
            self._paused_step_index = step_id
            self._change_run_state(RunState.PAUSED, message="run paused")
            metadata = {
                "step_id": step_id,
                "step_name": step_name,
                "action": getattr(step, "action", None),
            }
            record_step_state = getattr(self.run_logger, "record_step_state", None)
            if record_step_state is not None:
                record_step_state(
                    "paused",
                    step_id=step_id,
                    step_name=step_name,
                    action=getattr(step, "action", None),
                    metadata=metadata,
                )
            set_paused_metadata = getattr(self.run_logger, "set_paused_metadata", None)
            if set_paused_metadata is not None:
                set_paused_metadata(metadata)
            self._emit_runtime_event(
                StepPaused(
                    **self._runtime_event_fields(),
                    step_index=step_id,
                    step_name=step_name,
                    action=getattr(step, "action", "") or "",
                    reason="run paused",
                )
            )
            return

        if self._paused_step_index != step_id:
            return
        self._paused_step_index = None
        resumed_state = StepState.WAITING if step_state == StepState.WAITING else StepState.RUNNING
        record_step_state = getattr(self.run_logger, "record_step_state", None)
        if record_step_state is not None:
            record_step_state(
                resumed_state.value,
                step_id=step_id,
                step_name=step_name,
                action=getattr(step, "action", None),
            )
        set_paused_metadata = getattr(self.run_logger, "set_paused_metadata", None)
        if set_paused_metadata is not None:
            set_paused_metadata(None)
        self._emit_runtime_event(
            StepResumed(
                **self._runtime_event_fields(),
                step_index=step_id,
                step_name=step_name,
                action=getattr(step, "action", "") or "",
                state=resumed_state,
            )
        )
        self._change_run_state(
            RunState.WAITING if resumed_state == StepState.WAITING else RunState.RUNNING,
            message="run resumed",
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
        record_event("runtime.event", runtime_event=event)
        if self.runtime_event_callback is not None:
            self.runtime_event_callback(event)

    def _finish_run_logger(self, *, summary: RunSummary, final_state: RunState) -> None:
        finish = getattr(self.run_logger, "finish", None)
        if finish is None:
            return
        cleanup_offer = _cleanup_offer(
            final_state=final_state,
            stopped_reason=self._stopped_reason,
            ownership_ledger=self._ownership_ledger,
        )
        cleanup_choice = _default_cleanup_choice(cleanup_offer)
        try:
            finish(
                success=summary.success,
                final_state=final_state.value,
                final_message=_final_run_message(final_state, stopped_reason=self._stopped_reason),
                stopped_reason=self._stopped_reason,
                declined_target=self._declined_target,
                ownership_ledger=list(self._ownership_ledger),
                cleanup_offer=cleanup_offer,
                cleanup_choice=cleanup_choice,
                remembered_cleanup_preference_applied=False,
                remembered_approval_applied=self._remembered_approval_applied,
            )
        except TypeError:
            finish(success=summary.success)

    def _confirm(
        self,
        prompt: ConfirmationRequest | str,
        *,
        step_id: int,
        phase: str,
        step: ExecutableStep,
        recipe: Recipe | None = None,
    ) -> bool:
        confirmation_id = uuid.uuid4().hex
        prompt_text = _confirmation_prompt_text(prompt)
        metadata = _confirmation_metadata(prompt, step=step, confirmation_id=confirmation_id)
        remembered_scope = self._remembered_approval_scope(
            recipe=recipe,
            step=step,
            prompt=prompt,
            step_id=step_id,
            phase=phase,
        )
        remembered = self._matching_remembered_approval(remembered_scope)
        if remembered is not None:
            self._last_confirmation_result = {
                "approval": {"status": "remembered"},
                "remembered_approval": remembered,
            }
            self._remembered_approval_applied = remembered
            self._change_run_state(RunState.RUNNING, message="remembered approval applied")
            return True

        self._change_run_state(RunState.CONFIRMING, message="confirmation requested")
        record_step_state = getattr(self.run_logger, "record_step_state", None)
        if record_step_state is not None:
            record_step_state(
                "confirming",
                step_id=step_id,
                step_name=step.display_name,
                action=step.action,
                phase=phase,
                metadata=metadata,
            )
        set_confirming_metadata = getattr(self.run_logger, "set_confirming_metadata", None)
        if set_confirming_metadata is not None:
            set_confirming_metadata(metadata)
        self._emit_runtime_event(
            ConfirmationRequested(
                **self._runtime_event_fields(),
                confirmation_id=confirmation_id,
                step_index=step_id,
                step_name=step.display_name,
                action=step.action,
                prompt=prompt_text,
                target=str(
                    metadata.get("target_text")
                    or metadata.get("target_role")
                    or metadata.get("target_test_id")
                    or ""
                ),
                target_type=str(metadata.get("target_type") or ""),
            )
        )
        decision = normalize_confirmation_decision(self.confirmer(prompt))
        approved = decision.approved
        remembered_result = self._store_remembered_approval(
            remembered_scope,
            decision=decision,
        )
        self._last_confirmation_result = {
            "approval": {"status": "approved" if approved else "declined"},
        }
        if remembered_result is not None:
            self._last_confirmation_result["remembered_approval"] = remembered_result
        resolved_state = StepState.RUNNING if approved else StepState.CANCELLED
        if not approved:
            self._stopped_reason = STOPPED_USER_DECLINED_CONFIRMATION
            self._declined_target = _declined_target_metadata(metadata)
        self._emit_runtime_event(
            ConfirmationResolved(
                **self._runtime_event_fields(),
                confirmation_id=confirmation_id,
                step_index=step_id,
                step_name=step.display_name,
                action=step.action,
                approved=approved,
                state=resolved_state,
                message="approved" if approved else "declined",
            )
        )
        if set_confirming_metadata is not None:
            set_confirming_metadata(None)
        if approved:
            if record_step_state is not None:
                record_step_state(
                    "running",
                    step_id=step_id,
                    step_name=step.display_name,
                    action=step.action,
                    phase=phase,
                )
            self._change_run_state(RunState.RUNNING, message="confirmation approved")
        else:
            self._change_run_state(RunState.STOPPING, message="confirmation declined")
        return approved

    def _remembered_approval_scope(
        self,
        *,
        recipe: Recipe | None,
        step: ExecutableStep,
        prompt: ConfirmationRequest | str,
        step_id: int,
        phase: str,
    ) -> RememberedApprovalScope | None:
        if recipe is None or not isinstance(prompt, ConfirmationRequest):
            return None
        target_application = _approval_target_application(prompt)
        target_scope = str(prompt.target_scope or "").strip()
        risk_level = self._risk_level_for_step(step)
        target_identity = str(prompt.target_identity or "").strip()
        target_context = target_application or str(prompt.window_title or prompt.browser_title or "")
        if prompt.target_ambiguous:
            target_identity = target_identity or "ambiguous"
        return RememberedApprovalScope(
            recipe_or_intent_id=recipe.id,
            content_hash=self._active_recipe_content_hash or _recipe_content_hash(recipe),
            step_id=f"{phase}:{step_id}",
            action_or_primitive_id=step.action,
            resolved_target_identity=target_identity,
            target_context=target_context,
            target_text=str(prompt.target_text or ""),
            target_control=str(prompt.control_type or ""),
            target_role=str(prompt.target_role or ""),
            target_test_id=str(prompt.target_test_id or ""),
            target_scope=target_scope,
            target_application=target_application,
            risk_level=risk_level,
            target_ambiguous=bool(prompt.target_ambiguous),
            source_trust=self.approval_source_trust,
        )

    def _matching_remembered_approval(
        self,
        scope: RememberedApprovalScope | None,
    ) -> dict[str, Any] | None:
        if scope is None or not self.config.approvals.remembered_approvals_enabled:
            return None
        if not approval_matches(
            scope,
            path=self.approval_store_path,
            local_user_approved_source=self.approval_source_trust in APPROVAL_SOURCE_TRUSTS,
        ):
            return None
        return {
            "status": "applied",
            "scope": _approval_scope_summary(scope),
        }

    def _store_remembered_approval(
        self,
        scope: RememberedApprovalScope | None,
        *,
        decision: ConfirmationDecision,
    ) -> dict[str, Any] | None:
        if not decision.approved or not decision.remember:
            return None
        if not self.config.approvals.remembered_approvals_enabled:
            return {"status": "not_stored", "reason": "remembered approvals disabled"}
        if scope is None:
            return {"status": "not_stored", "reason": "confirmation is not target scoped"}
        if not can_remember_approval(scope):
            return {"status": "not_stored", "reason": "approval scope is not rememberable"}
        entry = remember_approval(scope, path=self.approval_store_path)
        return {
            "status": "stored",
            "approval_id": str(entry.get("id") or ""),
            "scope": _approval_scope_summary(scope),
        }

    def _risk_level_for_step(self, step: ExecutableStep) -> str:
        try:
            return self.registry.metadata(step.action).side_effect_level
        except KeyError:
            return "unknown"

    def _record_owned_resource(self, step: ExecutableStep) -> None:
        item = _owned_resource_for_step(step, keep_open_active=self._browser_keep_open_active)
        if item is None:
            return
        self._ownership_ledger.append(item)

    def _finalize_stop_reason(self, summary: RunSummary, final_state: RunState) -> None:
        if final_state == RunState.FAILED:
            self._stopped_reason = FAILED_REASON
            return
        if final_state == RunState.INTERRUPTED:
            self._stopped_reason = INTERRUPTED_REASON
            return
        if final_state != RunState.STOPPED:
            return
        if self._stopped_reason is not None:
            return
        if self.runtime_control.is_stopping():
            self._stopped_reason = STOPPED_BY_STOP_BUTTON
            return
        if any(_is_declined_confirmation_message(result.message) for result in summary.results):
            self._stopped_reason = STOPPED_USER_DECLINED_CONFIRMATION
            return
        self._stopped_reason = STOPPED_USER_CANCELLED

    def _clear_transient_step_metadata(self) -> None:
        metadata = getattr(self.run_logger, "_metadata", {}) if self.run_logger is not None else {}
        set_wait_metadata = getattr(self.run_logger, "set_wait_metadata", None)
        if set_wait_metadata is not None and metadata.get("wait_metadata") is not None:
            set_wait_metadata(None)
        set_paused_metadata = getattr(self.run_logger, "set_paused_metadata", None)
        if set_paused_metadata is not None and metadata.get("paused_metadata") is not None:
            set_paused_metadata(None)

    def _cleanup_browser_adapter(self) -> None:
        if self.dry_run or self._browser_keep_open_active or not self._browser_used:
            return
        self.close_browser_state()

    def close_browser_state(self) -> bool:
        close = getattr(getattr(self.adapters, "browser", None), "close", None)
        if close is None:
            return False
        try:
            close()
        except Exception as exc:  # noqa: BLE001 - cleanup must not mask run results.
            self.logger.debug("browser adapter cleanup failed: %s", exc)
            return False
        self._browser_keep_open_active = False
        self._browser_used = False
        return True

    def _resolve_confirmed_desktop_target(self, step: ExecutableStep) -> TargetRegion | None:
        if not isinstance(step, DesktopClickTextStep):
            return None
        finder = getattr(self.adapters.desktop, "find_text_region", None)
        if finder is None:
            return None
        return finder(
            text=step.text,
            window_title_contains=step.window_title_contains,
            control_type=step.control_type,
            exact=step.exact,
            timeout_seconds=step.timeout_seconds or 10.0,
        )

    def _invoke_confirmed_desktop_target(
        self,
        step: ExecutableStep,
        target: TargetRegion | None,
        *,
        result_metadata: dict[str, Any],
    ) -> ActionOutcome:
        if not isinstance(step, DesktopClickTextStep):
            raise RuntimeError("confirmed desktop target invocation requires desktop.click_text")
        if not _is_confirmable_region(target):
            raise RuntimeError(_target_unavailable_message(step))
        invoker = getattr(self.adapters.desktop, "invoke_resolved_text_region", None)
        if invoker is None:
            raise RuntimeError("desktop adapter cannot invoke a resolved target safely")
        try:
            region = invoker(
                target=target,
                text=step.text,
                window_title_contains=step.window_title_contains,
                control_type=step.control_type,
                exact=step.exact,
                button=step.button,
                timeout_seconds=step.timeout_seconds or 10.0,
            )
        except Exception as exc:  # noqa: BLE001 - preserve failure evidence on the step.
            result_metadata["target_invocation"] = {
                "status": "failed",
                "message": str(exc),
                "target": _target_evidence_metadata(target),
            }
            raise
        result_metadata["target_invocation"] = {
            "status": "invoked",
            "target": _target_evidence_metadata(region),
        }
        return ActionOutcome(
            message=f"invoked resolved target '{step.text}'",
            metadata=target_region_metadata(region),
        )

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
        browser_context = self._browser_confirmation_context(step)
        return ConfirmationRequest(
            prompt=_confirmation_outcome_label(recipe, step, region),
            action=step.action,
            step_name=step.display_name,
            recipe_name=recipe.name,
            target_scope=_confirmation_target_scope(step),
            target_type=_confirmation_target_type(step),
            window_title=_confirmation_window_title(step, region),
            browser_title=browser_context.get("title"),
            browser_url=browser_context.get("url"),
            target_text=_confirmation_target_text(step, region),
            target_role=_confirmation_target_role(step),
            target_test_id=_confirmation_target_test_id(step),
            target_identity=region.target_identity if region else None,
            target_ambiguous=bool(region.ambiguous) if region else False,
            control_type=region.control_type if region and region.control_type else getattr(step, "control_type", None),
            target_rect=region.rect if region else None,
            safety_message=_confirmation_safety_message(step),
        )

    def _browser_confirmation_context(self, step: ExecutableStep) -> dict[str, str]:
        if not _is_browser_click_step(step):
            return {}
        page_context = getattr(self.adapters.browser, "page_context", None)
        if page_context is None:
            return {}
        try:
            raw = page_context()
        except Exception as exc:  # noqa: BLE001 - context must not break confirmation safety.
            self.logger.debug("browser confirmation context unavailable: %s", exc)
            return {}
        if not isinstance(raw, dict):
            return {}
        title = str(raw.get("title") or "").strip()
        url = _redact_url(str(raw.get("url") or "").strip())
        return {key: value for key, value in {"title": title, "url": url}.items() if value}


def _deny_confirmation(prompt: ConfirmationRequest | str) -> bool:
    return False


def _execution_plan(recipe: Recipe) -> list[tuple[str, ExecutableStep]]:
    return [
        *[("preflight", step) for step in recipe.preflight],
        *[("steps", step) for step in recipe.steps],
        *[("verify", step) for step in recipe.verify],
    ]


def _count_plan_steps(
    plan: list[tuple[str, ExecutableStep]],
    *,
    include_all_branches: bool = False,
) -> int:
    return sum(_count_step(step, include_all_branches=include_all_branches) for _phase, step in plan)


def _count_step(step: ExecutableStep, *, include_all_branches: bool = False) -> int:
    count = 1
    if isinstance(step, FlowIfStep):
        then_count = sum(
            _count_step(child, include_all_branches=include_all_branches)
            for child in step.then
        )
        else_count = sum(
            _count_step(child, include_all_branches=include_all_branches)
            for child in step.else_
        )
        count += then_count + else_count if include_all_branches else max(then_count, else_count)
    timeout_steps = getattr(step, "on_timeout", None) or []
    count += sum(
        _count_step(child, include_all_branches=include_all_branches)
        for child in timeout_steps
    )
    return count


def _flow_branch_phase(phase: str, metadata: dict[str, Any]) -> str:
    branch = metadata.get("branch")
    if branch in {"then", "else"}:
        return f"{phase}:{branch}"
    return phase


def _is_timeout_failure(step: ExecutableStep, message: str) -> bool:
    return _is_wait_step(step) and "timed out" in message.casefold()


def _condition_uses_browser(condition: Condition) -> bool:
    if condition.type == "browser.text_visible":
        return True
    if condition.all is not None:
        return any(_condition_uses_browser(child) for child in condition.all)
    if condition.any is not None:
        return any(_condition_uses_browser(child) for child in condition.any)
    if condition.not_ is not None:
        return _condition_uses_browser(condition.not_)
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


def _requires_confirmed_desktop_target(step: ExecutableStep) -> bool:
    return isinstance(step, DesktopClickTextStep) and bool(step.requires_confirmation)


def _is_confirmable_region(region: TargetRegion | None) -> bool:
    if region is None:
        return False
    if region.ambiguous:
        return False
    if not region.target_identity:
        return False
    if region.visible is False or region.enabled is False:
        return False
    return True


def _target_unavailable_message(step: ExecutableStep) -> str:
    if isinstance(step, DesktopClickTextStep):
        return (
            "target unavailable or blocked before confirmation: visible enabled text "
            f"'{step.text}' was not resolved in window '{step.window_title_contains}'"
        )
    return "target unavailable or blocked before confirmation"


def _target_resolution_metadata(region: TargetRegion | None) -> dict[str, Any]:
    if region is None:
        return {"status": "unresolved", "target": None}
    status = "resolved" if _is_confirmable_region(region) else "blocked"
    return {"status": status, "target": _target_evidence_metadata(region)}


def _target_evidence_metadata(region: TargetRegion | None) -> dict[str, Any] | None:
    if region is None:
        return None
    payload: dict[str, Any] = {}
    if region.window_title:
        payload["window_title"] = region.window_title
    if region.target_text:
        payload["target_text"] = region.target_text
    if region.control_type:
        payload["control_type"] = region.control_type
    if region.target_identity:
        payload["target_identity"] = region.target_identity
    if region.ambiguous:
        payload["ambiguous"] = True
    if region.visible is not None:
        payload["visible"] = region.visible
    if region.enabled is not None:
        payload["enabled"] = region.enabled
    if region.rect is not None and region.rect.is_valid:
        payload["bounds"] = {
            "x": region.rect.x,
            "y": region.rect.y,
            "width": region.rect.width,
            "height": region.rect.height,
        }
    return payload


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
    return (
        step.action == "window.wait"
        or step.action == "target.wait_state"
        or step.action.startswith("wait.")
        or step.action
        in {
            "browser.wait_text",
            "browser.wait_media_playing",
            "browser.wait_title",
            "browser.wait_url",
            "browser.element_visible",
        }
    )


def _step_requests_keep_open(step: ExecutableStep) -> bool:
    return step.action == "browser.open" and bool(getattr(step, "keep_open", False))


def _uses_browser_adapter(step: ExecutableStep) -> bool:
    return step.action in {
        "browser.open",
        "browser.media",
        "browser.wait_media_playing",
        "browser.wait_text",
        "browser.wait_title",
        "browser.wait_url",
        "browser.element_visible",
        "browser.click_text",
        "browser.click_role",
        "browser.click_test_id",
        "assert.browser_text_visible",
    }


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
    if action == "browser.wait_text":
        return f"browser text {getattr(step, 'text', '')}"
    if action == "browser.wait_media_playing":
        return f"browser media {getattr(step, 'selector', '')} playing"
    if action == "browser.wait_title":
        return f"browser title {getattr(step, 'title', None) or getattr(step, 'title_contains', '')}"
    if action == "browser.wait_url":
        return f"browser URL {getattr(step, 'url', None) or getattr(step, 'url_contains', '')}"
    if action == "browser.element_visible":
        return f"browser element {_browser_element_label(step)}"
    if action == "target.wait_state":
        return f"target {getattr(step, 'target', '')} state"
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
    if result.action == "browser.open_native":
        if result.dry_run:
            return "would hand off URL"
        if result.status == "success":
            return "handed URL to default browser"
        return "browser.open_native did not complete"
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


def _final_run_message(state: RunState, *, stopped_reason: str | None) -> str:
    if stopped_reason == STOPPED_USER_DECLINED_CONFIRMATION:
        return "Confirmation declined; completed setup may remain open. No confirmed risky action was performed."
    if stopped_reason == STOPPED_BY_STOP_BUTTON:
        return "Run stopped by user; setup remains open unless cleanup is chosen."
    if stopped_reason == STOPPED_USER_CANCELLED:
        return "Run cancelled by user; setup remains open unless cleanup is chosen."
    if stopped_reason == FAILED_REASON:
        return "Run failed; setup remains open for inspection."
    if stopped_reason == INTERRUPTED_REASON:
        return "Ritualist exited before finalizing this run."
    if state == RunState.SUCCESS:
        return "Run completed."
    if state == RunState.STOPPED:
        return "Run stopped."
    return _run_finished_message(state)


def _is_declined_confirmation_message(message: str | None) -> bool:
    text = str(message or "").casefold()
    return "declined confirmation" in text or "confirmation declined" in text


def _owned_resource_for_step(step: ExecutableStep, *, keep_open_active: bool) -> dict[str, Any] | None:
    if step.action == "browser.open":
        cleanup_available = bool(getattr(step, "keep_open", False))
        return {
            "kind": "browser",
            "description": "Ritualist-managed browser page/window opened",
            "owned_by_ritual": True,
            "cleanup_available": cleanup_available,
            "cleanup_action": "close_browser",
            "cleanup_risk": "low",
        }
    if step.action == "browser.media":
        return {
            "kind": "media",
            "description": "Ritualist-started browser media",
            "owned_by_ritual": True,
            "cleanup_available": keep_open_active,
            "cleanup_action": "pause_media",
            "cleanup_risk": "low",
        }
    if step.action == "app.launch":
        return {
            "kind": "app",
            "description": f"App launched by Ritualist: {_safe_command_label(getattr(step, 'command', ''))}",
            "owned_by_ritual": True,
            "cleanup_available": False,
            "cleanup_action": "manual_review",
            "cleanup_risk": "medium",
        }
    if step.action in WINDOW_LAYOUT_ACTIONS:
        return {
            "kind": "window_layout",
            "description": f"Window layout changed by Ritualist: {step.action}",
            "owned_by_ritual": True,
            "cleanup_available": False,
            "cleanup_action": "manual_restore",
            "cleanup_risk": "medium",
        }
    return None


def _safe_command_label(command: object) -> str:
    raw = str(command or "").strip()
    if not raw:
        return "unknown app"
    try:
        first = shlex.split(raw, posix=False)[0]
    except (ValueError, IndexError):
        first = raw.split(maxsplit=1)[0] if raw.split() else ""
    first = first.strip().strip("\"'")
    if not first:
        return "app command"
    parsed = urlsplit(first)
    if parsed.scheme and parsed.netloc:
        return "app URL"
    basename = first.replace("\\", "/").split("/")[-1].strip()
    if not basename or _looks_like_sensitive_fragment(basename):
        return "app command"
    return basename


def _looks_like_sensitive_fragment(value: str) -> bool:
    text = value.casefold()
    if any(token in text for token in ("token", "secret", "password", "passwd", "apikey", "api_key")):
        return True
    return bool(re.search(r"[?&#=]", value))


def _cleanup_offer(
    *,
    final_state: RunState,
    stopped_reason: str | None,
    ownership_ledger: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if final_state not in {RunState.STOPPED, RunState.FAILED}:
        return None
    safe_cleanup_items = [
        item
        for item in ownership_ledger
        if item.get("owned_by_ritual")
        and item.get("cleanup_available")
        and item.get("cleanup_risk") == "low"
    ]
    options = [
        {
            "id": KEEP_SETUP_OPEN,
            "label": "Keep setup open",
            "default": True,
        },
        {
            "id": CLEAN_UP_RITUALIST_OPENED,
            "label": "Clean up things Ritualist opened",
            "default": False,
            "available": bool(safe_cleanup_items),
            "items": safe_cleanup_items,
        },
        {
            "id": OPEN_RUN_LOG,
            "label": "Open run log",
            "default": False,
        },
    ]
    return {
        "reason": stopped_reason,
        "default": KEEP_SETUP_OPEN,
        "options": options,
        "message": "Choose cleanup after the stop; Ritualist will not claim to undo irreversible changes.",
    }


def _default_cleanup_choice(cleanup_offer: dict[str, Any] | None) -> dict[str, Any] | None:
    if cleanup_offer is None:
        return None
    return {
        "choice": KEEP_SETUP_OPEN,
        "applied": False,
        "remembered": False,
    }


def _declined_target_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in metadata.items()
        if key
        in {
            "confirmation_id",
            "action",
            "step_name",
            "target_scope",
            "target_type",
            "window_title",
            "browser_title",
            "browser_url",
            "target_text",
            "target_role",
            "target_test_id",
            "control_type",
        }
        and value
    }


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


def _confirmation_target_scope(step: ExecutableStep) -> str | None:
    if isinstance(step, DesktopClickTextStep):
        return "desktop"
    if _is_browser_click_step(step):
        return "browser"
    if step.action.startswith("input."):
        return "input"
    if step.action.startswith("window."):
        return "window"
    return None


def _confirmation_target_type(step: ExecutableStep) -> str | None:
    if isinstance(step, DesktopClickTextStep):
        return "text"
    if isinstance(step, BrowserClickTextStep):
        return "text"
    if isinstance(step, BrowserClickRoleStep):
        return "role"
    if isinstance(step, BrowserClickTestIdStep):
        return "test_id"
    if step.action.startswith("window."):
        return "window"
    if step.action.startswith("input."):
        return "keyboard"
    return None


def _confirmation_target_text(step: ExecutableStep, region: TargetRegion | None) -> str | None:
    if region and region.target_text:
        return region.target_text
    if isinstance(step, DesktopClickTextStep):
        return step.text
    if isinstance(step, BrowserClickTextStep):
        return step.text
    if isinstance(step, BrowserClickRoleStep):
        return step.accessible_name
    if isinstance(step, BrowserClickTestIdStep):
        return step.test_id
    return None


def _confirmation_target_role(step: ExecutableStep) -> str | None:
    if isinstance(step, BrowserClickRoleStep):
        return step.role
    return None


def _confirmation_target_test_id(step: ExecutableStep) -> str | None:
    if isinstance(step, BrowserClickTestIdStep):
        return step.test_id
    return None


def _confirmation_safety_message(step: ExecutableStep) -> str | None:
    if isinstance(step, DesktopClickTextStep) and step.text.strip().casefold() == "play":
        return "Clicking visible text exactly equal to Play requires explicit confirmation."
    browser_target = _browser_click_target(step)
    if browser_target is not None and is_risky_browser_click_target(browser_target):
        return f"Clicking browser target '{browser_target.strip()}' requires explicit confirmation."
    if getattr(step, "requires_confirmation", False):
        return "This step requires explicit confirmation before Ritualist continues."
    return None


def _confirmation_outcome_label(
    recipe: Recipe,
    step: ExecutableStep,
    region: TargetRegion | None,
) -> str:
    if isinstance(step, DesktopClickTextStep):
        target_text = (region.target_text if region and region.target_text else step.text).strip()
        if target_text.casefold() == "play":
            subject = _confirmation_subject_from_recipe(recipe)
            if subject:
                return f"Start {subject}"
        if target_text:
            return f"{target_text} in {_confirmation_window_title(step, region) or 'desktop window'}"
    browser_target = _browser_click_target(step)
    if browser_target:
        return f"{browser_target.strip()} in browser"
    return f"Run '{step.display_name}' ({step.action})?"


def _confirmation_subject_from_recipe(recipe: Recipe) -> str:
    title = recipe.home.card.title.strip()
    if title:
        return _trim_session_words(title)
    name = recipe.name.strip()
    return _trim_session_words(name)


def _trim_session_words(value: str) -> str:
    cleaned = re.sub(r"\s+(night|mode|setup|placeholder)$", "", value.strip(), flags=re.IGNORECASE)
    return cleaned or value.strip()


def _confirmation_prompt_text(prompt: ConfirmationRequest | str) -> str:
    if isinstance(prompt, ConfirmationRequest):
        return prompt.prompt
    return str(prompt)


def _confirmation_metadata(
    prompt: ConfirmationRequest | str,
    *,
    step: ExecutableStep,
    confirmation_id: str,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "confirmation_id": confirmation_id,
        "action": getattr(prompt, "action", None) or step.action,
    }
    request_fields = (
        ("step_name", getattr(prompt, "step_name", None)),
        ("recipe_name", getattr(prompt, "recipe_name", None)),
        ("target_scope", getattr(prompt, "target_scope", None)),
        ("target_type", getattr(prompt, "target_type", None)),
        ("window_title", getattr(prompt, "window_title", None)),
        ("browser_title", getattr(prompt, "browser_title", None)),
        ("browser_url", getattr(prompt, "browser_url", None)),
        ("target_text", getattr(prompt, "target_text", None)),
        ("target_role", getattr(prompt, "target_role", None)),
        ("target_test_id", getattr(prompt, "target_test_id", None)),
        ("target_identity", getattr(prompt, "target_identity", None)),
        ("control_type", getattr(prompt, "control_type", None)),
    )
    for key, value in request_fields:
        if value:
            metadata[key] = value
    if getattr(prompt, "target_ambiguous", False):
        metadata["target_ambiguous"] = True
    return metadata


def _recipe_content_hash(recipe: Recipe) -> str:
    payload = recipe.model_dump(mode="json")
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _approval_target_application(prompt: ConfirmationRequest) -> str:
    if prompt.window_title:
        return prompt.window_title
    if prompt.browser_url:
        return prompt.browser_url
    if prompt.browser_title:
        return prompt.browser_title
    return str(prompt.target_scope or "")


def _approval_scope_summary(scope: RememberedApprovalScope) -> dict[str, str]:
    data = scope.to_dict()
    keys = (
        "recipe_or_intent_id",
        "content_hash",
        "step_id",
        "action_or_primitive_id",
        "target_scope",
        "target_application",
        "target_text",
        "target_control",
        "target_role",
        "target_test_id",
        "risk_level",
        "local_user",
        "local_device",
        "source_trust",
    )
    return {key: data[key] for key in keys if data.get(key)}


def _dry_run_message(step: ExecutableStep) -> str:
    if step.action == "browser.open":
        options = []
        if getattr(step, "clean_start", False):
            options.append("clean start")
        if getattr(step, "dismiss_restore_prompt", False):
            options.append("safe restore prompt handling")
        if getattr(step, "use_dedicated_profile", True):
            options.append(f"managed profile '{getattr(step, 'profile', 'default')}'")
        suffix = f" ({', '.join(options)})" if options else ""
        return f"would open browser URL{suffix}"
    if step.action == "browser.open_native":
        return "would hand off URL to default browser"
    if step.action == "target.inspect":
        return f"would inspect target {getattr(step, 'target', '')}"
    if step.action == "target.wait_state":
        return f"would wait for target {getattr(step, 'target', '')} state"
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


def _browser_click_target(step: ExecutableStep) -> str | None:
    if isinstance(step, BrowserClickTextStep):
        return step.text
    if isinstance(step, BrowserClickRoleStep):
        return step.accessible_name
    if isinstance(step, BrowserClickTestIdStep):
        return step.test_id
    return None


def _is_browser_click_step(step: ExecutableStep) -> bool:
    return isinstance(step, (BrowserClickTextStep, BrowserClickRoleStep, BrowserClickTestIdStep))


def _browser_element_label(step: ExecutableStep) -> str:
    text = getattr(step, "text", None)
    if text:
        return f"text {text}"
    role = getattr(step, "role", None)
    if role:
        return f"role {role} named {getattr(step, 'accessible_name', '')}"
    return f"test id {getattr(step, 'test_id', '')}"


def _redact_url(raw_url: str) -> str:
    if not raw_url:
        return ""
    try:
        parts = urlsplit(raw_url)
    except ValueError:
        return "[unavailable]"
    if not parts.scheme or not parts.netloc:
        return raw_url.split("?", 1)[0].split("#", 1)[0]
    try:
        port = parts.port
    except ValueError:
        return "[unavailable]"
    hostname = parts.hostname
    if not hostname:
        return "[unavailable]"
    host = f"[{hostname}]" if ":" in hostname and not hostname.startswith("[") else hostname
    netloc = f"{host}:{port}" if port is not None else host
    return urlunsplit((parts.scheme, netloc, _safe_url_path(parts.path), "", ""))


def _safe_url_path(path: str) -> str:
    lowered = path.casefold()
    sensitive_markers = ("token", "secret", "password", "passwd", "credential", "session")
    if any(marker in lowered for marker in sensitive_markers):
        return "/[redacted]"
    return path
