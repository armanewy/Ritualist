from __future__ import annotations

import json
import os
import re
import shlex
import sys
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .actions.base import StepResult
from .models import Recipe
from .paths import runs_dir


RUN_LOG_SCHEMA_VERSION = 2
OPERATOR_NOTES_FILENAME = "operator_notes.jsonl"
OPERATOR_NOTE_SCHEMA_VERSION = "operator_note.v1"

STOPPED_USER_DECLINED_CONFIRMATION = "stopped_user_declined_confirmation"
STOPPED_USER_CANCELLED = "stopped_user_cancelled"
STOPPED_BY_STOP_BUTTON = "stopped_by_stop_button"
FAILED_REASON = "failed"
INTERRUPTED_REASON = "interrupted"

KEEP_SETUP_OPEN = "keep_setup_open"
CLEAN_UP_RITUALIST_OPENED = "clean_up_ritualist_opened"
OPEN_RUN_LOG = "open_run_log"


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    path: Path
    metadata: dict[str, Any]
    steps: list[dict[str, Any]]
    notes: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class ReconciledRun:
    run_id: str
    path: Path
    message: str


@dataclass(frozen=True)
class RunbookSummary:
    preflight_status: str
    preflight_passed: int
    preflight_failed: int
    actions_completed: int
    assertions_passed: int
    assertions_failed: int
    human_prompts_answered: int
    final_status: str
    stop_semantics: str
    last_step: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "preflight_status": self.preflight_status,
            "preflight_passed": self.preflight_passed,
            "preflight_failed": self.preflight_failed,
            "actions_completed": self.actions_completed,
            "assertions_passed": self.assertions_passed,
            "assertions_failed": self.assertions_failed,
            "human_prompts_answered": self.human_prompts_answered,
            "final_status": self.final_status,
            "stop_semantics": self.stop_semantics,
            "last_step": self.last_step,
        }


