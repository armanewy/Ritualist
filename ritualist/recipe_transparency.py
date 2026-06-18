from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

from .errors import RecipeValidationError
from .models import SAFE_ID_PATTERN, FlowIfStep, Recipe
from .paths import config_dir
from .recipe_loader import (
    load_recipe,
    load_recipe_document,
    read_recipe_document,
    resolve_recipe_reference,
)

SETUP_FIELD_LABELS: dict[str, str] = {
    "ambience_enabled": "Ambience enabled",
    "ambience_url": "Ambience URL",
    "ambience_browser_mode": "Browser mode",
    "minimize_ambience": "Minimize ambience",
    "battle_net_path": "Battle.net path",
    "battle_net_window": "Expected Battle.net window",
    "target_game": "Target game",
    "target_id": "Target",
}
GAMING_SETUP_FIELD_ORDER = (
    "ambience_enabled",
    "ambience_url",
    "ambience_browser_mode",
    "minimize_ambience",
    "battle_net_path",
    "battle_net_window",
    "target_game",
    "target_id",
)
NEVER_DO = (
    "Never enters passwords or credentials.",
    "Never installs, locates, or updates games.",
    "Never automates gameplay.",
    "Never uses coordinate clicks.",
    "Never runs recipe-supplied Python, JavaScript, or shell snippets.",
    "Never runs automatically after setup edits.",
)
_FORBIDDEN_SETUP_TERMS = (
    "script",
    "javascript",
    "python",
    "shell",
    "powershell",
    "command_line",
    "coordinate",
    "password",
)


@dataclass(frozen=True)
class RecipeSetupUpdateResult:
    recipe_id: str
    recipe_path: Path
    overrides_path: Path
    overrides: dict[str, Any]
    plan: list[str]
    side_effects: dict[str, bool]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "recipe.setup_update.v1",
            "recipe_id": self.recipe_id,
            "recipe_path": str(self.recipe_path),
            "overrides_path": str(self.overrides_path),
            "overrides": dict(self.overrides),
            "plain_language_plan": list(self.plan),
            "side_effects": dict(self.side_effects),
        }


def view_recipe_payload(
    recipe_ref: str | Path,
    *,
    overrides_root: Path | None = None,
) -> dict[str, Any]:
    recipe_path = resolve_recipe_reference(recipe_ref)
    raw = read_recipe_document(recipe_path)
    stored_overrides = load_recipe_overrides(recipe_ref, overrides_root=overrides_root)
    recipe = load_recipe_document(raw, stored_overrides)
    setup_fields = build_setup_fields(raw, stored_overrides, recipe_id=recipe.id)
    plan = build_plain_language_plan(recipe)
    return {
        "schema_version": "recipe.transparency.v1",
        "recipe_id": recipe.id,
        "recipe_name": recipe.name,
        "recipe_path": str(recipe_path),
        "purpose": recipe.description or "",
        "ordered_steps": [_step_summary(step, index=index) for index, step in enumerate(recipe.steps, start=1)],
        "optional_steps": [
            item
            for item in _flatten_step_summaries(recipe.steps)
            if item["optional"] or item["on_timeout"]
        ],
        "current_variables": dict(recipe.variables),
        "setup_fields": setup_fields,
        "live_preflight_requirements": _preflight_requirements(recipe),
        "confirmations": _confirmation_summaries(recipe),
        "success_verification": [_step_summary(step, index=index) for index, step in enumerate(recipe.verify, start=1)],
        "blocked_branches": _blocked_branches(recipe),
        "what_ritualist_will_never_do": list(NEVER_DO),
        "plain_language_plan": plan,
        "actions": {
            "view_recipe": True,
            "edit_setup": True,
            "advanced_open_yaml": str(recipe_path),
            "doctor": f"python -m ritualist doctor {recipe.id}",
            "dry_run": f"python -m ritualist dry-run {recipe.id}",
            "auto_run_after_edit": False,
        },
    }


def open_yaml_payload(recipe_ref: str | Path) -> dict[str, Any]:
    recipe_path = resolve_recipe_reference(recipe_ref)
    return {
        "schema_version": "recipe.open_yaml_reference.v1",
        "recipe_path": str(recipe_path),
        "side_effects": {
            "opened_editor": False,
            "ran_recipe": False,
            "modified_recipe": False,
        },
        "warning": "Advanced YAML editing changes the source recipe; setup overrides are safer for normal configuration.",
    }


