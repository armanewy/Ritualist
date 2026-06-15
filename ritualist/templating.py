from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .errors import TemplateError

_PLACEHOLDER_RE = re.compile(r"{{\s*([A-Za-z_][A-Za-z0-9_.-]*)\s*}}")
_DOLLAR_PLACEHOLDER_RE = re.compile(r"\$\{\s*([A-Za-z_][A-Za-z0-9_.-]*)\s*\}")


def render_template_data(data: Any, variables: Mapping[str, Any]) -> Any:
    if isinstance(data, str):
        return render_string(data, variables)
    if isinstance(data, list):
        return [render_template_data(item, variables) for item in data]
    if isinstance(data, dict):
        return {key: render_template_data(value, variables) for key, value in data.items()}
    return data


def collect_template_variables(data: Any) -> set[str]:
    if isinstance(data, str):
        return {
            *(match.group(1) for match in _PLACEHOLDER_RE.finditer(data)),
            *(match.group(1) for match in _DOLLAR_PLACEHOLDER_RE.finditer(data)),
        }
    if isinstance(data, list):
        variables: set[str] = set()
        for item in data:
            variables.update(collect_template_variables(item))
        return variables
    if isinstance(data, dict):
        variables: set[str] = set()
        for value in data.values():
            variables.update(collect_template_variables(value))
        return variables
    return set()


def render_string(value: str, variables: Mapping[str, Any]) -> Any:
    full_match = _PLACEHOLDER_RE.fullmatch(value)
    if full_match:
        return _lookup(full_match.group(1), variables)
    dollar_full_match = _DOLLAR_PLACEHOLDER_RE.fullmatch(value)
    if dollar_full_match:
        return _lookup(dollar_full_match.group(1), variables)

    def replace(match: re.Match[str]) -> str:
        resolved = _lookup(match.group(1), variables)
        return str(resolved)

    rendered = _PLACEHOLDER_RE.sub(replace, value)
    return _DOLLAR_PLACEHOLDER_RE.sub(replace, rendered)


def _lookup(name: str, variables: Mapping[str, Any]) -> Any:
    current: Any = variables
    for part in name.split("."):
        if isinstance(current, Mapping) and part in current:
            current = current[part]
            continue
        raise TemplateError(f"unknown template variable '{name}'")
    return current
