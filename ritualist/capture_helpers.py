from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol

from ritualist.errors import RitualistError


CaptureSource = Literal[
    "foreground_window",
    "app_path_dialog",
    "file_path_dialog",
    "folder_path_dialog",
]


class PathPicker(Protocol):
    def browse_app_path(self) -> str | None:
        """Return a user-selected app path, or None when cancelled."""

    def browse_file_path(self) -> str | None:
        """Return a user-selected file path, or None when cancelled."""

    def browse_folder_path(self) -> str | None:
        """Return a user-selected folder path, or None when cancelled."""


@dataclass(frozen=True)
class CapturedValue:
    value: str
    source: CaptureSource
    variable_name: str | None = None

    @property
    def recipe_value(self) -> str:
        if self.variable_name:
            return f"{{{{ {self.variable_name} }}}}"
        return self.value

    @property
    def variable_update(self) -> dict[str, str]:
        if not self.variable_name:
            return {}
        return {self.variable_name: self.value}


@dataclass(frozen=True)
class CapturedWindowInspection:
    title: str
    labels: tuple[str, ...]


@dataclass(frozen=True)
class WindowTextInspection:
    query: str
    control_type: str | None
    windows: tuple[CapturedWindowInspection, ...]

    @property
    def labels(self) -> tuple[str, ...]:
        seen: set[str] = set()
        labels: list[str] = []
        for window in self.windows:
            for label in window.labels:
                if label in seen:
                    continue
                seen.add(label)
                labels.append(label)
        return tuple(labels)


@dataclass(frozen=True)
class VisibleTextChoice:
    window_title_contains: str
    text: str
    control_type: str | None = None
    exact: bool = True
    variable_name: str | None = None

    @property
    def recipe_text(self) -> str:
        if self.variable_name:
            return f"{{{{ {self.variable_name} }}}}"
        return self.text

    @property
    def variable_update(self) -> dict[str, str]:
        if not self.variable_name:
            return {}
        return {self.variable_name: self.text}

    def click_text_step(self) -> dict[str, object]:
        step: dict[str, object] = {
            "action": "desktop.click_text",
            "window_title_contains": self.window_title_contains,
            "text": self.recipe_text,
            "exact": self.exact,
        }
        if self.control_type:
            step["control_type"] = self.control_type
        if self.text.strip().casefold() == "play":
            step["requires_confirmation"] = True
        return step