def save_recipe_setup_overrides(
    recipe_ref: str | Path,
    updates: Mapping[str, Any],
    *,
    overrides_root: Path | None = None,
) -> RecipeSetupUpdateResult:
    recipe_path = resolve_recipe_reference(recipe_ref)
    raw = read_recipe_document(recipe_path)
    recipe_id = _recipe_id(raw)
    existing = load_recipe_overrides(recipe_ref, overrides_root=overrides_root)
    normalized = _normalize_setup_updates(raw, updates)
    merged = {**existing, **normalized}
    load_recipe_document(raw, merged)
    path = recipe_overrides_path(recipe_id, overrides_root=overrides_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(merged, sort_keys=True), encoding="utf-8")
    rendered = load_recipe(recipe_path, merged)
    return RecipeSetupUpdateResult(
        recipe_id=recipe_id,
        recipe_path=recipe_path,
        overrides_path=path,
        overrides=merged,
        plan=build_plain_language_plan(rendered),
        side_effects={
            "bundled_recipe_modified": False,
            "ran_recipe": False,
            "opened_external_app": False,
        },
    )


def load_recipe_overrides(
    recipe_ref: str | Path,
    *,
    overrides_root: Path | None = None,
) -> dict[str, Any]:
    recipe_path = resolve_recipe_reference(recipe_ref)
    raw = read_recipe_document(recipe_path)
    path = recipe_overrides_path(_recipe_id(raw), overrides_root=overrides_root)
    if not path.exists():
        return {}
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RecipeValidationError(f"invalid setup overrides in '{path}': {exc}") from exc
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise RecipeValidationError("setup overrides must be a YAML mapping")
    return {str(key): value for key, value in loaded.items()}


def recipe_overrides_path(recipe_id: str, *, overrides_root: Path | None = None) -> Path:
    if not SAFE_ID_PATTERN.fullmatch(recipe_id):
        raise RecipeValidationError("recipe id must be safe before storing setup overrides")
    root = overrides_root or (config_dir() / "recipe-overrides")
    return Path(root) / f"{recipe_id}.yaml"


def build_setup_fields(
    raw_recipe: Mapping[str, Any],
    overrides: Mapping[str, Any] | None = None,
    *,
    recipe_id: str | None = None,
) -> list[dict[str, Any]]:
    variables = dict(raw_recipe.get("variables") or {})
    applied = dict(overrides or {})
    ordered_names = list(GAMING_SETUP_FIELD_ORDER if recipe_id == "gaming_mode" else ())
    for name in variables:
        if name not in ordered_names:
            ordered_names.append(name)
    fields: list[dict[str, Any]] = []
    for name in ordered_names:
        fields.append(
            {
                "name": name,
                "label": SETUP_FIELD_LABELS.get(name, _label_from_name(name)),
                "available": name in variables,
                "value": applied.get(name, variables.get(name)),
                "overridden": name in applied,
                "choices": ["native", "managed"] if name == "ambience_browser_mode" else [],
                "editable": name in variables,
            }
        )
    return fields


def build_plain_language_plan(recipe: Recipe) -> list[str]:
    lines = [f"Purpose: {recipe.description or recipe.name}"]
    for index, step in enumerate(recipe.steps, start=1):
        lines.extend(_plan_lines_for_step(step, prefix=f"{index}."))
    if recipe.verify:
        lines.append("Verify success:")
        for index, step in enumerate(recipe.verify, start=1):
            lines.append(f"  {index}. {_step_phrase(step)}")
    lines.append("Doctor and Dry Run are available before any real run.")
    lines.append("Editing setup saves overrides only and does not run the recipe.")
    return lines


def _normalize_setup_updates(
    raw_recipe: Mapping[str, Any],
    updates: Mapping[str, Any],
) -> dict[str, Any]:
    variables = dict(raw_recipe.get("variables") or {})
    normalized: dict[str, Any] = {}
    for key, value in updates.items():
        name = str(key)
        _reject_forbidden_setup_name(name)
        if name not in variables:
            raise RecipeValidationError(f"unknown setup field: {name}")
        if isinstance(value, dict | list | tuple | set):
            raise RecipeValidationError(f"setup field '{name}' must be a scalar value")
        if name == "ambience_browser_mode" and value not in {"native", "managed"}:
            raise RecipeValidationError("ambience_browser_mode must be native or managed")
        if isinstance(variables[name], bool):
            normalized[name] = _coerce_bool(value, name)
        else:
            normalized[name] = value
    return normalized


def _reject_forbidden_setup_name(name: str) -> None:
    lowered = name.casefold()
    for term in _FORBIDDEN_SETUP_TERMS:
        if term in lowered:
            raise RecipeValidationError(f"setup field '{name}' is not allowed")


