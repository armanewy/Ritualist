from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping
import json
import re


ACTIVATION_SCHEMA_VERSION = "setpiece.activation.v1"
MAX_ACTIVATION_MESSAGE_BYTES = 8192

ACTIVATION_INTENTS = frozenset(
    {
        "startup_silent",
        "open_picker",
        "open_active_ritual",
        "open_settings",
        "open_builder",
        "open_run_log",
        "open_room",
        "run_recipe",
        "doctor_recipe",
        "dry_run_recipe",
        "exit",
    }
)

RECIPE_INTENTS = frozenset({"run_recipe", "doctor_recipe", "dry_run_recipe"})
ROOM_INTENTS = frozenset({"open_room"})
NO_PARAMETER_INTENTS = ACTIVATION_INTENTS - RECIPE_INTENTS - ROOM_INTENTS

_SAFE_LOCAL_REFERENCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")


class ActivationIntentError(ValueError):
    """Raised when a local activation intent does not match the public schema."""


@dataclass(frozen=True)
class ActivationIntent:
    """Versioned, local-only activation intent for single-instance redirection.

    The shape intentionally carries only a bounded intent name and small local
    references. It is not an execution channel for arbitrary commands or action
    payloads.
    """

    intent: str
    parameters: Mapping[str, str] = field(default_factory=dict)
    schema_version: str = ACTIVATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        validated = validate_activation_payload(
            {
                "schema_version": self.schema_version,
                "intent": self.intent,
                "parameters": dict(self.parameters),
            }
        )
        object.__setattr__(self, "intent", validated.intent)
        object.__setattr__(self, "parameters", MappingProxyType(dict(validated.parameters)))
        object.__setattr__(self, "schema_version", validated.schema_version)

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "intent": self.intent,
        }
        if self.parameters:
            payload["parameters"] = dict(self.parameters)
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_payload(), sort_keys=True, separators=(",", ":"))

    def to_bytes(self) -> bytes:
        data = self.to_json().encode("utf-8")
        if len(data) > MAX_ACTIVATION_MESSAGE_BYTES:
            raise ActivationIntentError("activation intent is too large")
        return data


def startup_silent_intent() -> ActivationIntent:
    return ActivationIntent("startup_silent")


def recipe_intent(intent: str, recipe_id: str) -> ActivationIntent:
    return ActivationIntent(intent, {"recipe_id": recipe_id})


def room_intent(room_id: str) -> ActivationIntent:
    return ActivationIntent("open_room", {"room_id": room_id})


def validate_activation_payload(payload: Mapping[str, Any]) -> ActivationIntent:
    if not isinstance(payload, Mapping):
        raise ActivationIntentError("activation payload must be an object")

    allowed_top_level = {"schema_version", "intent", "parameters"}
    extra_top_level = set(payload) - allowed_top_level
    if extra_top_level:
        raise ActivationIntentError(
            f"activation payload has unsupported fields: {', '.join(sorted(extra_top_level))}"
        )

    schema_version = payload.get("schema_version")
    if schema_version != ACTIVATION_SCHEMA_VERSION:
        raise ActivationIntentError("unsupported activation schema version")

    intent = payload.get("intent")
    if not isinstance(intent, str) or intent not in ACTIVATION_INTENTS:
        raise ActivationIntentError("unsupported activation intent")

    parameters = payload.get("parameters", {})
    if not isinstance(parameters, Mapping):
        raise ActivationIntentError("activation parameters must be an object")

    cleaned_parameters = _validate_parameters(intent, parameters)
    return _validated_intent(intent=intent, parameters=cleaned_parameters)


def parse_activation_message(message: bytes | bytearray | memoryview | str) -> ActivationIntent:
    if isinstance(message, str):
        raw = message.encode("utf-8")
    else:
        raw = bytes(message)
    if len(raw) > MAX_ACTIVATION_MESSAGE_BYTES:
        raise ActivationIntentError("activation intent is too large")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ActivationIntentError("activation message must be valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ActivationIntentError("activation payload must be an object")
    return validate_activation_payload(payload)


def _validate_parameters(intent: str, parameters: Mapping[str, Any]) -> dict[str, str]:
    if intent in NO_PARAMETER_INTENTS:
        if parameters:
            raise ActivationIntentError(f"{intent} does not accept parameters")
        return {}

    if intent in RECIPE_INTENTS:
        return _validate_exact_reference(parameters, field_name="recipe_id")

    if intent in ROOM_INTENTS:
        return _validate_exact_reference(parameters, field_name="room_id")

    raise ActivationIntentError("unsupported activation intent")


def _validate_exact_reference(parameters: Mapping[str, Any], *, field_name: str) -> dict[str, str]:
    if set(parameters) != {field_name}:
        raise ActivationIntentError(f"activation parameters must contain only {field_name}")
    value = parameters[field_name]
    if not isinstance(value, str) or not _SAFE_LOCAL_REFERENCE.fullmatch(value):
        raise ActivationIntentError(f"{field_name} must be a safe local identifier")
    return {field_name: value}


def _validated_intent(intent: str, parameters: Mapping[str, str]) -> ActivationIntent:
    instance = object.__new__(ActivationIntent)
    object.__setattr__(instance, "intent", intent)
    object.__setattr__(instance, "parameters", MappingProxyType(dict(parameters)))
    object.__setattr__(instance, "schema_version", ACTIVATION_SCHEMA_VERSION)
    return instance
