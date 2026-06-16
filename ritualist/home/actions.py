from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from ritualist.home.models import HomeCardStatus, HomeLastRunStatus, HomeRuntimeEvent


RecipeReference = str | Path


class HomeCardAction(StrEnum):
    RUN = "run"
    DRY_RUN = "dry_run"
    DOCTOR = "doctor"
    EDIT_RECIPE = "edit_recipe"
    OPEN_LOGS = "open_logs"


@dataclass(frozen=True)
class HomeActionOutcome:
    action: HomeCardAction
    card_id: str
    recipe_ref: RecipeReference | None = None
    dry_run: bool = False
    path: Path | None = None
    result: Any = None


@dataclass
class HomeActionService:
    runtime_runner: Callable[..., Any] | None = None
    doctor_runner: Callable[[RecipeReference], Any] | None = None
    recipe_path_resolver: Callable[[RecipeReference], Path] | None = None
    runs_path_resolver: Callable[[], Path] | None = None
    overlay_controller: Any | None = None

    def run_recipe(
        self,
        recipe_ref: RecipeReference,
        *,
        dry_run: bool,
        runtime_event_callback: Callable[[Any], None] | None = None,
        status_callback: Callable[[Any], None] | None = None,
        confirmer: Callable[[Any], bool] | None = None,
        control: Any | None = None,
    ) -> Any:
        if self.runtime_runner is not None:
            return self.runtime_runner(
                recipe_ref,
                dry_run=dry_run,
                runtime_event_callback=runtime_event_callback,
                status_callback=status_callback,
                confirmer=confirmer,
                control=control,
            )

        from ritualist.adapters import create_default_adapters
        from ritualist.config import load_app_config
        from ritualist.executor import WorkflowExecutor
        from ritualist.logging_setup import setup_logging
        from ritualist.overlay import NullOverlayController
        from ritualist.recipe_loader import load_recipe_reference
        from ritualist.run_logs import RunLogWriter
        from ritualist.runtime_control import RuntimeControl

        runtime_control = control or RuntimeControl()
        executor = WorkflowExecutor(
            adapters=create_default_adapters(),
            dry_run=dry_run,
            confirmer=confirmer,
            status_callback=status_callback,
            logger=setup_logging(),
            run_logger=RunLogWriter(),
            runtime_control=runtime_control,
            runtime_event_callback=runtime_event_callback,
            stop_requested=runtime_control.is_stopping,
            config=load_app_config(),
            overlay=self.overlay_controller or NullOverlayController(),
        )
        return executor.run(load_recipe_reference(recipe_ref))

    def doctor_recipe(self, recipe_ref: RecipeReference) -> Any:
        if self.doctor_runner is not None:
            return self.doctor_runner(recipe_ref)

        from ritualist.doctor import build_doctor_report
        from ritualist.recipe_loader import load_recipe_for_diagnostics

        recipe, _raw, missing_variables = load_recipe_for_diagnostics(recipe_ref)
        return build_doctor_report(recipe, missing_variables=missing_variables)

    def resolve_recipe_path(self, recipe_ref: RecipeReference) -> Path:
        if self.recipe_path_resolver is not None:
            return self.recipe_path_resolver(recipe_ref)

        from ritualist.recipe_loader import resolve_recipe_reference

        return resolve_recipe_reference(recipe_ref)

    def resolve_runs_path(self) -> Path:
        if self.runs_path_resolver is not None:
            return self.runs_path_resolver()

        from ritualist.paths import runs_dir

        return runs_dir()


@dataclass
class HomeActionDispatcher:
    service: HomeActionService = field(default_factory=HomeActionService)
    recipe_refs: Mapping[str, RecipeReference] = field(default_factory=dict)

    def dispatch(
        self,
        action: HomeCardAction | str,
        card_id: str,
        *,
        runtime_event_callback: Callable[[Any], None] | None = None,
        status_callback: Callable[[Any], None] | None = None,
        confirmer: Callable[[Any], bool] | None = None,
        control: Any | None = None,
    ) -> HomeActionOutcome:
        parsed = HomeCardAction(action)
        recipe_ref = self.recipe_reference(card_id)

        if parsed is HomeCardAction.RUN:
            result = self.service.run_recipe(
                recipe_ref,
                dry_run=False,
                runtime_event_callback=runtime_event_callback,
                status_callback=status_callback,
                confirmer=confirmer,
                control=control,
            )
            return HomeActionOutcome(parsed, card_id, recipe_ref, dry_run=False, result=result)

        if parsed is HomeCardAction.DRY_RUN:
            result = self.service.run_recipe(
                recipe_ref,
                dry_run=True,
                runtime_event_callback=runtime_event_callback,
                status_callback=status_callback,
                confirmer=confirmer,
                control=control,
            )
            return HomeActionOutcome(parsed, card_id, recipe_ref, dry_run=True, result=result)

        if parsed is HomeCardAction.DOCTOR:
            result = self.service.doctor_recipe(recipe_ref)
            return HomeActionOutcome(parsed, card_id, recipe_ref, result=result)

        if parsed is HomeCardAction.EDIT_RECIPE:
            path = self.service.resolve_recipe_path(recipe_ref)
            return HomeActionOutcome(parsed, card_id, recipe_ref, path=path)

        path = self.service.resolve_runs_path()
        return HomeActionOutcome(parsed, card_id, path=path)

    def recipe_reference(self, card_id: str) -> RecipeReference:
        return self.recipe_refs.get(card_id, card_id)


