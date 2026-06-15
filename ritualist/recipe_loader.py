from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml
from pydantic import ValidationError

from .errors import RecipeValidationError, SafetyError, TemplateError
from .models import Recipe
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
