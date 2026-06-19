from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from enum import StrEnum
from typing import Any

from setpiece.agent.instrument_model import (
    InstrumentAction,
    InstrumentActionRole,
    InstrumentModel,
    InstrumentSources,
    InstrumentState,
    build_instrument_model,
)


INSTRUMENT_PRESENTATION_SCHEMA_VERSION = "setpiece.agent.instrument.presentation.v1"


@dataclass(frozen=True, slots=True)
class PresentedRow:
    label: str
    text: str
    severity: str = "info"

    def to_dict(self) -> dict[str, Any]:
        return _dataclass_to_dict(self)


@dataclass(frozen=True, slots=True)
class PresentedSection:
    title: str
    rows: tuple[PresentedRow, ...] = ()
    collapsed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return _dataclass_to_dict(self)


@dataclass(frozen=True, slots=True)
class PresentedInstrument:
    schema_version: str
    state: InstrumentState
    title: str
    subtitle: str
    primary_actions: tuple[InstrumentAction, ...]
    secondary_actions: tuple[InstrumentAction, ...]
    sections: tuple[PresentedSection, ...]
    compact_history: bool = True

    def to_dict(self) -> dict[str, Any]:
        return _dataclass_to_dict(self)


def build_instrument_presentation(
    sources: InstrumentSources | None = None,
    **overrides: Any,
) -> PresentedInstrument:
    return present_instrument(build_instrument_model(sources, **overrides))


def present_instrument(model: InstrumentModel) -> PresentedInstrument:
    sections = [_overview_section(model)]
    state_section = _state_section(model)
    if state_section is not None:
        sections.append(state_section)
    history_section = _history_section(model)
    if history_section is not None:
        sections.append(history_section)
    return PresentedInstrument(
        schema_version=INSTRUMENT_PRESENTATION_SCHEMA_VERSION,
        state=model.state,
        title=model.headline,
        subtitle=model.subheadline,
        primary_actions=tuple(
            action for action in model.actions if action.role == InstrumentActionRole.PRIMARY
        ),
        secondary_actions=tuple(
            action for action in model.actions if action.role != InstrumentActionRole.PRIMARY
        ),
        sections=tuple(sections),
        compact_history=model.history.collapsed,
    )


def _overview_section(model: InstrumentModel) -> PresentedSection:
    rows = [
        PresentedRow("Ritual", model.ritual_name),
        PresentedRow("Intent", model.intent),
    ]
    rows.extend(PresentedRow(fact.label, fact.value, fact.severity) for fact in model.facts)
    if model.affected:
        rows.append(PresentedRow("Affected apps/settings", "; ".join(model.affected)))
    if model.prerequisites:
        rows.append(PresentedRow("Prerequisites", "; ".join(model.prerequisites)))
    if model.warnings:
        rows.append(PresentedRow("Warnings", "; ".join(model.warnings), "warning"))
    return PresentedSection("Overview", tuple(rows))


def _state_section(model: InstrumentModel) -> PresentedSection | None:
    if model.state == InstrumentState.RUNNING:
        rows = [
            PresentedRow("Current", model.current_verb or "Running"),
            PresentedRow("Step", _step_label(model)),
            PresentedRow("Elapsed", _duration(model.progress.elapsed_seconds)),
        ]
        if model.next_step:
            rows.append(PresentedRow("Next", model.next_step))
        return PresentedSection("Running", tuple(row for row in rows if row.text))

    if model.state == InstrumentState.WAITING and model.wait is not None:
        rows = [
            PresentedRow("Dependency", model.wait.dependency),
            PresentedRow(
                "User action",
                "Required" if model.wait.user_action_required else "Not required",
            ),
            PresentedRow("Elapsed", _duration(model.wait.elapsed_seconds)),
            PresentedRow("Timeout", _duration(model.wait.timeout_seconds)),
            PresentedRow("Next check", _duration(model.wait.next_check_seconds)),
        ]
        return PresentedSection("Waiting", tuple(row for row in rows if row.text))

    if model.state == InstrumentState.CONFIRMATION and model.confirmation is not None:
        confirmation = model.confirmation
        rows = [
            PresentedRow("Consequence", confirmation.consequence),
            PresentedRow("Target", confirmation.target),
            PresentedRow("Preserved work", confirmation.preserved_work),
            PresentedRow("Safe negative path", confirmation.safe_negative_path),
            PresentedRow(
                "Remembered approval",
                confirmation.remembered_approval_summary,
                "info" if confirmation.remembered_approval_eligible else "warning",
            ),
        ]
        return PresentedSection("Confirmation", tuple(row for row in rows if row.text))

    if model.state == InstrumentState.FAILURE and model.failure is not None:
        failure = model.failure
        rows = [
            PresentedRow("Failed step", failure.failed_step, "error"),
            PresentedRow("Cause", failure.cause, "error"),
            PresentedRow("Completed work", failure.completed_work),
            PresentedRow("Steps not run", str(failure.steps_not_run)),
            PresentedRow("Remedy", failure.remedy),
            PresentedRow("Run log", failure.run_log_path),
        ]
        return PresentedSection("Failure", tuple(row for row in rows if row.text))

    if (
        model.state in {InstrumentState.RECOVERY, InstrumentState.INTERRUPTED}
        and model.recovery is not None
    ):
        recovery = model.recovery
        rows = [
            PresentedRow("Checkpoint", recovery.checkpoint),
            PresentedRow("Repair steps", "; ".join(recovery.repair_steps)),
            PresentedRow("Progress", recovery.progress),
        ]
        return PresentedSection("Recovery", tuple(row for row in rows if row.text))

    return None


def _history_section(model: InstrumentModel) -> PresentedSection | None:
    if not model.history.summary:
        return None
    if model.history.collapsed:
        return PresentedSection(
            "History",
            (PresentedRow("Interrupted run", model.history.summary),),
            collapsed=True,
        )
    return PresentedSection(
        "History",
        (
            PresentedRow("Interrupted run", model.history.summary),
            *(PresentedRow("Step", entry) for entry in model.history.entries),
        ),
        collapsed=False,
    )


def _step_label(model: InstrumentModel) -> str:
    index = model.progress.step_index
    total = model.progress.total_steps
    if index is None or total <= 0:
        return ""
    return f"{index} of {total}"


def _duration(value: float | None) -> str:
    if value is None:
        return ""
    total = int(max(0, value))
    minutes, seconds = divmod(total, 60)
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def _dataclass_to_dict(instance: object) -> dict[str, Any]:
    return {field.name: _to_json_value(getattr(instance, field.name)) for field in fields(instance)}


def _to_json_value(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if is_dataclass(value):
        return _dataclass_to_dict(value)
    if isinstance(value, tuple):
        return [_to_json_value(item) for item in value]
    if isinstance(value, list):
        return [_to_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _to_json_value(item) for key, item in value.items()}
    return value


__all__ = [
    "INSTRUMENT_PRESENTATION_SCHEMA_VERSION",
    "PresentedInstrument",
    "PresentedRow",
    "PresentedSection",
    "build_instrument_presentation",
    "present_instrument",
]