def home_event_from_runtime(card_id: str, event: Any) -> HomeRuntimeEvent | None:
    event_type = str(getattr(event, "type", ""))
    if event_type == "run.started":
        dry_run = bool(getattr(event, "dry_run", False))
        return HomeRuntimeEvent(
            card_id=card_id,
            status=HomeCardStatus.RUNNING,
            subtitle="Dry run started" if dry_run else "Run started",
            description=_recipe_event_description(event),
        )

    if event_type == "run.state_changed":
        state = _event_value(getattr(event, "state", "running"))
        return HomeRuntimeEvent(
            card_id=card_id,
            status=_home_status_for_run_state(state),
            subtitle=f"Run state: {state}",
            description=str(getattr(event, "message", "") or ""),
        )

    if event_type == "step.started":
        return HomeRuntimeEvent(
            card_id=card_id,
            status=HomeCardStatus.RUNNING,
            subtitle=f"Running step {getattr(event, 'step_index', '')}",
            description=str(getattr(event, "step_name", "") or ""),
        )

    if event_type == "step.finished":
        state = _event_value(getattr(event, "state", "success"))
        return HomeRuntimeEvent(
            card_id=card_id,
            status=_home_status_for_step_state(state),
            subtitle=f"Step {getattr(event, 'step_index', '')}: {state}",
            description=str(getattr(event, "message", "") or getattr(event, "step_name", "") or ""),
        )

    if event_type == "run.finished":
        state = _event_value(getattr(event, "state", "stopped"))
        return HomeRuntimeEvent(
            card_id=card_id,
            status=_home_status_for_run_state(state),
            last_run_status=_last_run_status_for_run_state(state),
            subtitle=f"Run {state}",
            description=str(getattr(event, "message", "") or ""),
        )

    if event_type == "heartbeat":
        run_state = _event_value(getattr(event, "run_state", "running"))
        step_state = getattr(event, "step_state", None)
        return HomeRuntimeEvent(
            card_id=card_id,
            status=_home_status_for_run_state(run_state),
            subtitle=f"Run state: {run_state}",
            description=f"Step state: {_event_value(step_state)}" if step_state is not None else "",
        )

    if event_type == "log.message":
        return HomeRuntimeEvent(
            card_id=card_id,
            description=str(getattr(event, "message", "") or ""),
        )

    return None


def _recipe_event_description(event: Any) -> str:
    recipe_name = getattr(event, "recipe_name", None)
    if recipe_name:
        return str(recipe_name)
    recipe_id = getattr(event, "recipe_id", None)
    return str(recipe_id or "")


def _event_value(value: Any) -> str:
    if value is None:
        return ""
    return str(getattr(value, "value", value))


def _home_status_for_run_state(state: str) -> HomeCardStatus:
    if state == "success":
        return HomeCardStatus.SUCCESS
    if state == "failed":
        return HomeCardStatus.FAILED
    if state in {"stopped", "interrupted", "confirming"}:
        return HomeCardStatus.WARNING
    return HomeCardStatus.RUNNING


def _home_status_for_step_state(state: str) -> HomeCardStatus:
    if state in {"failed", "cancelled"}:
        return HomeCardStatus.FAILED if state == "failed" else HomeCardStatus.WARNING
    return HomeCardStatus.RUNNING


def _last_run_status_for_run_state(state: str) -> HomeLastRunStatus:
    if state == "success":
        return HomeLastRunStatus.SUCCESS
    if state == "failed":
        return HomeLastRunStatus.FAILED
    if state == "interrupted" and hasattr(HomeLastRunStatus, "INTERRUPTED"):
        return HomeLastRunStatus.INTERRUPTED
    if state == "running" and hasattr(HomeLastRunStatus, "RUNNING"):
        return HomeLastRunStatus.RUNNING
    return HomeLastRunStatus.STOPPED
