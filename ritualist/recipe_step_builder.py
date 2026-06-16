from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml

from ritualist.actions.catalog import ActionCatalog, ActionCatalogEntry, create_action_catalog
from ritualist.errors import RecipeValidationError
from ritualist.models import SAFE_ID_PATTERN, Recipe
from ritualist.recipe_builder import RecipeBuilder
from ritualist.templating import collect_template_variables

BOOL_FIELDS = {
    "exact",
    "keep_open",
    "loop",
    "muted",
    "new_window",
    "optional",
    "play",
    "requires_confirmation",
    "wait",
}
FLOAT_FIELDS = {"seconds", "timeout_seconds"}
INT_FIELDS = {"height", "width", "x", "y"}
LIST_FIELDS = {"args", "evidence", "items", "keys"}
DICT_FIELDS = {"env"}
WORKFLOW_PREFIXES = (
    "app.",
    "browser.",
    "confirm.",
    "desktop.",
    "human.",
    "input.",
    "note.",
    "wait.",
    "window.",
)


@dataclass(frozen=True)
class RecipeStepCatalog:
    catalog: ActionCatalog

    @classmethod
    def default(cls) -> "RecipeStepCatalog":
        return cls(create_action_catalog())

    def categories(self) -> list[str]:
        return [
            category.name
            for category in self.catalog.categories
            if any(_is_workflow_action(entry.action_name) for entry in category.entries)
        ]

    def actions(self, *, category: str | None = None) -> list[ActionCatalogEntry]:
        entries = [entry for entry in self.catalog.entries if _is_workflow_action(entry.action_name)]
        if category:
            entries = [
                entry
                for entry in entries
                if self._category_for_action(entry.action_name) == category
            ]
        return sorted(entries, key=lambda entry: entry.display_name.casefold())

    def entry(self, action_name: str) -> ActionCatalogEntry:
        entry = self.catalog.entry(action_name)
        if not _is_workflow_action(entry.action_name):
            raise KeyError(f"action '{action_name}' is not a workflow step action")
        return entry

    def _category_for_action(self, action_name: str) -> str:
        for category in self.catalog.categories:
            if any(entry.action_name == action_name for entry in category.entries):
                return category.name
        return "System"


class RecipeStepBuilder:
    """Builds and validates structured recipe step dictionaries for editor UIs."""

    def __init__(self, catalog: RecipeStepCatalog | None = None) -> None:
        self.catalog = catalog or RecipeStepCatalog.default()

    def build_step(
        self,
        action_name: str,
        required_values: dict[str, object],
        optional_values: dict[str, object] | None = None,
    ) -> dict[str, Any]:
        entry = self.catalog.entry(action_name)
        values: dict[str, Any] = {"action": action_name}
        values.update(
            self._coerce_fields(
                entry.required_fields,
                required_values,
                required=True,
            )
        )
        values.update(
            self._coerce_fields(
                entry.optional_fields,
                optional_values or {},
                required=False,
            )
        )
        self._enforce_confirmation_defaults(values)
        self._validate_step(values)
        return values

    def _coerce_fields(
        self,
        field_names: Iterable[str],
        values: dict[str, object],
        *,
        required: bool,
    ) -> dict[str, Any]:
        coerced: dict[str, Any] = {}
        for field_name in field_names:
            raw = values.get(field_name)
            if raw is None or raw == "":
                if required:
                    raise RecipeValidationError(f"{field_name} is required")
                continue
            if not required and field_name in BOOL_FIELDS and raw is False:
                continue
            coerced[field_name] = _coerce_field_value(field_name, raw)
        return coerced

    def _enforce_confirmation_defaults(self, values: dict[str, Any]) -> None:
        if (
            values.get("action") == "desktop.click_text"
            and str(values.get("text", "")).strip().casefold() == "play"
        ):
            values["requires_confirmation"] = True

    def _validate_step(self, values: dict[str, Any]) -> None:
        Recipe.model_validate(
            {
                "id": "step_preview",
                "name": "Step Preview",
                "steps": [values],
            }
        )


class RecipeStepAppendController:
    """Saves wizard-created steps through the shared RecipeBuilder backend."""

    def append_step(
        self,
        recipe_path: str | Path,
        step_data: dict[str, Any],
        *,
        variable_updates: dict[str, Any] | None = None,
    ) -> Recipe:
        builder = RecipeBuilder.from_path(recipe_path)
        _apply_variable_updates(builder, filter_variable_updates_for_step(step_data, variable_updates))
        builder.add_step(step_data)
        return builder.save(recipe_path)

    def create_recipe_with_step(
        self,
        recipe_path: str | Path,
        step_data: dict[str, Any],
        *,
        name: str | None = None,
        variable_updates: dict[str, Any] | None = None,
    ) -> Recipe:
        path = Path(recipe_path)
        recipe_id = path.stem
        if not SAFE_ID_PATTERN.fullmatch(recipe_id):
            raise RecipeValidationError(
                "recipe filename must be a safe filename-like identifier "
                "(letters, numbers, hyphen, underscore)"
            )
        builder = RecipeBuilder.create(
            recipe_id,
            name or _name_from_id(recipe_id),
            variables=filter_variable_updates_for_step(step_data, variable_updates) or None,
        )
        builder.add_step(step_data)
        return builder.save(path)


def side_effect_label(entry: ActionCatalogEntry) -> str:
    warnings = "; ".join(entry.safety_warnings) if entry.safety_warnings else "No extra warnings"
    return f"Side effect: {entry.side_effect_label} | Safety: {warnings}"


def filter_variable_updates_for_step(
    step_data: dict[str, Any] | None,
    variable_updates: dict[str, Any] | None,
) -> dict[str, Any]:
    """Keep captured variable writes only when the accepted step still references them."""

    if not step_data or not variable_updates:
        return {}
    referenced = collect_template_variables(step_data)
    return {
        name: value
        for name, value in variable_updates.items()
        if name in referenced or any(variable.startswith(f"{name}.") for variable in referenced)
    }


def _coerce_field_value(field_name: str, raw: object) -> Any:
    if field_name in BOOL_FIELDS:
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            return raw.strip().casefold() in {"1", "true", "yes", "on"}
        return bool(raw)
    if field_name in FLOAT_FIELDS:
        return float(raw)
    if field_name in INT_FIELDS:
        return int(raw)
    if field_name in LIST_FIELDS:
        if isinstance(raw, list):
            return raw
        if not isinstance(raw, str):
            raise RecipeValidationError(f"{field_name} must be a list")
        return [item.strip() for item in raw.replace("\n", ",").split(",") if item.strip()]
    if field_name in DICT_FIELDS:
        if isinstance(raw, dict):
            return raw
        if not isinstance(raw, str):
            raise RecipeValidationError(f"{field_name} must be a mapping")
        loaded = yaml.safe_load(raw) if raw.strip() else {}
        if not isinstance(loaded, dict):
            raise RecipeValidationError(f"{field_name} must be a YAML mapping")
        return loaded
    return str(raw)


def _is_workflow_action(action_name: str) -> bool:
    return action_name.startswith(WORKFLOW_PREFIXES)


def _apply_variable_updates(
    builder: RecipeBuilder,
    variable_updates: dict[str, Any] | None,
) -> None:
    if not variable_updates:
        return
    document = builder.document
    variables = dict(document.get("variables") or {})
    variables.update(variable_updates)
    builder.update_metadata(variables=variables)


def _name_from_id(recipe_id: str) -> str:
    return recipe_id.replace("_", " ").replace("-", " ").title()
