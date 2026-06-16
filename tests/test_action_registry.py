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
        "wait.for_file",
        "wait.for_process",
        "wait.for_process_exit",
        "wait.for_user",
        "wait.for_window",
        "wait.for_window_gone",
        "wait.seconds",
        "window.focus",
        "window.maximize",
        "window.minimize",
        "window.move",
        "window.resize",
        "window.restore",
        "window.snap_bottom",
        "window.snap_left",
        "window.snap_right",
        "window.snap_top",
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


def test_window_layout_action_metadata_requires_title_scope():
    registry = create_default_registry()
    layout_actions = {
        "window.move",
        "window.resize",
        "window.restore",
        "window.snap_left",
        "window.snap_right",
        "window.snap_top",
        "window.snap_bottom",
    }

    for action in layout_actions:
        metadata = registry.metadata(action)
        assert "title_contains" in metadata.required_params
        assert "process_name" not in metadata.optional_params
        assert metadata.allowed_in_imported_packs is False
        assert metadata.side_effect_level == "controls_ui"


def test_window_maximize_metadata_preserves_process_match_scope():
    metadata = create_default_registry().metadata("window.maximize")

    assert metadata.required_params == ()
    assert "title_contains" in metadata.optional_params
    assert "process_name" in metadata.optional_params


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
