from __future__ import annotations

import pytest

from ritualist.actions.metadata import (
    ALLOWED_CATEGORIES,
    ALLOWED_CONFIRMATION_POLICIES,
    ALLOWED_PLATFORMS,
    ALLOWED_SIDE_EFFECT_LEVELS,
    ActionMetadata,
)
from ritualist.actions.registry import ActionRegistry
from ritualist.actions.registry import create_default_registry


def test_default_registry_contains_supported_actions():
    registry = create_default_registry()

    assert registry.action_types() == [
        "app.launch",
        "app.wait_process",
        "assert.browser_text_visible",
        "assert.file_exists",
        "assert.path_exists",
        "assert.process_running",
        "assert.registry_value",
        "assert.window_exists",
        "assert.window_text_visible",
        "browser.media",
        "browser.open",
        "confirm.ask",
        "desktop.click_text",
        "input.hotkey",
        "window.focus",
        "window.maximize",
        "window.minimize",
        "window.wait",
    ]


def test_registered_actions_declare_metadata():
    registry = create_default_registry()
    required_fields = {
        "action_name",
        "schema_version",
        "category",
        "required_capabilities",
        "supported_platforms",
        "side_effect_level",
        "allowed_in_imported_packs",
        "confirmation_policy",
    }

    for action_type in registry.action_types():
        metadata = registry.metadata(action_type)
        serialized = metadata.to_dict()
        assert required_fields <= serialized.keys()
        assert metadata.action_name == action_type
        assert metadata.action == action_type
        assert metadata.schema_version == "0.1"
        assert metadata.category in ALLOWED_CATEGORIES
        assert isinstance(metadata.required_capabilities, tuple)
        assert all(capability for capability in metadata.required_capabilities)
        assert metadata.supported_platforms
        assert all(platform in ALLOWED_PLATFORMS for platform in metadata.supported_platforms)
        assert metadata.side_effect_level in ALLOWED_SIDE_EFFECT_LEVELS
        assert metadata.confirmation_policy in ALLOWED_CONFIRMATION_POLICIES
        assert isinstance(metadata.allowed_in_imported_packs, bool)


def test_registry_rejects_missing_metadata():
    class MissingMetadataHandler:
        action_type = "test.missing_metadata"

        def run(self, step, context):
            return "unused"

    with pytest.raises(ValueError, match="must declare ActionMetadata"):
        ActionRegistry().register(MissingMetadataHandler())


def test_action_metadata_rejects_unknown_values():
    with pytest.raises(ValueError, match="side_effect_level"):
        ActionMetadata(
            action_name="test.bad_effect",
            schema_version="0.1",
            category="app",
            required_params=(),
            optional_params=(),
            required_capabilities=(),
            supported_platforms=("windows",),
            side_effect_level="executes_code",
            confirmation_policy="never",
            allowed_in_imported_packs=False,
        )
