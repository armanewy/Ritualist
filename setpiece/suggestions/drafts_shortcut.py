from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
import re

from setpiece.canvas import (
    CanvasBindingKind,
    CanvasComponent,
    CanvasComponentBinding,
    CanvasDocument,
    CanvasRuntimeContext,
    build_canvas_runtime_model,
    validate_canvas_structure,
)
from setpiece.suggestions.models import Suggestion, SuggestionKind
from setpiece.suggestions.review import require_approval_for_draft


SHORTCUT_DRAFT_SCHEMA_VERSION = "setpiece.shortcut_draft.v1"
SUPPORTED_SHORTCUT_COMPONENT_TYPES = frozenset(
    {
        "shortcut.folder",
        "shortcut.app",
        "shortcut.url",
    }
)

_BLOCKED_REVIEW_INPUT_KEYS = frozenset(
    {
        "args",
        "cmd",
        "code",
        "command",
        "exec",
        "executable",
        "html",
        "javascript",
        "js",
        "powershell",
        "python",
        "qml",
        "raw_command",
        "script",
        "shell",
        "subprocess",
    }
)
_TOKEN_RE = re.compile(r"[^a-z0-9]+")


class ShortcutDraftError(ValueError):
    """Base error for shortcut draft creation failures."""


class ShortcutDraftUnsupportedError(ShortcutDraftError):
    """Raised when a suggestion is not a supported shortcut draft."""


class ShortcutDraftValidationError(ShortcutDraftError):
    """Raised when reviewed shortcut data fails Canvas shortcut validation."""


