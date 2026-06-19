from __future__ import annotations

import pytest

from setpiece.agent.activation import (
    ACTIVATION_INTENTS,
    ACTIVATION_SCHEMA_VERSION,
    ActivationIntent,
    ActivationIntentError,
    parse_activation_message,
    recipe_intent,
    room_intent,
    startup_silent_intent,
    validate_activation_payload,
)


@pytest.mark.parametrize(
    "intent",
    sorted(ACTIVATION_INTENTS - {"open_room", "run_recipe", "doctor_recipe", "dry_run_recipe"}),
)
def test_no_parameter_activation_intents_round_trip(intent: str) -> None:
    parsed = parse_activation_message(ActivationIntent(intent).to_bytes())

    assert parsed.intent == intent
    assert parsed.schema_version == ACTIVATION_SCHEMA_VERSION
    assert parsed.parameters == {}


@pytest.mark.parametrize("intent", ["run_recipe", "doctor_recipe", "dry_run_recipe"])
def test_recipe_activation_intents_require_safe_recipe_id(intent: str) -> None:
    parsed = parse_activation_message(recipe_intent(intent, "gaming_mode").to_bytes())

    assert parsed.intent == intent
    assert parsed.parameters == {"recipe_id": "gaming_mode"}


def test_open_room_activation_intent_requires_safe_room_id() -> None:
    parsed = parse_activation_message(room_intent("project_room").to_bytes())

    assert parsed.intent == "open_room"
    assert parsed.parameters == {"room_id": "project_room"}


def test_startup_silent_helper_uses_startup_intent() -> None:
    assert startup_silent_intent().to_payload() == {
        "schema_version": ACTIVATION_SCHEMA_VERSION,
        "intent": "startup_silent",
    }


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"schema_version": "setpiece.activation.v0", "intent": "open_picker"},
        {"schema_version": ACTIVATION_SCHEMA_VERSION, "intent": "open_home"},
        {
            "schema_version": ACTIVATION_SCHEMA_VERSION,
            "intent": "open_picker",
            "payload": {"command": "run"},
        },
        {
            "schema_version": ACTIVATION_SCHEMA_VERSION,
            "intent": "open_settings",
            "parameters": {"recipe_id": "gaming_mode"},
        },
        {
            "schema_version": ACTIVATION_SCHEMA_VERSION,
            "intent": "run_recipe",
            "parameters": {"recipe_id": "gaming_mode", "action": "shell"},
        },
        {
            "schema_version": ACTIVATION_SCHEMA_VERSION,
            "intent": "run_recipe",
            "parameters": {"recipe_id": "../gaming_mode"},
        },
        {
            "schema_version": ACTIVATION_SCHEMA_VERSION,
            "intent": "open_room",
            "parameters": {"room_id": "https://example.invalid/room"},
        },
    ],
)
def test_malformed_activation_payloads_are_rejected(payload: dict[str, object]) -> None:
    with pytest.raises(ActivationIntentError):
        validate_activation_payload(payload)


@pytest.mark.parametrize("message", [b"not-json", b'["open_picker"]'])
def test_malformed_activation_messages_are_rejected(message: bytes) -> None:
    with pytest.raises(ActivationIntentError):
        parse_activation_message(message)


def test_activation_intent_is_immutable_after_validation() -> None:
    intent = recipe_intent("dry_run_recipe", "gaming_mode")

    with pytest.raises(TypeError):
        intent.parameters["recipe_id"] = "other"  # type: ignore[index]