class RunLogWriter:
    def __init__(
        self,
        *,
        base_dir: Path | None = None,
        heartbeat_flush_interval_seconds: float = 1.0,
        monotonic_clock: Callable[[], float] | None = None,
    ) -> None:
        self.base_dir = base_dir or runs_dir()
        self.run_dir: Path | None = None
        self._run_json: Path | None = None
        self._steps_jsonl: Path | None = None
        self._metadata: dict[str, Any] = {}
        self._run_writer_id = str(uuid.uuid4())
        self._heartbeat_flush_interval_seconds = max(0.0, heartbeat_flush_interval_seconds)
        self._monotonic_clock = monotonic_clock or time.monotonic
        self._last_heartbeat_write_at: float | None = None

    def start(self, recipe: Recipe, *, dry_run: bool) -> None:
        started_at = _now_iso()
        run_dir = self._create_run_dir(recipe.id)
        self._run_json = run_dir / "run.json"
        self._steps_jsonl = run_dir / "steps.jsonl"
        self._metadata = {
            "recipe_id": recipe.id,
            "recipe_name": recipe.name,
            "dry_run": dry_run,
            "status": "running",
            "process_id": os.getpid(),
            "process_start_time": _current_process_start_time(),
            "run_writer_id": self._run_writer_id,
            "run_log_schema_version": RUN_LOG_SCHEMA_VERSION,
            "pyinstaller_bundle": _is_pyinstaller_bundle(),
            "started_at": started_at,
            "ended_at": None,
            "last_heartbeat_at": started_at,
            "last_step_id": None,
            "last_step_name": None,
            "last_step_phase": None,
            "current_phase": None,
            "final_message": None,
            "stopped_reason": None,
            "declined_target": None,
            "ownership_ledger": [],
            "cleanup_offer": None,
            "cleanup_choice": None,
            "remembered_cleanup_preference_applied": False,
            "remembered_approval_applied": None,
            "current_run_state": "running",
            "current_step_state": None,
            "final_state": None,
            "run_state_history": [
                {
                    "at": started_at,
                    "state": "running",
                    "event": "run.started",
                }
            ],
            "event_summaries": [
                {
                    "at": started_at,
                    "event": "run.started",
                    "run_state": "running",
                }
            ],
            "wait_metadata": None,
            "paused_metadata": None,
            "confirming_metadata": None,
            "steps_total": len(recipe.execution_steps),
            "steps_completed": 0,
            "operator_notes_count": 0,
            "last_operator_note_at": None,
        }
        self._write_run_json()
        self._steps_jsonl.write_text("", encoding="utf-8")
        self.run_dir = run_dir

    def heartbeat(
        self,
        step_id: int | None = None,
        step_name: str | None = None,
        run_state: str | None = None,
        step_state: str | None = None,
    ) -> None:
        if self._run_json is None:
            return
        self._metadata["last_heartbeat_at"] = _now_iso()
        if step_id is not None:
            self._metadata["last_step_id"] = step_id
        if step_name is not None:
            self._metadata["last_step_name"] = step_name
        if step_id is not None or step_name is not None:
            resolved_step_state = step_state or "running"
            resolved_run_state = run_state or "running"
            step_state_changed = self._metadata.get("current_step_state") != resolved_step_state
            run_state_changed = self._metadata.get("current_run_state") != resolved_run_state
            if step_state_changed:
                self._metadata["current_step_state"] = resolved_step_state
            if run_state_changed:
                self._set_run_state(resolved_run_state, event="run.state_changed")
            force_write = step_state_changed or run_state_changed
            if force_write or self._heartbeat_due():
                self._append_event_summary(
                    "heartbeat",
                    run_state=resolved_run_state,
                    step_state=resolved_step_state,
                    step_id=step_id,
                    step_name=step_name,
                )
                self._write_run_json(force=True)
            return
        self._write_run_json(force=False)

    def write_step(self, result: StepResult) -> None:
        if self._steps_jsonl is None:
            return
        payload = {
            "index": result.index,
            "step_name": result.step_name,
            "action": result.action,
            "status": result.status,
            "message": _safe_message(result),
            "phase": result.phase,
            "started_at": result.started_at.isoformat(),
            "ended_at": result.ended_at.isoformat(),
            "optional": result.optional,
            "dry_run": result.dry_run,
        }
        if result.metadata:
            payload["metadata"] = result.metadata
        with self._steps_jsonl.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self._metadata["steps_completed"] = result.index
        self._metadata["last_step_id"] = result.index
        self._metadata["last_step_name"] = result.step_name
        self._metadata["last_step_phase"] = result.phase
        self._metadata["current_phase"] = result.phase
        self._metadata["last_heartbeat_at"] = _now_iso()
        step_state = _runtime_step_state(result.status)
        self._metadata["current_step_state"] = step_state
        self._append_event_summary(
            "step.finished",
            step_state=step_state,
            step_id=result.index,
            step_name=result.step_name,
            phase=result.phase,
            action=result.action,
            message=_safe_message(result),
            metadata=result.metadata or None,
        )
        self._write_run_json()

    def finish(
        self,
        *,
        success: bool,
        final_state: str | None = None,
        final_message: str | None = None,
        stopped_reason: str | None = None,
        declined_target: dict[str, Any] | None = None,
        ownership_ledger: list[dict[str, Any]] | None = None,
        cleanup_offer: dict[str, Any] | None = None,
        cleanup_choice: dict[str, Any] | None = None,
        remembered_cleanup_preference_applied: bool | None = None,
        remembered_approval_applied: dict[str, Any] | None = None,
    ) -> None:
        if self._run_json is None:
            return
        resolved_final_state = final_state or ("success" if success else "stopped")
        self._metadata["status"] = _terminal_status(resolved_final_state, success=success)
        self._metadata["ended_at"] = _now_iso()
        self._metadata["last_heartbeat_at"] = self._metadata["ended_at"]
        self._metadata["final_message"] = final_message
        self._metadata["stopped_reason"] = stopped_reason
        self._metadata["declined_target"] = declined_target
        if ownership_ledger is not None:
            self._metadata["ownership_ledger"] = ownership_ledger
        self._metadata["cleanup_offer"] = cleanup_offer
        self._metadata["cleanup_choice"] = cleanup_choice
        if remembered_cleanup_preference_applied is not None:
            self._metadata["remembered_cleanup_preference_applied"] = (
                remembered_cleanup_preference_applied
            )
        self._metadata["remembered_approval_applied"] = remembered_approval_applied
        self._metadata["final_state"] = resolved_final_state
        self._set_run_state(resolved_final_state, event="run.finished")
        self._append_event_summary("run.finished", run_state=resolved_final_state)
        self._clear_transient_metadata()
        self._write_run_json()

    def record_run_state(
        self,
        state: str,
        *,
        event: str | None = None,
        message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if self._run_json is None:
            return
        self._metadata["last_heartbeat_at"] = _now_iso()
        self._set_run_state(state, event=event, message=message, metadata=metadata)
        self._append_event_summary(
            event or "run.state_changed",
            run_state=state,
            message=message,
            metadata=metadata,
        )
        self._write_run_json()

    def record_step_state(
        self,
        state: str,
        *,
        step_id: int | None = None,
        step_name: str | None = None,
        phase: str | None = None,
        action: str | None = None,
        message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if self._run_json is None:
            return
        self._metadata["last_heartbeat_at"] = _now_iso()
        if step_id is not None:
            self._metadata["last_step_id"] = step_id
        if step_name is not None:
            self._metadata["last_step_name"] = step_name
        if phase is not None:
            self._metadata["last_step_phase"] = phase
            self._metadata["current_phase"] = phase
        self._metadata["current_step_state"] = state
        self._append_event_summary(
            _event_for_step_state(state),
            step_state=state,
            step_id=step_id,
            step_name=step_name,
            phase=phase,
            action=action,
            message=message,
            metadata=metadata,
        )
        self._write_run_json()

    def set_wait_metadata(self, metadata: dict[str, Any] | None) -> None:
        self._set_transient_metadata("wait_metadata", metadata, event="step.waiting")

    def set_paused_metadata(self, metadata: dict[str, Any] | None) -> None:
        self._set_transient_metadata("paused_metadata", metadata, event="step.paused")

    def set_confirming_metadata(self, metadata: dict[str, Any] | None) -> None:
        self._set_transient_metadata("confirming_metadata", metadata, event="confirmation.requested")

    def add_operator_note(self, note: str) -> dict[str, Any] | None:
        if self.run_dir is None:
            return None
        entry = _operator_note_entry(note)
        _append_operator_note_entry(self.run_dir, entry)
        self._metadata["operator_notes_count"] = int(
            self._metadata.get("operator_notes_count") or 0
        ) + 1
        self._metadata["last_operator_note_at"] = entry["at"]
        self._append_event_summary(
            "operator_note.added",
            metadata={"source": "user", "user_entered": True},
        )
        self._write_run_json()
        return entry

    def _create_run_dir(self, recipe_id: str) -> Path:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        base_name = f"{timestamp}_{recipe_id}"
        candidate = self.base_dir / base_name
        counter = 2
        while candidate.exists():
            candidate = self.base_dir / f"{base_name}_{counter}"
            counter += 1
        candidate.mkdir(parents=True, exist_ok=False)
        return candidate

    def _write_run_json(self, *, force: bool = True) -> None:
        if self._run_json is None:
            return
        if not force and not self._heartbeat_due():
            return
        self._last_heartbeat_write_at = self._monotonic_clock()
        self._refresh_operator_note_metadata()
        _atomic_write_json(self._run_json, self._metadata)

    def _heartbeat_due(self) -> bool:
        if self._last_heartbeat_write_at is None:
            return True
        return (
            self._monotonic_clock() - self._last_heartbeat_write_at
            >= self._heartbeat_flush_interval_seconds
        )

    def _refresh_operator_note_metadata(self) -> None:
        if self.run_dir is None:
            return
        notes = _read_operator_notes(self.run_dir)
        if not notes:
            self._metadata.setdefault("operator_notes_count", 0)
            self._metadata.setdefault("last_operator_note_at", None)
            return
        self._metadata["operator_notes_count"] = len(notes)
        last_at = notes[-1].get("at")
        if isinstance(last_at, str) and last_at:
            self._metadata["last_operator_note_at"] = last_at

    def _set_run_state(
        self,
        state: str,
        *,
        event: str | None = None,
        message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        changed = self._metadata.get("current_run_state") != state
        self._metadata["current_run_state"] = state
        history = self._metadata.setdefault("run_state_history", [])
        if changed or not history:
            entry = {
                "at": _now_iso(),
                "state": state,
                "event": event or "run.state_changed",
            }
            if message:
                entry["message"] = message
            if metadata:
                entry["metadata"] = metadata
            history.append(entry)

    def _append_event_summary(
        self,
        event: str,
        *,
        run_state: str | None = None,
        step_state: str | None = None,
        step_id: int | None = None,
        step_name: str | None = None,
        phase: str | None = None,
        action: str | None = None,
        message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        entry: dict[str, Any] = {"at": _now_iso(), "event": event}
        if run_state is not None:
            entry["run_state"] = run_state
        if step_state is not None:
            entry["step_state"] = step_state
        if step_id is not None:
            entry["step_id"] = step_id
        if step_name is not None:
            entry["step_name"] = step_name
        if phase is not None:
            entry["phase"] = phase
        if action is not None:
            entry["action"] = action
        if message:
            entry["message"] = message
        if metadata:
            entry["metadata"] = metadata
        self._metadata.setdefault("event_summaries", []).append(entry)

    def _set_transient_metadata(
        self,
        key: str,
        metadata: dict[str, Any] | None,
        *,
        event: str,
    ) -> None:
        if self._run_json is None:
            return
        self._metadata["last_heartbeat_at"] = _now_iso()
        self._metadata[key] = metadata
        self._append_event_summary(event, metadata={key: metadata} if metadata else None)
        self._write_run_json()

    def _clear_transient_metadata(self) -> None:
        self._metadata["wait_metadata"] = None
        self._metadata["paused_metadata"] = None
        self._metadata["confirming_metadata"] = None


def _safe_message(result: StepResult) -> str:
    if result.action == "browser.open":
        if result.dry_run:
            return "would open URL"
        if result.status == "success":
            return "opened URL"
        return "browser.open did not complete"
    if result.action == "app.launch":
        if result.dry_run:
            return "would launch app"
        if result.status == "success":
            return f"launched {_safe_app_command_label(result.message)}"
        return "app.launch did not complete"
    return result.message


def _safe_app_command_label(message: str) -> str:
    raw = str(message or "").strip()
    if raw.casefold().startswith("launched "):
        raw = raw[9:].strip()
    try:
        first = shlex.split(raw, posix=False)[0]
    except (ValueError, IndexError):
        first = raw.split(maxsplit=1)[0] if raw.split() else ""
    first = first.strip().strip("\"'")
    if not first:
        return "app"
    if "://" in first:
        return "app URL"
    basename = first.replace("\\", "/").split("/")[-1].strip()
    if not basename or _looks_like_sensitive_fragment(basename):
        return "app"
    return basename


def _looks_like_sensitive_fragment(value: str) -> bool:
    text = value.casefold()
    if any(token in text for token in ("token", "secret", "password", "passwd", "apikey", "api_key")):
        return True
    return bool(re.search(r"[?&#=]", value))


def _runtime_step_state(status: str) -> str:
    if status == "dry-run":
        return "success"
    return status


def _terminal_status(final_state: str, *, success: bool) -> str:
    if final_state in {"success", "failed", "stopped", "interrupted"}:
        return final_state
    return "success" if success else "stopped"


def _event_for_step_state(state: str) -> str:
    if state == "running":
        return "step.started"
    if state == "waiting":
        return "step.waiting"
    if state == "paused":
        return "step.paused"
    if state == "confirming":
        return "confirmation.requested"
    if state in {"success", "failed", "cancelled", "skipped"}:
        return "step.finished"
    return "log.message"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def reconcile_running_runs(
    *,
    limit: int = 100,
    base_dir: Path | None = None,
    stale_after: timedelta = timedelta(hours=1),
    process_checker: Any | None = None,
) -> list[ReconciledRun]:
    root = base_dir or runs_dir()
    if not root.exists():
        return []

    repaired: list[ReconciledRun] = []
    candidates = sorted(
        (candidate for candidate in root.iterdir() if candidate.is_dir()),
        key=lambda candidate: candidate.stat().st_mtime,
        reverse=True,
    )[:limit]
    checker = process_checker or _process_status
    for path in candidates:
        metadata = _read_run_metadata(path)
        if metadata is None or metadata.get("status") != "running":
            continue

        reason = _interruption_reason(metadata, checker=checker, stale_after=stale_after)
        if reason is None:
            continue

        message = _interrupted_message(metadata, path)
        metadata["status"] = "interrupted"
        metadata["ended_at"] = _now_iso()
        metadata["interrupted_at"] = metadata["ended_at"]
        metadata["final_message"] = message
        metadata["interruption_reason"] = reason
        metadata["stopped_reason"] = INTERRUPTED_REASON
        metadata.setdefault("ownership_ledger", [])
        metadata["cleanup_offer"] = None
        metadata["cleanup_choice"] = None
        metadata["current_run_state"] = "interrupted"
        metadata["final_state"] = "interrupted"
        _append_metadata_run_state(
            metadata,
            state="interrupted",
            event="run.interrupted",
            at=metadata["ended_at"],
            message=message,
        )
        _append_metadata_event_summary(
            metadata,
            event="run.interrupted",
            at=metadata["ended_at"],
            run_state="interrupted",
            message=message,
        )
        _write_run_metadata(path, metadata)
        repaired.append(ReconciledRun(run_id=path.name, path=path, message=message))
    return repaired


def list_recent_runs(*, limit: int = 10, base_dir: Path | None = None) -> list[RunRecord]:
    root = base_dir or runs_dir()
    if not root.exists():
        return []
    records: list[RunRecord] = []
    for path in sorted(
        (candidate for candidate in root.iterdir() if candidate.is_dir()),
        key=lambda candidate: candidate.stat().st_mtime,
        reverse=True,
    ):
        record = load_run(path, include_notes=False)
        if record is not None:
            records.append(record)
        if len(records) >= limit:
            break
    return records


def resolve_run_reference(run_id_or_path: str | Path, *, base_dir: Path | None = None) -> Path:
    raw = Path(run_id_or_path)
    if raw.exists() or raw.parent != Path("."):
        return raw
    return (base_dir or runs_dir()) / str(run_id_or_path)


def load_run(
    run_id_or_path: str | Path,
    *,
    base_dir: Path | None = None,
    include_notes: bool = True,
) -> RunRecord | None:
    path = resolve_run_reference(run_id_or_path, base_dir=base_dir)
    run_json = path / "run.json"
    steps_jsonl = path / "steps.jsonl"
    if not run_json.exists():
        return None
    try:
        metadata = json.loads(run_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    steps: list[dict[str, Any]] = []
    if steps_jsonl.exists():
        try:
            for line in steps_jsonl.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    steps.append(json.loads(line))
        except (OSError, json.JSONDecodeError):
            steps = []
    notes = _read_operator_notes(path) if include_notes else []
    return RunRecord(run_id=path.name, path=path, metadata=metadata, steps=steps, notes=notes)


def append_operator_note(
    run_id_or_path: str | Path,
    note: str,
    *,
    base_dir: Path | None = None,
) -> dict[str, Any] | None:
    path = resolve_run_reference(run_id_or_path, base_dir=base_dir)
    if not (path / "run.json").exists():
        return None
    entry = _operator_note_entry(note)
    _append_operator_note_entry(path, entry)
    metadata = _read_run_metadata(path)
    if metadata is not None:
        _mark_operator_note_in_metadata(path, metadata, entry)
        _write_run_metadata(path, metadata)
    return entry


def summarize_run_record(record: RunRecord) -> RunbookSummary:
    return summarize_run_steps(record.steps, metadata=record.metadata)


def summarize_step_results(
    results: list[StepResult],
    *,
    metadata: dict[str, Any] | None = None,
    interrupted: bool = False,
) -> RunbookSummary:
    steps = [
        {
            "index": result.index,
            "step_name": result.step_name,
            "action": result.action,
            "status": result.status,
            "message": result.message,
            "phase": result.phase,
        }
        for result in results
    ]
    return summarize_run_steps(steps, metadata=metadata, interrupted=interrupted)


def summarize_run_steps(
    steps: list[dict[str, Any]],
    *,
    metadata: dict[str, Any] | None = None,
    interrupted: bool = False,
) -> RunbookSummary:
    metadata = metadata or {}
    normalized_steps = [_SummaryStep.from_mapping(step) for step in steps]
    preflight_steps = _preflight_steps(normalized_steps)
    statuses = [step.status for step in normalized_steps]
    final_status = _summary_final_status(statuses, metadata, interrupted=interrupted)
    return RunbookSummary(
        preflight_status=_preflight_status(preflight_steps),
        preflight_passed=_count_status(preflight_steps, "success"),
        preflight_failed=_count_status(preflight_steps, "failed"),
        actions_completed=sum(
            1
            for step in normalized_steps
            if not _is_assertion_action(step.action) and step.status == "success"
        ),
        assertions_passed=sum(
            1
            for step in normalized_steps
            if _is_assertion_action(step.action) and step.status == "success"
        ),
        assertions_failed=sum(
            1
            for step in normalized_steps
            if _is_assertion_action(step.action) and step.status == "failed"
        ),
        human_prompts_answered=sum(
            1
            for step in normalized_steps
            if step.action in HUMAN_PROMPT_ACTIONS and step.status == "success"
        ),
        final_status=final_status,
        stop_semantics=_stop_semantics(final_status, statuses, interrupted=interrupted),
        last_step=_summary_last_step(normalized_steps, metadata),
    )


@dataclass(frozen=True)
class _SummaryStep:
    index: int | None
    step_name: str
    action: str
    status: str
    phase: str

    @classmethod
    def from_mapping(cls, step: dict[str, Any]) -> "_SummaryStep":
        raw_index = step.get("index")
        try:
            index = int(raw_index) if raw_index not in (None, "") else None
        except (TypeError, ValueError):
            index = None
        return cls(
            index=index,
            step_name=str(step.get("step_name") or ""),
            action=str(step.get("action") or ""),
            status=str(step.get("status") or ""),
            phase=str(step.get("phase") or ""),
        )


ASSERTION_ACTION_PREFIX = "assert."
HUMAN_PROMPT_ACTIONS = {
    "confirm.ask",
    "human.checklist",
    "human.confirm_evidence",
    "human.prompt",
    "wait.for_user",
}


def _preflight_steps(steps: list[_SummaryStep]) -> list[_SummaryStep]:
    if any(step.phase for step in steps):
        return [step for step in steps if step.phase == "preflight"]
    return _legacy_leading_assertion_steps(steps)


def _legacy_leading_assertion_steps(steps: list[_SummaryStep]) -> list[_SummaryStep]:
    preflight: list[_SummaryStep] = []
    for step in steps:
        if not _is_assertion_action(step.action):
            break
        preflight.append(step)
    return preflight


def _is_assertion_action(action: str) -> bool:
    return action.startswith(ASSERTION_ACTION_PREFIX)


def _count_status(steps: list[_SummaryStep], status: str) -> int:
    return sum(1 for step in steps if step.status == status)


def _preflight_status(preflight_steps: list[_SummaryStep]) -> str:
    if not preflight_steps:
        return "not configured"
    if any(step.status == "failed" for step in preflight_steps):
        return "failed"
    if any(step.status == "cancelled" for step in preflight_steps):
        return "stopped"
    if all(step.status == "dry-run" for step in preflight_steps):
        return "dry-run"
    if all(step.status in {"success", "dry-run", "skipped"} for step in preflight_steps):
        return "passed"
    return "incomplete"


def _summary_final_status(
    statuses: list[str],
    metadata: dict[str, Any],
    *,
    interrupted: bool,
) -> str:
    if interrupted:
        return "stopped"
    raw_status = metadata.get("final_state") or metadata.get("status")
    status = str(raw_status or "").strip().lower()
    if status and status != "running":
        return status
    if any(step_status == "failed" for step_status in statuses):
        return "failed"
    if any(step_status == "cancelled" for step_status in statuses):
        return "stopped"
    if statuses and all(
        step_status in {"success", "skipped", "dry-run"} for step_status in statuses
    ):
        return "success"
    return status or "unknown"


def _stop_semantics(final_status: str, statuses: list[str], *, interrupted: bool) -> str:
    if interrupted or final_status == "interrupted":
        return "interrupted"
    if final_status == "stopped" or any(status == "cancelled" for status in statuses):
        return "stopped"
    return "none"


def _summary_last_step(steps: list[_SummaryStep], metadata: dict[str, Any]) -> str:
    step_id = metadata.get("last_step_id")
    step_name = metadata.get("last_step_name")
    step_state = metadata.get("current_step_state")
    if step_id is not None or step_name:
        label = f"#{step_id}" if step_id is not None else "unknown step"
        if step_name:
            label = f"{label} {step_name}"
        if step_state:
            label = f"{label} ({step_state})"
        return label
    if not steps:
        return ""
    step = steps[-1]
    label = f"#{step.index}" if step.index is not None else "unknown step"
    if step.step_name:
        label = f"{label} {step.step_name}"
    if step.status:
        label = f"{label} ({step.status})"
    return label


def _operator_note_entry(note: str) -> dict[str, Any]:
    normalized = note.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        raise ValueError("operator note cannot be empty")
    return {
        "schema_version": OPERATOR_NOTE_SCHEMA_VERSION,
        "kind": "operator_note",
        "source": "user",
        "user_entered": True,
        "at": _now_iso(),
        "note": normalized,
    }


def _append_operator_note_entry(path: Path, entry: dict[str, Any]) -> None:
    notes_path = path / OPERATOR_NOTES_FILENAME
    with notes_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _read_operator_notes(path: Path) -> list[dict[str, Any]]:
    notes_path = path / OPERATOR_NOTES_FILENAME
    if not notes_path.exists():
        return []
    notes: list[dict[str, Any]] = []
    try:
        for line in notes_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            if isinstance(payload, dict):
                notes.append(payload)
    except (OSError, json.JSONDecodeError):
        return []
    return notes


def _mark_operator_note_in_metadata(
    path: Path,
    metadata: dict[str, Any],
    entry: dict[str, Any],
) -> None:
    metadata["operator_notes_count"] = len(_read_operator_notes(path))
    metadata["last_operator_note_at"] = entry["at"]
    _append_metadata_event_summary(
        metadata,
        event="operator_note.added",
        at=str(entry["at"]),
    )


def _read_run_metadata(path: Path) -> dict[str, Any] | None:
    run_json = path / "run.json"
    if not run_json.exists():
        return None
    try:
        return json.loads(run_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write_run_metadata(path: Path, metadata: dict[str, Any]) -> None:
    _atomic_write_json(path / "run.json", metadata)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    tmp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    tmp_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    for attempt in range(5):
        try:
            tmp_path.replace(path)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.05)


def _append_metadata_run_state(
    metadata: dict[str, Any],
    *,
    state: str,
    event: str,
    at: str,
    message: str | None = None,
) -> None:
    history = metadata.setdefault("run_state_history", [])
    if not isinstance(history, list):
        history = []
        metadata["run_state_history"] = history
    if history and history[-1].get("state") == state and history[-1].get("event") == event:
        return
    entry: dict[str, Any] = {"at": at, "state": state, "event": event}
    if message:
        entry["message"] = message
    history.append(entry)


def _append_metadata_event_summary(
    metadata: dict[str, Any],
    *,
    event: str,
    at: str,
    run_state: str | None = None,
    step_state: str | None = None,
    message: str | None = None,
) -> None:
    summaries = metadata.setdefault("event_summaries", [])
    if not isinstance(summaries, list):
        summaries = []
        metadata["event_summaries"] = summaries
    entry: dict[str, Any] = {"at": at, "event": event}
    if run_state is not None:
        entry["run_state"] = run_state
    if step_state is not None:
        entry["step_state"] = step_state
    if message:
        entry["message"] = message
    summaries.append(entry)


def _interruption_reason(
    metadata: dict[str, Any],
    *,
    checker: Any,
    stale_after: timedelta,
) -> str | None:
    raw_pid = metadata.get("process_id")
    if raw_pid is None:
        return "missing run ownership metadata"
    try:
        pid = int(raw_pid)
    except (TypeError, ValueError):
        return "invalid process_id"

    process_exists, process_start_time = checker(pid)
    if process_exists is False:
        return f"recorded process {pid} is not running"

    recorded_start_time = metadata.get("process_start_time")
    if (
        process_exists is True
        and recorded_start_time is not None
        and process_start_time is not None
        and _process_start_time_mismatch(recorded_start_time, process_start_time)
    ):
        return f"recorded process {pid} belongs to a different process start time"

    heartbeat = _parse_iso_datetime(metadata.get("last_heartbeat_at"))
    if process_exists is None and _is_stale(heartbeat, stale_after):
        return (
            f"process status for {pid} could not be determined and "
            f"heartbeat is older than {stale_after}"
        )
    return None



def _process_start_time_mismatch(recorded_start_time: Any, actual_start_time: float) -> bool:
    try:
        return abs(float(recorded_start_time) - float(actual_start_time)) > 1
    except (TypeError, ValueError):
        return True

def _interrupted_message(metadata: dict[str, Any], path: Path) -> str:
    last_step = metadata.get("last_step_name") or _last_logged_step_name(path)
    if last_step:
        return (
            "Ritualist exited before finalizing this run. "
            f"Last recorded step: {last_step}."
        )
    return "Ritualist exited before finalizing this run."


def _last_logged_step_name(path: Path) -> str | None:
    steps_jsonl = path / "steps.jsonl"
    if not steps_jsonl.exists():
        return None
    last_step_name = None
    try:
        for line in steps_jsonl.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            if payload.get("step_name"):
                last_step_name = str(payload["step_name"])
    except (OSError, json.JSONDecodeError):
        return None
    return last_step_name


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _is_stale(value: datetime | None, stale_after: timedelta) -> bool:
    if value is None:
        return True
    return datetime.now(timezone.utc) - value > stale_after


def _process_status(pid: int) -> tuple[bool | None, float | None]:
    try:
        import psutil
    except ImportError:
        if pid == os.getpid():
            return True, _current_process_start_time()
        return _pid_exists_without_psutil(pid), None

    try:
        process = psutil.Process(pid)
        return process.is_running(), float(process.create_time())
    except psutil.NoSuchProcess:
        return False, None
    except psutil.AccessDenied:
        return True, None


def _current_process_start_time() -> float | None:
    try:
        import psutil
    except ImportError:
        return None
    try:
        return float(psutil.Process(os.getpid()).create_time())
    except Exception:  # noqa: BLE001
        return None


def _pid_exists_without_psutil(pid: int) -> bool | None:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        return _pid_exists_windows(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return None
    return True


def _pid_exists_windows(pid: int) -> bool | None:
    try:
        import ctypes
    except ImportError:
        return None
    kernel32 = ctypes.windll.kernel32
    process_query_limited_information = 0x1000
    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if handle:
        kernel32.CloseHandle(handle)
        return True
    error = kernel32.GetLastError()
    if error == 87:  # ERROR_INVALID_PARAMETER
        return False
    if error == 5:  # ERROR_ACCESS_DENIED
        return True
    return None


def _is_pyinstaller_bundle() -> bool:
    return bool(getattr(sys, "frozen", False)) and hasattr(sys, "_MEIPASS")
