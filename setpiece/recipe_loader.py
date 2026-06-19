from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

import yaml
from pydantic import ValidationError

from .errors import RecipeValidationError, SafetyError, TemplateError
from .models import SAFE_ID_PATTERN, Recipe
from .paths import recipes_dir
from .templating import collect_template_variables, render_template_data


def load_recipe(path: str | Path, overrides: Mapping[str, Any] | None = None) -> Recipe:
    raw = read_recipe_document(path)
    return load_recipe_document(raw, overrides)


def read_recipe_document(path: str | Path) -> dict[str, Any]:
    recipe_path = Path(path)
    try:
        raw_text = recipe_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RecipeValidationError(f"could not read recipe '{recipe_path}': {exc}") from exc

    try:
        raw = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise RecipeValidationError(f"invalid YAML in '{recipe_path}': {exc}") from exc

    if not isinstance(raw, dict):
        raise RecipeValidationError("recipe must be a YAML mapping")
    return raw


def load_recipe_document(
    raw: dict[str, Any],
    overrides: Mapping[str, Any] | None = None,
) -> Recipe:
    variables = dict(raw.get("variables") or {})
    if overrides:
        variables.update(overrides)

    rendered_input = dict(raw)
    rendered_input["variables"] = variables

    try:
        rendered = render_template_data(rendered_input, variables)
        return Recipe.model_validate(rendered)
    except (TemplateError, SafetyError) as exc:
        raise RecipeValidationError(str(exc)) from exc
    except ValidationError as exc:
        raise RecipeValidationError(str(exc)) from exc


def resolve_recipe_reference(recipe_id_or_path: str | Path) -> Path:
    raw = Path(recipe_id_or_path)
    if raw.exists() or raw.suffix in {".yaml", ".yml"} or raw.parent != Path("."):
        return raw

    recipe_id = str(recipe_id_or_path)
    if not SAFE_ID_PATTERN.fullmatch(recipe_id):
        raise RecipeValidationError(
            "recipe id must be a safe filename-like identifier or a path to a YAML file"
        )
    candidate = recipes_dir() / f"{recipe_id}.yaml"
    if not candidate.exists():
        raise RecipeValidationError(f"recipe not found: {recipe_id}")
    return candidate


def load_recipe_reference(
    recipe_id_or_path: str | Path,
    overrides: Mapping[str, Any] | None = None,
) -> Recipe:
    return load_recipe(resolve_recipe_reference(recipe_id_or_path), overrides)


def load_recipe_for_diagnostics(
    recipe_id_or_path: str | Path,
    overrides: Mapping[str, Any] | None = None,
) -> tuple[Recipe, dict[str, Any], list[str]]:
    path = resolve_recipe_reference(recipe_id_or_path)
    raw = read_recipe_document(path)
    variables = dict(raw.get("variables") or {})
    if overrides:
        variables.update(overrides)
    missing = sorted(_missing_template_variables(raw, variables))
    if not missing:
        return load_recipe_document(raw, overrides), raw, []

    diagnostic_variables = deepcopy(variables)
    for name in missing:
        _set_missing_variable(diagnostic_variables, name, f"__MISSING_{name}__")
    diagnostic_raw = dict(raw)
    diagnostic_raw["variables"] = diagnostic_variables
    return load_recipe_document(diagnostic_raw), raw, missing


def discover_recipes() -> list[tuple[Path, Recipe | None, str | None]]:
    discovered: list[tuple[Path, Recipe | None, str | None]] = []
    for path in sorted(recipes_dir().glob("*.y*ml")):
        try:
            discovered.append((path, load_recipe(path), None))
        except RecipeValidationError as exc:
            discovered.append((path, None, str(exc)))
    return discovered


def _missing_template_variables(raw: dict[str, Any], variables: Mapping[str, Any]) -> set[str]:
    variable_names = collect_template_variables(
        {key: value for key, value in raw.items() if key != "variables"}
    )
    return {name for name in variable_names if not _has_variable(name, variables)}


def _has_variable(name: str, variables: Mapping[str, Any]) -> bool:
    current: Any = variables
    for part in name.split("."):
        if isinstance(current, Mapping) and part in current:
            current = current[part]
            continue
        return False
    return True


def _set_missing_variable(variables: dict[str, Any], name: str, value: str) -> None:
    current = variables
    parts = name.split(".")
    for part in parts[:-1]:
        existing = current.get(part)
        if not isinstance(existing, dict):
            existing = {}
            current[part] = existing
        current = existing
    current[parts[-1]] = value
