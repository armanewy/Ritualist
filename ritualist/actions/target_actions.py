from __future__ import annotations

import time
from typing import Any

from ritualist.errors import RitualistError
from ritualist.models import TargetInspectStep, TargetWaitStateStep
from ritualist.target_resolution import (
    TargetResolutionResult,
    TargetState,
    build_target_plan_summary,
    compile_target_start_plan,
    resolve_target,
)

from .base import ActionContext, ActionOutcome
from .metadata import ALL_PLATFORMS, ActionMetadata


TARGET_READINESS_CAPABILITIES = ("process_inspection", "windows_uia")


class TargetInspectHandler:
    action_type = "target.inspect"
    metadata = ActionMetadata(
        action_name=action_type,
        schema_version="0.1",
        category="target",
        required_params=("target",),
        optional_params=("timeout_seconds", "name", "optional", "when"),
        required_capabilities=TARGET_READINESS_CAPABILITIES,
        supported_platforms=ALL_PLATFORMS,
        side_effect_level="read_only",
        confirmation_policy="never",
        allowed_in_imported_packs=True,
    )

    def run(self, step: TargetInspectStep, context: ActionContext) -> ActionOutcome:
        _cooperate(context)
        resolution = resolve_target(step.target)
        return ActionOutcome(
            message=_resolution_message(resolution),
            metadata=_resolution_metadata(step.target, resolution),
        )


class TargetWaitStateHandler:
    action_type = "target.wait_state"
    metadata = ActionMetadata(
        action_name=action_type,
        schema_version="0.1",
        category="target",
        required_params=("target",),
        optional_params=(
            "states",
            "readiness_states",
            "timeout_seconds",
            "name",
            "optional",
            "when",
        ),
        required_capabilities=TARGET_READINESS_CAPABILITIES,
        supported_platforms=ALL_PLATFORMS,
        side_effect_level="read_only",
        confirmation_policy="never",
        allowed_in_imported_packs=True,
    )

    def run(self, step: TargetWaitStateStep, context: ActionContext) -> ActionOutcome:
        timeout = step.timeout_seconds or 30.0
        expected_states = _target_states(step.states)
        expected_readiness = _normalized_set(step.readiness_states)
        deadline = time.monotonic() + timeout
        last_resolution: TargetResolutionResult | None = None

        while True:
            _cooperate(context)
            resolution = resolve_target(step.target)
            last_resolution = resolution
            if _resolution_matches(
                resolution,
                states=expected_states,
                readiness_states=expected_readiness,
            ):
                return ActionOutcome(
                    message=_resolution_message(resolution, prefix="target state matched"),
                    metadata=_resolution_metadata(step.target, resolution),
                )
            if timeout <= 0 or time.monotonic() >= deadline:
                break
            time.sleep(min(0.25, max(deadline - time.monotonic(), 0)))

        actual_state = last_resolution.state.value if last_resolution else "unknown"
        actual_readiness = _readiness_state(last_resolution)
        expected = [
            *(state.value for state in expected_states),
            *(f"readiness:{state}" for state in sorted(expected_readiness)),
        ]
        raise RitualistError(
            "target.wait_state timed out: "
            f"{step.target} was {actual_state}"
            + (f" / readiness:{actual_readiness}" if actual_readiness else "")
            + f"; expected one of {', '.join(expected)}"
        )


def create_target_handlers():
    return (TargetInspectHandler(), TargetWaitStateHandler())


def _resolution_matches(
    resolution: TargetResolutionResult,
    *,
    states: set[TargetState],
    readiness_states: set[str],
) -> bool:
    if resolution.state in states:
        return True
    readiness = _readiness_state(resolution)
    return bool(readiness and readiness.casefold() in readiness_states)


def _target_states(values: list[str]) -> set[TargetState]:
    states: set[TargetState] = set()
    for value in values:
        try:
            states.add(TargetState(value))
        except ValueError as exc:
            raise RitualistError(f"unsupported target state: {value}") from exc
    return states


def _readiness_state(resolution: TargetResolutionResult | None) -> str:
    if resolution is None or resolution.best_candidate is None:
        return ""
    readiness = resolution.best_candidate.details.get("readiness")
    if not isinstance(readiness, dict):
        return ""
    return str(readiness.get("state") or "").strip()


def _normalized_set(values: list[str]) -> set[str]:
    return {value.strip().casefold() for value in values if value.strip()}


def _resolution_message(
    resolution: TargetResolutionResult,
    *,
    prefix: str = "target inspected",
) -> str:
    target_name = resolution.target.display_name if resolution.target else resolution.query
    readiness = _readiness_state(resolution)
    suffix = f" / readiness:{readiness}" if readiness else ""
    return f"{prefix}: {target_name} is {resolution.state.value}{suffix}"


def _resolution_metadata(target: str, resolution: TargetResolutionResult) -> dict[str, Any]:
    plan = compile_target_start_plan(target, resolution=resolution)
    summary = build_target_plan_summary(resolution, plan)
    return {
        "target_resolution": resolution.to_dict(),
        "target_plan_summary": summary.to_dict(),
    }


def _cooperate(context: ActionContext) -> None:
    if context.runtime_control is not None:
        context.runtime_control.heartbeat()
    if context.heartbeat is not None:
        context.heartbeat()
