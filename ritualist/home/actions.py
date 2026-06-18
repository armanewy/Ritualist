from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from threading import Lock
from time import monotonic
from typing import Any

from ritualist.activity_journal import ActivityJournal
from ritualist.home.models import HomeCardStatus, HomeLastRunStatus, HomeRuntimeEvent
from ritualist.learning_config import LocalLearningConfig


RecipeReference = str | Path
RITUALIST_JOURNAL_SOURCE_ID = "ritualist_journal"
_JOURNAL_DEDUPE_SECONDS = 0.5


class HomeCardAction(StrEnum):
    RUN = "run"
    DRY_RUN = "dry_run"
    DOCTOR = "doctor"
    EDIT_RECIPE = "edit_recipe"
    OPEN_LOGS = "open_logs"


@dataclass
class ActivityJournalHook:
    journal: ActivityJournal
    executor: Any | None = None
    dedupe_seconds: float = _JOURNAL_DEDUPE_SECONDS
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)
    _owned_executor: ThreadPoolExecutor | None = field(default=None, init=False, repr=False)
    _pending: list[Future[Any]] = field(default_factory=list, init=False, repr=False)
    _recent: dict[tuple[str, tuple[tuple[str, str], ...]], float] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )

    def record(self, event_type: str, **payload: Any) -> bool:
        if not _journal_is_enabled(self.journal):
            return False
        key = _journal_dedupe_key(event_type, payload)
        if self._is_duplicate(key):
            return False
        try:
            future = self._executor().submit(
                _write_journal_event,
                self.journal,
                event_type,
                dict(payload),
            )
        except Exception:  # noqa: BLE001 - journal hooks must never break callers.
            return False
        if isinstance(future, Future):
            with self._lock:
                self._pending.append(future)
        return True

    def flush(self, *, timeout: float | None = 2.0) -> None:
        with self._lock:
            pending = list(self._pending)
            self._pending = [future for future in self._pending if not future.done()]
        for future in pending:
            try:
                future.result(timeout=timeout)
            except Exception:  # noqa: BLE001 - journal failures are nonfatal.
                pass

    def shutdown(self, *, wait: bool = False) -> None:
        if self._owned_executor is None:
            return
        self._owned_executor.shutdown(wait=wait)
        self._owned_executor = None

    def _executor(self) -> Any:
        if self.executor is not None:
            return self.executor
        with self._lock:
            if self._owned_executor is None:
                self._owned_executor = ThreadPoolExecutor(
                    max_workers=1,
                    thread_name_prefix="ritualist-activity-journal",
                )
            return self._owned_executor

    def _is_duplicate(self, key: tuple[str, tuple[tuple[str, str], ...]]) -> bool:
        if self.dedupe_seconds <= 0:
            return False
        now = monotonic()
        cutoff = now - self.dedupe_seconds
        with self._lock:
            self._recent = {
                recent_key: seen_at
                for recent_key, seen_at in self._recent.items()
                if seen_at >= cutoff
            }
            if key in self._recent:
                return True
            self._recent[key] = now
        return False