def _coerce_bool(value: Any, name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().casefold()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
    raise RecipeValidationError(f"setup field '{name}' must be a boolean")


def _recipe_id(raw: Mapping[str, Any]) -> str:
    recipe_id = str(raw.get("id") or "").strip()
    if not SAFE_ID_PATTERN.fullmatch(recipe_id):
        raise RecipeValidationError("recipe id must be a safe filename-like identifier")
    return recipe_id


def _preflight_requirements(recipe: Recipe) -> dict[str, Any]:
    return {
        "os": list(recipe.environment.os),
        "required_capabilities": list(recipe.environment.required_capabilities),
        "expected_windows": [item.model_dump(mode="json") for item in recipe.environment.expected_windows],
        "expected_labels": [item.model_dump(mode="json") for item in recipe.environment.expected_labels],
        "preflight_steps": [_step_summary(step, index=index) for index, step in enumerate(recipe.preflight, start=1)],
    }


def _confirmation_summaries(recipe: Recipe) -> list[dict[str, Any]]:
    confirmations: list[dict[str, Any]] = []
    for item in _flatten_step_summaries(recipe.steps):
        if item["requires_confirmation"] or item["action"] == "confirm.ask":
            confirmations.append(item)
    return confirmations


def _blocked_branches(recipe: Recipe) -> list[dict[str, Any]]:
    branches: list[dict[str, Any]] = []
    for step in recipe.steps:
        _collect_blocked_branches(step, branches, path=step.display_name)
    return branches


def _collect_blocked_branches(step: Any, branches: list[dict[str, Any]], *, path: str) -> None:
    if isinstance(step, FlowIfStep):
        branches.append(
            {
                "step": path,
                "condition": step.condition.model_dump(mode="json", by_alias=True, exclude_none=True),
                "then_steps": [_step_phrase(item) for item in step.then],
                "else_steps": [_step_phrase(item) for item in step.else_],
            }
        )
        for branch_step in [*step.then, *step.else_]:
            _collect_blocked_branches(branch_step, branches, path=f"{path} > {branch_step.display_name}")
    for timeout_step in getattr(step, "on_timeout", None) or []:
        branches.append(
            {
                "step": path,
                "condition": "timeout",
                "then_steps": [_step_phrase(timeout_step)],
                "else_steps": [],
            }
        )
        _collect_blocked_branches(timeout_step, branches, path=f"{path} > timeout")


def _flatten_step_summaries(steps: list[Any]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for index, step in enumerate(steps, start=1):
        summaries.append(_step_summary(step, index=index))
        if isinstance(step, FlowIfStep):
            summaries.extend(_flatten_step_summaries(step.then))
            summaries.extend(_flatten_step_summaries(step.else_))
        summaries.extend(_flatten_step_summaries(getattr(step, "on_timeout", None) or []))
    return summaries


def _step_summary(step: Any, *, index: int) -> dict[str, Any]:
    return {
        "index": index,
        "name": step.display_name,
        "action": step.action,
        "optional": bool(getattr(step, "optional", False)),
        "requires_confirmation": bool(getattr(step, "requires_confirmation", False)),
        "timeout_seconds": getattr(step, "timeout_seconds", None),
        "on_timeout": bool(getattr(step, "on_timeout", None)),
        "summary": _step_phrase(step),
    }


def _plan_lines_for_step(step: Any, *, prefix: str) -> list[str]:
    lines = [f"{prefix} {_step_phrase(step)}"]
    if isinstance(step, FlowIfStep):
        if step.then:
            lines.append(f"{prefix} when matched:")
            for index, branch_step in enumerate(step.then, start=1):
                lines.extend(_plan_lines_for_step(branch_step, prefix=f"  {index}."))
        if step.else_:
            lines.append(f"{prefix} otherwise:")
            for index, branch_step in enumerate(step.else_, start=1):
                lines.extend(_plan_lines_for_step(branch_step, prefix=f"  {index}."))
    return lines


def _step_phrase(step: Any) -> str:
    name = str(getattr(step, "display_name", "") or getattr(step, "action", "step"))
    action = str(getattr(step, "action", ""))
    if action == "browser.open_native":
        return f"{name}: hand off URL to the normal browser."
    if action == "browser.open":
        return f"{name}: open a managed browser session."
    if action == "browser.wait_media_playing":
        return f"{name}: verify managed media is playing."
    if action == "app.launch":
        return f"{name}: launch local app path."
    if action in {"window.wait", "wait.for_window"}:
        return f"{name}: wait for the expected window."
    if action == "target.inspect":
        return f"{name}: inspect target readiness without clicking."
    if action == "target.wait_state":
        return f"{name}: wait for target readiness state."
    if action == "desktop.click_text":
        outcome = " after confirmation" if getattr(step, "requires_confirmation", False) else ""
        return f"{name}: invoke exact visible desktop text{outcome}."
    if action == "flow.if":
        return f"{name}: branch on a live condition."
    if action.startswith("assert."):
        return f"{name}: verify {action.removeprefix('assert.').replace('_', ' ')}."
    if action.startswith("human."):
        return f"{name}: ask the operator for review."
    return f"{name}: {action}."


def _label_from_name(name: str) -> str:
    return name.replace("_", " ").replace("-", " ").strip().title()
