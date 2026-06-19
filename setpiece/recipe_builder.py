from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Final, Mapping

import yaml

from .errors import RecipeValidationError
from .models import Recipe
from .recipe_loader import load_recipe_document, read_recipe_document

_UNSET: Final = object()


class RecipeBuilder:
    """Mutable recipe draft for GUI-backed editing.

    The builder edits the raw YAML-shaped mapping and validates through the same
    loader/model path used by power-user YAML files. Saving rewrites YAML with
    PyYAML, so comments and original formatting may not be preserved.
    """

    def __init__(self, document: Mapping[str, Any]) -> None:
        self._document = deepcopy(dict(document))

    @classmethod
    def create(
        cls,
        recipe_id: str,
        name: str,
        *,
        description: str | None = None,
        variables: Mapping[str, Any] | None = None,
        home: Mapping[str, Any] | None = None,
        environment: Mapping[str, Any] | None = None,
    ) -> "RecipeBuilder":
        document: dict[str, Any] = {
            "version": "0.1",
            "id": recipe_id,
            "name": name,
            "steps": [],
        }
        if description:
            document["description"] = description
        if variables is not None:
            document["variables"] = deepcopy(dict(variables))
        if home is not None:
            document["home"] = deepcopy(dict(home))
        if environment is not None:
            document["environment"] = deepcopy(dict(environment))
        return cls(document)

    @classmethod
    def from_path(cls, path: str | Path) -> "RecipeBuilder":
        return cls(read_recipe_document(path))

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> "RecipeBuilder":
        return cls(document)

    @property
    def document(self) -> dict[str, Any]:
        return deepcopy(self._document)

    @property
    def steps(self) -> list[dict[str, Any]]:
        return deepcopy(self._steps())

    def update_metadata(
        self,
        *,
        recipe_id: str | None = None,
        name: str | None = None,
        description: str | None | object = _UNSET,
        variables: Mapping[str, Any] | None = None,
        home: Mapping[str, Any] | None = None,
        environment: Mapping[str, Any] | None = None,
    ) -> None:
        if recipe_id is not None:
            self._document["id"] = recipe_id
        if name is not None:
            self._document["name"] = name
        if description is not _UNSET:
            if description is None:
                self._document.pop("description", None)
            else:
                self._document["description"] = description
        if variables is not None:
            self._document["variables"] = deepcopy(dict(variables))
        if home is not None:
            self._document["home"] = deepcopy(dict(home))
        if environment is not None:
            self._document["environment"] = deepcopy(dict(environment))

    def add_step(self, step: Mapping[str, Any], index: int | None = None) -> int:
        steps = self._steps()
        draft = deepcopy(dict(step))
        if index is None:
            steps.append(draft)
            return len(steps) - 1
        if index < 0 or index > len(steps):
            raise IndexError("step index out of range")
        steps.insert(index, draft)
        return index

    def reorder_step(self, old_index: int, new_index: int) -> None:
        steps = self._steps()
        if old_index < 0 or old_index >= len(steps):
            raise IndexError("old step index out of range")
        if new_index < 0 or new_index >= len(steps):
            raise IndexError("new step index out of range")
        step = steps.pop(old_index)
        steps.insert(new_index, step)

    def delete_step(self, index: int) -> dict[str, Any]:
        steps = self._steps()
        if index < 0 or index >= len(steps):
            raise IndexError("step index out of range")
        return steps.pop(index)

    def validate(self) -> Recipe:
        return load_recipe_document(self.document)

    def to_yaml(self, *, validate: bool = True) -> str:
        if validate:
            self.validate()
        return yaml.safe_dump(self.document, sort_keys=False, allow_unicode=True)

    def save(self, path: str | Path) -> Recipe:
        recipe = self.validate()
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.to_yaml(validate=False), encoding="utf-8")
        return recipe

    def _steps(self) -> list[dict[str, Any]]:
        steps = self._document.setdefault("steps", [])
        if not isinstance(steps, list):
            raise RecipeValidationError("recipe steps must be a list before editing")
        return steps