def create_activity_journal_hook(
    config: LocalLearningConfig | None = None,
    *,
    journal: ActivityJournal | None = None,
    journal_path: Path | None = None,
) -> ActivityJournalHook:
    enabled = (
        config.is_source_enabled(RITUALIST_JOURNAL_SOURCE_ID)
        if config is not None
        else _current_journal_source_enabled
    )
    return ActivityJournalHook(journal or ActivityJournal(path=journal_path, enabled=enabled))


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
    journal_hook: ActivityJournalHook | None = None
    _last_executor: Any | None = field(default=None, init=False, repr=False)
    _default_journal_hook: ActivityJournalHook | None = field(default=None, init=False, repr=False)

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
        if dry_run:
            self.record_journal_event(
                "recipe_dry_run",
                surface="runtime",
                component_type="recipe",
                action_id="dry_run",
                recipe_id=recipe_ref,
            )
        runtime_event_callback = _runtime_journal_callback(
            self._activity_journal(),
            runtime_event_callback,
            recipe_ref=recipe_ref,
            dry_run=dry_run,
        )
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
        self._last_executor = executor
        return executor.run(load_recipe_reference(recipe_ref))

    def close_browser_state(self) -> bool:
        if self._last_executor is None:
            return False
        close = getattr(self._last_executor, "close_browser_state", None)
        if close is None:
            return False
        return bool(close())

    def doctor_recipe(self, recipe_ref: RecipeReference) -> Any:
        self.record_journal_event(
            "recipe_doctor_run",
            surface="runtime",
            component_type="recipe",
            action_id="doctor",
            recipe_id=recipe_ref,
        )
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

    def record_journal_event(self, event_type: str, **payload: Any) -> bool:
        try:
            return self._activity_journal().record(event_type, **payload)
        except Exception:  # noqa: BLE001 - journaling must never affect runtime actions.
            return False

    def _activity_journal(self) -> ActivityJournalHook:
        if self.journal_hook is not None:
            return self.journal_hook
        if self._default_journal_hook is None:
            self._default_journal_hook = create_activity_journal_hook()
        return self._default_journal_hook


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
        self.service.record_journal_event(
            "component_clicked",
            surface="home",
            component_id=card_id,
            component_type="ritual.card",
            action_id=parsed.value,
            recipe_id=recipe_ref,
        )

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
            keep_open_active=False,
            **_clear_wait_fields(),
        )

    if event_type == "run.state_changed":
        state = _event_value(getattr(event, "state", "running"))
        return HomeRuntimeEvent(
            card_id=card_id,
            status=_home_status_for_run_state(state),
            subtitle=f"Run state: {state}",
            description=str(getattr(event, "message", "") or ""),
            **({} if state == "waiting" else _clear_wait_fields()),
        )

    if event_type == "step.waiting":
        return HomeRuntimeEvent(
            card_id=card_id,
            status=HomeCardStatus.RUNNING,
            subtitle=f"Waiting: {getattr(event, 'action', '')}",
            description=_wait_description(
                target=getattr(event, "target", None),
                timeout_seconds=getattr(event, "timeout_seconds", None),
            ),
            wait_action=str(getattr(event, "action", "") or ""),
            wait_target=str(getattr(event, "target", "") or ""),
            wait_started_at=_datetime_string(getattr(event, "started_at", None)),
            wait_elapsed_seconds=_seconds_string(getattr(event, "elapsed_seconds", None)),
            wait_timeout_seconds=_seconds_string(getattr(event, "timeout_seconds", None)),
        )

    if event_type == "step.paused":
        return HomeRuntimeEvent(
            card_id=card_id,
            status=HomeCardStatus.WARNING,
            subtitle=f"Paused: {getattr(event, 'step_index', '')}",
            description=str(getattr(event, "step_name", "") or ""),
        )

    if event_type == "step.resumed":
        return HomeRuntimeEvent(
            card_id=card_id,
            status=HomeCardStatus.RUNNING,
            subtitle=f"Resumed: {getattr(event, 'step_index', '')}",
            description=str(getattr(event, "step_name", "") or ""),
        )

    if event_type == "confirmation.requested":
        return HomeRuntimeEvent(
            card_id=card_id,
            status=HomeCardStatus.WARNING,
            subtitle="Confirmation required",
            description=str(getattr(event, "prompt", "") or ""),
        )

    if event_type == "confirmation.resolved":
        approved = bool(getattr(event, "approved", False))
        return HomeRuntimeEvent(
            card_id=card_id,
            status=HomeCardStatus.RUNNING if approved else HomeCardStatus.WARNING,
            subtitle="Confirmation approved" if approved else "Confirmation declined",
            description=str(getattr(event, "message", "") or ""),
        )

    if event_type == "step.started":
        return HomeRuntimeEvent(
            card_id=card_id,
            status=HomeCardStatus.RUNNING,
            subtitle=f"Running step {getattr(event, 'step_index', '')}",
            description=str(getattr(event, "step_name", "") or ""),
            **_clear_wait_fields(),
        )

    if event_type == "step.finished":
        state = _event_value(getattr(event, "state", "success"))
        return HomeRuntimeEvent(
            card_id=card_id,
            status=_home_status_for_step_state(state),
            subtitle=f"Step {getattr(event, 'step_index', '')}: {state}",
            description=str(getattr(event, "message", "") or getattr(event, "step_name", "") or ""),
            **_clear_wait_fields(),
        )

    if event_type == "run.finished":
        state = _event_value(getattr(event, "state", "stopped"))
        return HomeRuntimeEvent(
            card_id=card_id,
            status=_home_status_for_run_state(state),
            last_run_status=_last_run_status_for_run_state(state),
            last_run_message=str(getattr(event, "message", "") or ""),
            subtitle=f"Run {state}",
            description=str(getattr(event, "message", "") or ""),
            **_clear_wait_fields(),
        )

    if event_type == "heartbeat":
        run_state = _event_value(getattr(event, "run_state", "running"))
        step_state = getattr(event, "step_state", None)
        if run_state == "waiting" or _event_value(step_state) == "waiting":
            action = str(getattr(event, "action", "") or "")
            target = str(getattr(event, "wait_target", "") or "")
            timeout = getattr(event, "wait_timeout_seconds", None)
            return HomeRuntimeEvent(
                card_id=card_id,
                status=HomeCardStatus.RUNNING,
                subtitle=f"Waiting: {action or 'step'}",
                description=_wait_description(target=target, timeout_seconds=timeout),
                wait_action=action,
                wait_target=target,
                wait_started_at=_datetime_string(getattr(event, "wait_started_at", None)),
                wait_elapsed_seconds=_seconds_string(getattr(event, "wait_elapsed_seconds", None)),
                wait_timeout_seconds=_seconds_string(timeout),
            )
        return HomeRuntimeEvent(
            card_id=card_id,
            status=_home_status_for_run_state(run_state),
            subtitle=f"Run state: {run_state}",
            description=f"Step state: {_event_value(step_state)}" if step_state is not None else "",
            **_clear_wait_fields(),
        )

    if event_type == "log.message":
        return HomeRuntimeEvent(
            card_id=card_id,
            description=str(getattr(event, "message", "") or ""),
        )

    return None