class CaptureHelperController:
    def __init__(self, adapters: Any, *, path_picker: PathPicker | None = None) -> None:
        self.adapters = adapters
        self.path_picker = path_picker

    def pick_foreground_window_title(
        self,
        *,
        recipe: Any | None = None,
        variable_name: str | None = None,
    ) -> CapturedValue:
        title = self.adapters.window.foreground_window_title()
        return CapturedValue(
            value=_require_value(title, "foreground window title"),
            source="foreground_window",
            variable_name=_recipe_variable(
                recipe,
                variable_name,
                preferred_names=("window_title", "app_window", "window"),
                suffix="_window",
            ),
        )

    def browse_app_path(
        self,
        *,
        recipe: Any | None = None,
        variable_name: str | None = None,
    ) -> CapturedValue | None:
        path = self._path_picker().browse_app_path()
        return self._captured_path(
            path,
            source="app_path_dialog",
            recipe=recipe,
            variable_name=variable_name,
            preferred_names=("app_path", "exe_path", "command_path"),
            suffix="_path",
        )

    def browse_file_path(
        self,
        *,
        recipe: Any | None = None,
        variable_name: str | None = None,
    ) -> CapturedValue | None:
        path = self._path_picker().browse_file_path()
        return self._captured_path(
            path,
            source="file_path_dialog",
            recipe=recipe,
            variable_name=variable_name,
            preferred_names=("file_path", "path"),
            suffix="_path",
        )

    def browse_folder_path(
        self,
        *,
        recipe: Any | None = None,
        variable_name: str | None = None,
    ) -> CapturedValue | None:
        path = self._path_picker().browse_folder_path()
        return self._captured_path(
            path,
            source="folder_path_dialog",
            recipe=recipe,
            variable_name=variable_name,
            preferred_names=("folder_path", "directory_path", "path"),
            suffix="_path",
        )

    def inspect_window_text(
        self,
        *,
        window_title_contains: str | None = None,
        recipe: Any | None = None,
        variable_name: str | None = None,
        control_type: str | None = None,
        limit: int = 30,
    ) -> WindowTextInspection:
        query = (
            window_title_contains
            or _recipe_variable_default(recipe, variable_name)
            or _recipe_variable_default(recipe, "window_title")
            or _recipe_variable_default(recipe, "app_window")
        )
        query = _require_value(query, "window title query")
        rows = self.adapters.desktop.inspect_windows(
            title_contains=query,
            limit=limit,
            control_type=control_type,
        )
        windows = tuple(
            CapturedWindowInspection(
                title=str(getattr(row, "title", "")),
                labels=tuple(str(label) for label in getattr(row, "labels", ())),
            )
            for row in rows
        )
        return WindowTextInspection(query=query, control_type=control_type, windows=windows)

    def choose_visible_text(
        self,
        inspection: WindowTextInspection,
        *,
        text: str | None = None,
        label_index: int | None = None,
        recipe: Any | None = None,
        variable_name: str | None = None,
    ) -> VisibleTextChoice:
        label = _choose_label(inspection, text=text, label_index=label_index)
        title = _window_title_for_label(inspection, label) or inspection.query
        return VisibleTextChoice(
            window_title_contains=title,
            text=label,
            control_type=inspection.control_type,
            variable_name=_recipe_variable(
                recipe,
                variable_name,
                preferred_names=("visible_text", "button_text", "label_text"),
                suffix="_text",
            ),
        )

    def _captured_path(
        self,
        path: str | None,
        *,
        source: CaptureSource,
        recipe: Any | None,
        variable_name: str | None,
        preferred_names: tuple[str, ...],
        suffix: str,
    ) -> CapturedValue | None:
        if path is None:
            return None
        return CapturedValue(
            value=_require_value(path, "selected path"),
            source=source,
            variable_name=_recipe_variable(
                recipe,
                variable_name,
                preferred_names=preferred_names,
                suffix=suffix,
            ),
        )

    def _path_picker(self) -> PathPicker:
        if self.path_picker is None:
            raise RitualistError("path capture requires an explicit path picker")
        return self.path_picker


def _choose_label(
    inspection: WindowTextInspection,
    *,
    text: str | None,
    label_index: int | None,
) -> str:
    if (text is None) == (label_index is None):
        raise RitualistError("choose visible text with exactly one of text or label_index")
    labels = inspection.labels
    if label_index is not None:
        if label_index < 0 or label_index >= len(labels):
            raise RitualistError(f"visible text index out of range: {label_index}")
        return labels[label_index]
    assert text is not None
    for label in labels:
        if label == text:
            return label
    raise RitualistError(f"visible text was not present in the inspection: {text}")


def _window_title_for_label(inspection: WindowTextInspection, label: str) -> str | None:
    for window in inspection.windows:
        if label in window.labels:
            return window.title or None
    return None


def _recipe_variable(
    recipe: Any | None,
    variable_name: str | None,
    *,
    preferred_names: tuple[str, ...],
    suffix: str,
) -> str | None:
    variables = _recipe_variables(recipe)
    if variable_name:
        return variable_name if variable_name in variables else None
    for preferred in preferred_names:
        if preferred in variables:
            return preferred
    matches = [name for name in variables if name.casefold().endswith(suffix)]
    return matches[0] if len(matches) == 1 else None


def _recipe_variable_default(recipe: Any | None, variable_name: str | None) -> str | None:
    if not variable_name:
        return None
    value = _recipe_variables(recipe).get(variable_name)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _recipe_variables(recipe: Any | None) -> dict[str, Any]:
    variables = getattr(recipe, "variables", None)
    return variables if isinstance(variables, dict) else {}


def _require_value(value: str | None, label: str) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        raise RitualistError(f"{label} is empty")
    return text
