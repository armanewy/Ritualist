from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .actions.base import ActionContext
from .models import Condition
from .target_resolution import TargetResolutionResult, TargetState, resolve_target


@dataclass(frozen=True)
class PredicateResult:
    matched: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_metadata(self) -> dict[str, Any]:
        return {
            "matched": self.matched,
            "message": self.message,
            "details": self.details,
        }


def evaluate_condition(condition: Condition, context: ActionContext) -> PredicateResult:
    _cooperate(context)
    if condition.type == "value.equals":
        matched = condition.left == condition.right
        return PredicateResult(
            matched=matched,
            message="values matched" if matched else "values did not match",
            details={
                "type": condition.type,
                "left": _safe_value(condition.left),
                "right": _safe_value(condition.right),
            },
        )
    if condition.all is not None:
        results = [evaluate_condition(child, context) for child in condition.all]
        matched = all(result.matched for result in results)
        return PredicateResult(
            matched=matched,
            message="all conditions matched" if matched else "one or more conditions did not match",
            details={"operator": "all", "results": [result.to_metadata() for result in results]},
        )
    if condition.any is not None:
        results = [evaluate_condition(child, context) for child in condition.any]
        matched = any(result.matched for result in results)
        return PredicateResult(
            matched=matched,
            message="at least one condition matched" if matched else "no conditions matched",
            details={"operator": "any", "results": [result.to_metadata() for result in results]},
        )
    if condition.not_ is not None:
        result = evaluate_condition(condition.not_, context)
        matched = not result.matched
        return PredicateResult(
            matched=matched,
            message="condition was not matched" if matched else "negated condition matched",
            details={"operator": "not", "result": result.to_metadata()},
        )
    if condition.type == "file.exists":
        path = _expand_path(condition.path or "")
        matched = path.is_file()
        return PredicateResult(
            matched=matched,
            message=f"file exists: {path}" if matched else f"file does not exist: {path}",
            details={"type": condition.type, "path": str(path)},
        )
    if condition.type == "path.exists":
        path = _expand_path(condition.path or "")
        matched = path.exists()
        return PredicateResult(
            matched=matched,
            message=f"path exists: {path}" if matched else f"path does not exist: {path}",
            details={"type": condition.type, "path": str(path)},
        )
    if condition.type == "process.running":
        process_name = condition.process_name or ""
        matched = bool(context.adapters.shell.process_running(process_name, timeout_seconds=0))
        return PredicateResult(
            matched=matched,
            message=(
                f"process is running: {process_name}"
                if matched
                else f"process is not running: {process_name}"
            ),
            details={"type": condition.type, "process_name": process_name},
        )
    if condition.type == "window.exists":
        matched = bool(
            context.adapters.window.window_exists(
                title_contains=condition.title_contains,
                process_name=condition.process_name,
                timeout_seconds=0,
            )
        )
        target = condition.title_contains or condition.process_name or "window"
        return PredicateResult(
            matched=matched,
            message=f"window exists: {target}" if matched else f"window not found: {target}",
            details={
                "type": condition.type,
                "title_contains": condition.title_contains,
                "process_name": condition.process_name,
            },
        )
    if condition.type == "window.text_visible":
        window = condition.window_title_contains or ""
        text = condition.text or ""
        matched = bool(
            context.adapters.desktop.text_visible(
                text=text,
                window_title_contains=window,
                control_type=condition.control_type,
                exact=condition.exact,
                timeout_seconds=0,
            )
        )
        return PredicateResult(
            matched=matched,
            message=(
                f"visible window text found: {text}"
                if matched
                else f"visible window text not found in '{window}': {text}"
            ),
            details={
                "type": condition.type,
                "window_title_contains": window,
                "text": text,
                "control_type": condition.control_type,
                "exact": condition.exact,
            },
        )
    if condition.type == "browser.text_visible":
        text = condition.text or ""
        matched = bool(
            context.adapters.browser.text_visible(
                text=text,
                exact=condition.exact,
                timeout_seconds=0,
            )
        )
        return PredicateResult(
            matched=matched,
            message=(
                f"visible browser text found: {text}"
                if matched
                else f"visible browser text not found: {text}"
            ),
            details={"type": condition.type, "text": text, "exact": condition.exact},
        )
    if condition.type == "target.state":
        target = condition.target or ""
        resolution = resolve_target(target)
        expected = _target_states(condition.state, condition.states)
        matched = resolution.state in expected
        return PredicateResult(
            matched=matched,
            message=(
                f"target state matched: {target} is {resolution.state.value}"
                if matched
                else f"target state did not match: {target} is {resolution.state.value}"
            ),
            details={
                "type": condition.type,
                "target": target,
                "state": resolution.state.value,
                "expected": sorted(state.value for state in expected),
                "readiness_state": _readiness_state(resolution),
                "matched_candidate": _candidate_summary(resolution),
            },
        )
    if condition.type == "target.readiness_state":
        target = condition.target or ""
        resolution = resolve_target(target)
        readiness = _readiness_state(resolution)
        expected = _normalized_states(condition.readiness_state, condition.readiness_states)
        matched = bool(readiness and readiness in expected)
        return PredicateResult(
            matched=matched,
            message=(
                f"target readiness matched: {target} is {readiness}"
                if matched
                else f"target readiness did not match: {target} is {readiness or 'unavailable'}"
            ),
            details={
                "type": condition.type,
                "target": target,
                "state": resolution.state.value,
                "readiness_state": readiness,
                "expected": sorted(expected),
                "matched_candidate": _candidate_summary(resolution),
            },
        )
    return PredicateResult(
        matched=False,
        message="condition type is not supported",
        details={"type": condition.type},
    )


def _cooperate(context: ActionContext) -> None:
    if context.runtime_control is not None:
        context.runtime_control.heartbeat()
    if context.heartbeat is not None:
        context.heartbeat()


def _expand_path(raw: str) -> Path:
    expanded = os.path.expanduser(os.path.expandvars(raw))

    def replace_percent_var(match: re.Match[str]) -> str:
        key = match.group(1)
        return os.environ.get(key, match.group(0))

    return Path(re.sub(r"%([^%]+)%", replace_percent_var, expanded))


def _target_states(state: str | None, states: list[str] | None) -> set[TargetState]:
    values = [*(states or [])]
    if state:
        values.append(state)
    resolved: set[TargetState] = set()
    for value in values:
        resolved.add(TargetState(value))
    return resolved


def _normalized_states(state: str | None, states: list[str] | None) -> set[str]:
    values = [*(states or [])]
    if state:
        values.append(state)
    return {value.strip().casefold() for value in values if value.strip()}


def _readiness_state(resolution: TargetResolutionResult) -> str:
    candidate = resolution.best_candidate
    if candidate is None:
        return ""
    readiness = candidate.details.get("readiness")
    if not isinstance(readiness, dict):
        return ""
    return str(readiness.get("state") or "").strip()


def _candidate_summary(resolution: TargetResolutionResult) -> dict[str, Any]:
    candidate = resolution.best_candidate
    if candidate is None:
        return {}
    return {
        "candidate_id": candidate.candidate_id,
        "provider": candidate.provider,
        "state": candidate.state.value,
        "label": candidate.label,
    }


def _safe_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