def home_event_from_step_status(card_id: str, event: Any) -> HomeRuntimeEvent:
    wait_action = str(getattr(event, "wait_action", "") or "")
    if wait_action:
        target = str(getattr(event, "wait_target", "") or "")
        timeout = getattr(event, "wait_timeout_seconds", None)
        return HomeRuntimeEvent(
            card_id=card_id,
            status=HomeCardStatus.RUNNING,
            subtitle=f"Waiting: {wait_action}",
            description=_wait_description(target=target, timeout_seconds=timeout),
            wait_action=wait_action,
            wait_target=target,
            wait_started_at=_datetime_string(getattr(event, "wait_started_at", None)),
            wait_elapsed_seconds=_seconds_string(getattr(event, "wait_elapsed_seconds", None)),
            wait_timeout_seconds=_seconds_string(timeout),
        )

    keep_open_active = bool(getattr(event, "keep_open_active", False))
    if keep_open_active:
        return HomeRuntimeEvent(
            card_id=card_id,
            status=HomeCardStatus.RUNNING,
            subtitle="Keep-open active",
            description="Browser window will remain open after the run.",
            keep_open_active=True,
            **_clear_wait_fields(),
        )

    return HomeRuntimeEvent(
        card_id=card_id,
        status=HomeCardStatus.RUNNING,
        subtitle=f"Step {getattr(event, 'index', '')}: {getattr(event, 'status', '')}",
        description=str(getattr(event, "step_name", "") or ""),
        **_clear_wait_fields(),
    )


