from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml
from pydantic import ValidationError

from .errors import RecipeValidationError, SafetyError, TemplateError
from .models import SAFE_ID_PATTERN, Recipe
from .paths import recipes_dir
from .templating import render_template_data


def load_recipe(path: str | Path, overrides: Mapping[str, Any] | None = None) -> Recipe:
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

    variables = dict(raw.get("variables") or {})
    if overrides:
        variables.update(overrides)

    raw["variables"] = variables

    try:
        rendered = render_template_data(raw, variables)
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


def discover_recipes() -> list[tuple[Path, Recipe | None, str | None]]:
    discovered: list[tuple[Path, Recipe | None, str | None]] = []
    for path in sorted(recipes_dir().glob("*.y*ml")):
        try:
            discovered.append((path, load_recipe(path), None))
        except RecipeValidationError as exc:
            discovered.append((path, None, str(exc)))
    return discovered
