from __future__ import annotations

import queue
import threading
import time
from typing import Any

from setpiece.errors import SetpieceError, UserCancelledError
from setpiece.models import (
    HumanChecklistStep,
    HumanConfirmEvidenceStep,
    HumanPromptStep,
    NoteAddStep,
)
from setpiece.overlay import ConfirmationRequest

from .base import ActionContext, ActionOutcome
from .metadata import ALL_PLATFORMS, ActionMetadata


POLL_INTERVAL_SECONDS = 0.1


class HumanPromptHandler:
    action_type = "human.prompt"
    metadata = ActionMetadata(
        action_name=action_type,
        schema_version="0.1",
        category="human",
        required_params=("prompt",),
        optional_params=("timeout_seconds", "name", "optional"),
        required_capabilities=(),
        supported_platforms=ALL_PLATFORMS,
        side_effect_level="read_only",
        confirmation_policy="always",
        allowed_in_imported_packs=True,
    )

    def run(self, step: HumanPromptStep, context: ActionContext) -> ActionOutcome:
        _cooperate(context)
        accepted = _confirm_operator(
            _request(step.prompt, step=step, context=context),
            context=context,
            timeout_seconds=step.timeout_seconds,
            timeout_message=_timeout_message(step.action, step.timeout_seconds),
        )
        if not accepted:
            raise UserCancelledError("operator declined prompt")
        _cooperate(context)
        return ActionOutcome(
            message="operator acknowledged prompt",
            metadata=_operator_metadata(step.action, response="acknowledged"),
        )


class HumanChecklistHandler:
    action_type = "human.checklist"
    metadata = ActionMetadata(
        action_name=action_type,
        schema_version="0.1",
        category="human",
        required_params=("prompt", "items"),
        optional_params=("timeout_seconds", "name", "optional"),
        required_capabilities=(),
        supported_platforms=ALL_PLATFORMS,
        side_effect_level="read_only",
        confirmation_policy="always",
        allowed_in_imported_packs=True,
    )

    def run(self, step: HumanChecklistStep, context: ActionContext) -> ActionOutcome:
        _cooperate(context)
        accepted = _confirm_operator(
            _request(_checklist_prompt(step), step=step, context=context),
            context=context,
            timeout_seconds=step.timeout_seconds,
            timeout_message=_timeout_message(step.action, step.timeout_seconds),
        )
        if not accepted:
            raise UserCancelledError("operator declined checklist")
        _cooperate(context)
        return ActionOutcome(
            message="operator completed checklist",
            metadata=_operator_metadata(
                step.action,
                response="completed",
                item_count=len(step.items),
            ),
        )


class HumanConfirmEvidenceHandler:
    action_type = "human.confirm_evidence"
    metadata = ActionMetadata(
        action_name=action_type,
        schema_version="0.1",
        category="human",
        required_params=("prompt", "evidence"),
        optional_params=("timeout_seconds", "name", "optional"),
        required_capabilities=(),
        supported_platforms=ALL_PLATFORMS,
        side_effect_level="read_only",
        confirmation_policy="always",
        allowed_in_imported_packs=True,
    )

    def run(self, step: HumanConfirmEvidenceStep, context: ActionContext) -> ActionOutcome:
        _cooperate(context)
        accepted = _confirm_operator(
            _request(_evidence_prompt(step), step=step, context=context),
            context=context,
            timeout_seconds=step.timeout_seconds,
            timeout_message=_timeout_message(step.action, step.timeout_seconds),
        )
        if not accepted:
            raise UserCancelledError("operator declined evidence confirmation")
        _cooperate(context)
        return ActionOutcome(
            message="operator confirmed evidence",
            metadata=_operator_metadata(
                step.action,
                response="confirmed",
                evidence_count=len(step.evidence),
            ),
        )


class NoteAddHandler:
    action_type = "note.add"
    metadata = ActionMetadata(
        action_name=action_type,
        schema_version="0.1",
        category="note",
        required_params=("text",),
        optional_params=("name", "optional"),
        required_capabilities=(),
        supported_platforms=ALL_PLATFORMS,
        side_effect_level="read_only",
        confirmation_policy="never",
        allowed_in_imported_packs=True,
    )

    def run(self, step: NoteAddStep, context: ActionContext) -> ActionOutcome:
        _cooperate(context)
        text = step.text.strip()
        return ActionOutcome(
            message="note recorded",
            metadata={
                "note": {
                    "action": step.action,
                    "recorded": True,
                    "text_redacted": True,
                    "text_length": len(text),
                }
            },
        )


def create_human_handlers():
    return (
        HumanPromptHandler(),
        HumanChecklistHandler(),
        HumanConfirmEvidenceHandler(),
        NoteAddHandler(),
    )


def _request(prompt: str, *, step: Any, context: ActionContext) -> ConfirmationRequest:
    return ConfirmationRequest(
        prompt=prompt,
        action=step.action,
        step_name=step.display_name,
        recipe_name=context.recipe.name,
    )


def _checklist_prompt(step: HumanChecklistStep) -> str:
    lines = [step.prompt, "", "Confirm after completing every item:"]
    lines.extend(f"- {item}" for item in step.items)
    return "\n".join(lines)


def _evidence_prompt(step: HumanConfirmEvidenceStep) -> str:
    lines = [step.prompt, "", "Confirm the evidence is present:"]
    lines.extend(f"- {item}" for item in step.evidence)
    return "\n".join(lines)


def _operator_metadata(action: str, *, response: str, **extra: Any) -> dict[str, Any]:
    return {
        "operator_response": {
            "action": action,
            "response": response,
            **extra,
        }
    }


def _confirm_operator(
    request: ConfirmationRequest,
    *,
    context: ActionContext,
    timeout_seconds: float | None,
    timeout_message: str,
) -> bool:
    if timeout_seconds is None:
        return context.confirm(request)

    results: queue.Queue[tuple[str, object]] = queue.Queue(maxsize=1)

    def run_confirmation() -> None:
        try:
            results.put(("result", context.confirm(request)))
        except Exception as exc:  # noqa: BLE001 - re-raised in runtime thread.
            results.put(("error", exc))

    thread = threading.Thread(target=run_confirmation, daemon=True)
    thread.start()
    deadline = time.monotonic() + timeout_seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise SetpieceError(timeout_message)
        try:
            kind, value = results.get(timeout=min(POLL_INTERVAL_SECONDS, remaining))
        except queue.Empty:
            _cooperate(context)
            continue
        if kind == "error":
            if isinstance(value, BaseException):
                raise value
            raise SetpieceError(str(value))
        return bool(value)


def _timeout_message(action: str, timeout_seconds: float | None) -> str:
    if timeout_seconds is None:
        return f"{action} timed out"
    return f"{action} timed out after {timeout_seconds:g}s"


def _cooperate(context: ActionContext) -> None:
    if context.runtime_control is not None:
        context.runtime_control.heartbeat()
    if context.heartbeat is not None:
        context.heartbeat()