def build_shortcut_draft(
    suggestion: Suggestion,
    *,
    reviewed_inputs: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Return a reviewed, unplaced shortcut component draft.

    The function is intentionally side-effect-free: it does not save the draft,
    attach it to a canvas, open targets, or dispatch any shortcut action.
    """

    approved = require_approval_for_draft(suggestion)
    inputs = _normalized_inputs(reviewed_inputs or {})
    _reject_raw_command_inputs(inputs)

    component_type = _shortcut_component_type(approved)
    target = _target_for(component_type, inputs)
    component = _component_for(approved, component_type, target)
    document = CanvasDocument(
        id="shortcut_draft_preview",
        name="Shortcut Draft Preview",
        components=(component,),
    )
    validation = validate_canvas_structure(document)
    _raise_for_validation_errors(validation.errors)
    runtime = build_canvas_runtime_model(
        document,
        context=CanvasRuntimeContext(
            recipe_ids=set(),
            target_ids=set(),
            recent_runs=(),
        ),
    )
    state = runtime.component_state(component.id)

    approval = approved.approval
    review_payload: dict[str, object] = {"required": True, "approved": True}
    if approval is not None:
        review_payload.update(
            {
                "review_token": approval.review_token,
                "reviewed_at": approval.reviewed_at,
                "artifact_summary": approval.artifact_summary,
            }
        )

    return {
        "schema_version": SHORTCUT_DRAFT_SCHEMA_VERSION,
        "suggestion_id": approved.id,
        "status": state.state,
        "component_type": component_type,
        "component": _unplaced_component_payload(component),
        "shortcut": {
            "kind": component_type.removeprefix("shortcut."),
            "action": "launch" if component_type == "shortcut.app" else "open",
            "target_configured": bool(target),
            "target_label": state.data.get("shortcut", {}).get("target_label", ""),
        },
        "missing_inputs": _missing_inputs(approved, component_type, state.state),
        "setup_issue": state.message if state.state == "needs_setup" else "",
        "review": review_payload,
        "validation": validation.to_dict(),
    }


def _normalized_inputs(values: Mapping[str, object]) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for key, value in values.items():
        normalized[_normalize_token(key)] = value
    return normalized


def _reject_raw_command_inputs(inputs: Mapping[str, object]) -> None:
    for key in inputs:
        if _token_matches_any(key, _BLOCKED_REVIEW_INPUT_KEYS):
            raise ShortcutDraftValidationError(
                f"Shortcut draft input {key!r} is not accepted; provide a reviewed "
                "folder path, app path, or http(s) URL instead."
            )


def _shortcut_component_type(suggestion: Suggestion) -> str:
    if suggestion.kind is not SuggestionKind.SHORTCUT_COMPONENT:
        raise ShortcutDraftUnsupportedError(
            f"Suggestion {suggestion.id!r} is not a shortcut component suggestion."
        )

    component_types: list[str] = []
    for action in suggestion.proposed_actions:
        if _normalize_token(action.get("action")) != "review_shortcut_component":
            continue
        for key in ("component_type", "kind", "type"):
            value = _canonical_shortcut_type(action.get(key))
            if value:
                component_types.append(value)
                break

    unique = tuple(dict.fromkeys(component_types))
    if len(unique) != 1:
        raise ShortcutDraftUnsupportedError(
            f"Suggestion {suggestion.id!r} must propose exactly one shortcut component type."
        )
    return unique[0]


def _canonical_shortcut_type(value: object) -> str:
    text = str(value or "").strip().casefold().replace("_", ".")
    if text in SUPPORTED_SHORTCUT_COMPONENT_TYPES:
        return text
    return ""


def _target_for(component_type: str, inputs: Mapping[str, object]) -> str:
    keys_by_type = {
        "shortcut.folder": ("folder_path", "folder", "path"),
        "shortcut.app": ("app_path", "app_target", "path"),
        "shortcut.url": ("url",),
    }
    for key in keys_by_type[component_type]:
        value = str(inputs.get(key) or "").strip()
        if value:
            return value
    return ""


def _component_for(
    suggestion: Suggestion,
    component_type: str,
    target: str,
) -> CanvasComponent:
    props: dict[str, object] = {"title": _title_for(suggestion, component_type)}
    binding: CanvasComponentBinding | None = None

    if target:
        if component_type == "shortcut.folder":
            props["path"] = target
            binding = CanvasComponentBinding(kind=CanvasBindingKind.SHORTCUT_FOLDER, path=target)
        elif component_type == "shortcut.app":
            props["path"] = target
            binding = CanvasComponentBinding(kind=CanvasBindingKind.SHORTCUT_APP, path=target)
        elif component_type == "shortcut.url":
            props["url"] = target
            binding = CanvasComponentBinding(kind=CanvasBindingKind.SHORTCUT_URL, url=target)

    return CanvasComponent(
        id=_component_id(suggestion, component_type),
        type=component_type,
        width=240,
        height=96,
        props=props,
        binding=binding,
    )


def _title_for(suggestion: Suggestion, component_type: str) -> str:
    for action in suggestion.proposed_actions:
        label = str(action.get("label") or action.get("title") or "").strip()
        if label and label != "[redacted]":
            return label
    title = suggestion.title.strip()
    if title and title != "[redacted]":
        return title
    return {
        "shortcut.folder": "Folder shortcut",
        "shortcut.app": "App shortcut",
        "shortcut.url": "URL shortcut",
    }[component_type]


def _component_id(suggestion: Suggestion, component_type: str) -> str:
    suffix = component_type.rsplit(".", maxsplit=1)[-1]
    digest = sha256(suggestion.id.encode("utf-8")).hexdigest()[:12]
    return f"shortcut_{suffix}_{digest}"


def _unplaced_component_payload(component: CanvasComponent) -> dict[str, object]:
    payload = component.to_dict()
    for key in ("x", "y", "z"):
        payload.pop(key, None)
    return payload


def _missing_inputs(
    suggestion: Suggestion,
    component_type: str,
    state: str,
) -> list[str]:
    missing = list(suggestion.missing_inputs)
    if state == "needs_setup":
        default = {
            "shortcut.folder": "folder_path",
            "shortcut.app": "app_target",
            "shortcut.url": "url",
        }[component_type]
        if default not in missing:
            missing.append(default)
    return missing


def _raise_for_validation_errors(errors: tuple[str, ...]) -> None:
    if errors:
        raise ShortcutDraftValidationError("; ".join(errors))


def _normalize_token(value: object) -> str:
    text = str(value or "")
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", text)
    text = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", "_", text)
    text = text.casefold()
    return _TOKEN_RE.sub("_", text).strip("_")


def _token_matches_any(value: str, tokens: frozenset[str]) -> bool:
    compact_value = value.replace("_", "")
    for token in tokens:
        if (
            value == token
            or value.startswith(f"{token}_")
            or value.endswith(f"_{token}")
            or f"_{token}_" in value
        ):
            return True
        compact_token = token.replace("_", "")
        if (
            compact_value == compact_token
            or compact_value.startswith(compact_token)
            or compact_value.endswith(compact_token)
            or compact_token in compact_value
        ):
            return True
    return False


__all__ = [
    "SHORTCUT_DRAFT_SCHEMA_VERSION",
    "ShortcutDraftError",
    "ShortcutDraftUnsupportedError",
    "ShortcutDraftValidationError",
    "build_shortcut_draft",
]
