from __future__ import annotations

import pytest

from ritualist.actions.catalog import (
    CATALOG_CATEGORY_NAMES,
    SIDE_EFFECT_LABELS,
    ActionCatalogEntry,
    create_action_catalog,
)
from ritualist.actions.registry import ActionRegistry, create_default_registry


def test_action_catalog_contains_all_registered_actions() -> None:
    registry = create_default_registry()
    catalog = create_action_catalog(registry)

    assert [entry.action_name for entry in catalog.entries] == registry.action_types()
    assert {category.name for category in catalog.categories} == set(CATALOG_CATEGORY_NAMES)
    assert tuple(category.name for category in catalog.categories) == CATALOG_CATEGORY_NAMES


def test_action_catalog_entries_include_required_gui_fields() -> None:
    catalog = create_action_catalog()

    for entry in catalog.entries:
        assert isinstance(entry, ActionCatalogEntry)
        assert entry.display_name
        assert entry.description
        assert isinstance(entry.required_fields, tuple)
        assert isinstance(entry.optional_fields, tuple)
        assert entry.side_effect_level
        assert entry.side_effect_label == SIDE_EFFECT_LABELS[entry.side_effect_level]
        assert isinstance(entry.safety_warnings, tuple)


def test_action_catalog_preserves_safety_warnings() -> None:
    catalog = create_action_catalog()

    click_text = catalog.entry("desktop.click_text")
    assert click_text.category == "Desktop UI"
    assert click_text.side_effect_level == "risky"
    assert "Clicking text exactly equal to Play requires confirmation" in click_text.safety_warnings
    assert "Requires window_title_contains" in click_text.safety_warnings


def test_action_catalog_rejects_missing_metadata() -> None:
    class MissingMetadataHandler:
        action_type = "test.missing_metadata"

        def run(self, step, context):
            return "unused"

    registry = ActionRegistry()
    registry._handlers[MissingMetadataHandler.action_type] = MissingMetadataHandler()

    with pytest.raises(ValueError, match="must declare ActionMetadata"):
        create_action_catalog(registry)