def _runtime_journal_callback(
    journal: ActivityJournalHook,
    callback: Callable[[Any], None] | None,
    *,
    recipe_ref: RecipeReference,
    dry_run: bool,
) -> Callable[[Any], None]:
    def wrapped(event: Any) -> None:
        _record_runtime_journal_event(
            journal,
            event,
            recipe_ref=recipe_ref,
            dry_run=dry_run,
        )
        if callback is not None:
            callback(event)

    return wrapped


def _record_runtime_journal_event(
    journal: ActivityJournalHook,
    event: Any,
    *,
    recipe_ref: RecipeReference,
    dry_run: bool,
) -> bool:
    event_type = str(getattr(event, "type", "") or "")
    if event_type == "run.started":
        return journal.record(
            "recipe_run_started",
            recipe_id=str(getattr(event, "recipe_id", "") or recipe_ref),
            recipe_name=str(getattr(event, "recipe_name", "") or ""),
            run_id=str(getattr(event, "run_id", "") or ""),
            dry_run=bool(getattr(event, "dry_run", dry_run)),
            steps_total=getattr(event, "steps_total", None),
        )
    if event_type == "run.finished":
        return journal.record(
            "recipe_run_finished",
            recipe_id=recipe_ref,
            run_id=str(getattr(event, "run_id", "") or ""),
            status=_event_value(getattr(event, "state", "")),
            success=bool(getattr(event, "success", False)),
            dry_run=dry_run,
            duration_seconds=getattr(event, "duration_seconds", None),
        )
    return False


def _write_journal_event(journal: ActivityJournal, event_type: str, payload: dict[str, Any]) -> bool:
    try:
        return bool(journal.write(event_type, **payload))
    except Exception:  # noqa: BLE001 - activity journal writes are best-effort.
        return False


def _journal_is_enabled(journal: ActivityJournal) -> bool:
    try:
        return bool(journal.enabled)
    except Exception:  # noqa: BLE001 - opt-in checks must be nonfatal.
        return False


def _journal_dedupe_key(
    event_type: str,
    payload: Mapping[str, Any],
) -> tuple[str, tuple[tuple[str, str], ...]]:
    return (
        str(event_type),
        tuple(sorted((str(key), _journal_dedupe_value(value)) for key, value in payload.items())),
    )


def _journal_dedupe_value(value: Any) -> str:
    if isinstance(value, Mapping):
        return repr(
            tuple(
                sorted(
                    (str(key), _journal_dedupe_value(item))
                    for key, item in value.items()
                )
            )
        )
    if isinstance(value, list | tuple):
        return repr(tuple(_journal_dedupe_value(item) for item in value))
    return str(value)


def _load_local_learning_config() -> LocalLearningConfig:
    try:
        from ritualist.config import load_app_config

        return load_app_config().learning
    except Exception:  # noqa: BLE001 - config failures must disable journal writes.
        return LocalLearningConfig()


def _current_journal_source_enabled() -> bool:
    return _load_local_learning_config().is_source_enabled(RITUALIST_JOURNAL_SOURCE_ID)


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


def _clear_wait_fields() -> dict[str, str]:
    return {
        "wait_action": "",
        "wait_target": "",
        "wait_started_at": "",
        "wait_elapsed_seconds": "",
        "wait_timeout_seconds": "",
    }


def _wait_description(*, target: object, timeout_seconds: object) -> str:
    target_text = str(target or "").strip()
    timeout_text = _seconds_string(timeout_seconds)
    if target_text and timeout_text:
        return f"Target: {target_text} | Timeout: {timeout_text}s"
    if target_text:
        return f"Target: {target_text}"
    if timeout_text:
        return f"Timeout: {timeout_text}s"
    return "Waiting for condition"


def _datetime_string(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _seconds_string(value: object) -> str:
    if value is None or value == "":
        return ""
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return str(value)
