from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from .metadata import ActionMetadata, SideEffectLevel
from .registry import ActionRegistry, create_default_registry


CatalogCategoryName = Literal[
    "Apps",
    "Browser",
    "Windows",
    "Desktop UI",
    "Input",
    "Files",
    "System",
    "Human",
    "Notes",
    "Notifications",
    "Flow",
    "Assertions",
    "Waits",
]

CATALOG_CATEGORY_NAMES: tuple[CatalogCategoryName, ...] = (
    "Apps",
    "Browser",
    "Windows",
    "Desktop UI",
    "Input",
    "Files",
    "System",
    "Human",
    "Notes",
    "Notifications",
    "Flow",
    "Assertions",
    "Waits",
)

SIDE_EFFECT_LABELS: dict[SideEffectLevel, str] = {
    "read_only": "Read only",
    "launches_app": "Launches app",
    "controls_ui": "Controls UI",
    "types_input": "Types input",
    "modifies_files": "Modifies files",
    "risky": "Risky",
}

_FILES_ACTIONS = frozenset({"assert.file_exists", "assert.path_exists", "wait.for_file"})
_SYSTEM_ACTIONS = frozenset(
    {
        "app.wait_process",
        "assert.process_running",
        "assert.registry_value",
        "confirm.ask",
        "wait.for_process",
        "wait.for_process_exit",
    }
)
_WAITS_ACTIONS = frozenset(
    {"wait.seconds", "wait.for_user", "wait.for_window", "wait.for_window_gone"}
)

_ACTION_DESCRIPTIONS: dict[str, str] = {
    "app.launch": "Launch a local application or command with structured arguments.",
    "app.wait_process": "Wait until a local process is running.",
    "assert.browser_text_visible": "Check that text is visible in the active browser context.",
    "assert.file_exists": "Check that a filesystem path exists and is a file.",
    "assert.path_exists": "Check that a filesystem path exists.",
    "assert.process_running": "Check that a local process is running.",
    "assert.registry_value": "Check that a Windows registry value exists or matches an expected value.",
    "assert.window_exists": "Check that a matching desktop window exists.",
    "assert.window_text_visible": "Check that text is visible in a scoped desktop window.",
    "browser.click_role": "Click a visible browser element by ARIA role and accessible name.",
    "browser.click_test_id": "Click a visible browser element by test id.",
    "browser.click_text": "Click visible text in the active Ritualist-managed browser page.",
    "browser.element_visible": "Wait until a structured browser element target is visible.",
    "browser.media": "Configure media playback options in a browser page.",
    "browser.open": "Open a URL in a managed browser session with a Ritualist dedicated profile.",
    "browser.open_native": "Hand an HTTP or HTTPS URL to the OS default browser without Playwright control.",
    "browser.wait_media_playing": "Wait until media in the managed browser page is ready and time advances.",
    "browser.wait_text": "Wait until text is visible in the active Ritualist-managed browser page.",
    "browser.wait_title": "Wait until the active browser page title matches.",
    "browser.wait_url": "Wait until the active browser page URL matches.",
    "confirm.ask": "Ask the user for explicit confirmation before continuing.",
    "desktop.click_text": "Click visible text inside a scoped desktop window.",
    "human.checklist": "Ask the operator to complete an explicit checklist before continuing.",
    "human.confirm_evidence": "Ask the operator to confirm expected evidence before continuing.",
    "human.prompt": "Show an explicit operator prompt and wait for acknowledgement.",
    "input.hotkey": "Send a structured keyboard hotkey.",
    "note.add": "Record a redacted note marker in the action result metadata.",
    "notify.beep": "Play a local fallback beep.",
    "notify.sound": "Play a local sound file when available, with a fallback beep.",
    "notify.toast": "Record a local notification message for the operator.",
    "flow.if": "Branch between structured step lists based on a read-only condition.",
    "wait.for_file": "Wait until a file appears.",
    "wait.for_process": "Wait until a local process appears.",
    "wait.for_process_exit": "Wait until a local process exits.",
    "wait.for_user": "Wait until the user confirms that the workflow can continue.",
    "wait.for_window": "Wait until a matching desktop window appears.",
    "wait.for_window_gone": "Wait until a matching desktop window is no longer present.",
    "wait.seconds": "Wait for a fixed duration while keeping the runtime responsive.",
    "window.focus": "Focus a matching desktop window.",
    "window.maximize": "Maximize a matching desktop window.",
    "window.minimize": "Minimize a matching desktop window.",
    "window.move": "Move a scoped desktop window to a screen position.",
    "window.resize": "Resize a scoped desktop window.",
    "window.restore": "Restore a scoped desktop window.",
    "window.snap_bottom": "Snap a scoped desktop window to the bottom half of the screen.",
    "window.snap_left": "Snap a scoped desktop window to the left half of the screen.",
    "window.snap_right": "Snap a scoped desktop window to the right half of the screen.",
    "window.snap_top": "Snap a scoped desktop window to the top half of the screen.",
    "window.wait": "Wait until a matching desktop window appears.",
}


@dataclass(frozen=True)
class ActionCatalogEntry:
    action_name: str
    category: CatalogCategoryName
    display_name: str
    description: str
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...]
    side_effect_level: SideEffectLevel
    side_effect_label: str
    safety_warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["required_fields"] = list(self.required_fields)
        data["optional_fields"] = list(self.optional_fields)
        data["safety_warnings"] = list(self.safety_warnings)
        return data


@dataclass(frozen=True)
class ActionCatalogCategory:
    name: CatalogCategoryName
    entries: tuple[ActionCatalogEntry, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "entries": [entry.to_dict() for entry in self.entries],
        }


@dataclass(frozen=True)
class ActionCatalog:
    categories: tuple[ActionCatalogCategory, ...]
    entries: tuple[ActionCatalogEntry, ...]

    def entry(self, action_name: str) -> ActionCatalogEntry:
        for catalog_entry in self.entries:
            if catalog_entry.action_name == action_name:
                return catalog_entry
        raise KeyError(f"no catalog entry for action '{action_name}'")

    def to_dict(self) -> dict[str, object]:
        return {
            "categories": [category.to_dict() for category in self.categories],
            "entries": [entry.to_dict() for entry in self.entries],
        }


def create_action_catalog(registry: ActionRegistry | None = None) -> ActionCatalog:
    """Build a GUI-consumable catalog from registered action metadata."""

    resolved_registry = registry or create_default_registry()
    entries = tuple(_entry_from_metadata(metadata) for metadata in _metadata_items(resolved_registry))
    entries_by_category: dict[CatalogCategoryName, list[ActionCatalogEntry]] = {
        name: [] for name in CATALOG_CATEGORY_NAMES
    }
    for entry in entries:
        entries_by_category[entry.category].append(entry)
    categories = tuple(
        ActionCatalogCategory(
            name=name,
            entries=tuple(
                sorted(entries_by_category[name], key=lambda item: item.display_name.casefold())
            ),
        )
        for name in CATALOG_CATEGORY_NAMES
    )
    return ActionCatalog(categories=categories, entries=entries)


def _metadata_items(registry: ActionRegistry) -> tuple[ActionMetadata, ...]:
    metadata_items: list[ActionMetadata] = []
    for action_type in registry.action_types():
        try:
            metadata = registry.metadata(action_type)
        except AttributeError as exc:
            raise ValueError(f"handler '{action_type}' must declare ActionMetadata") from exc
        if not isinstance(metadata, ActionMetadata):
            raise ValueError(f"handler '{action_type}' must declare ActionMetadata")
        if metadata.action_name != action_type:
            raise ValueError(
                f"metadata action '{metadata.action_name}' does not match "
                f"handler action '{action_type}'"
            )
        metadata_items.append(metadata)
    return tuple(metadata_items)


def _entry_from_metadata(metadata: ActionMetadata) -> ActionCatalogEntry:
    return ActionCatalogEntry(
        action_name=metadata.action_name,
        category=_catalog_category(metadata),
        display_name=_display_name(metadata.action_name),
        description=_description(metadata),
        required_fields=metadata.required_params,
        optional_fields=metadata.optional_params,
        side_effect_level=metadata.side_effect_level,
        side_effect_label=SIDE_EFFECT_LABELS[metadata.side_effect_level],
        safety_warnings=_safety_warnings(metadata),
    )


def _catalog_category(metadata: ActionMetadata) -> CatalogCategoryName:
    action_name = metadata.action_name
    if action_name in _FILES_ACTIONS:
        return "Files"
    if action_name in _SYSTEM_ACTIONS:
        return "System"
    if action_name in _WAITS_ACTIONS:
        return "Waits"
    if metadata.category == "app":
        return "Apps"
    if metadata.category == "browser":
        return "Browser"
    if metadata.category == "window":
        return "Windows"
    if metadata.category == "desktop":
        return "Desktop UI"
    if metadata.category == "human":
        return "Human"
    if metadata.category == "input":
        return "Input"
    if metadata.category == "note":
        return "Notes"
    if metadata.category == "notify":
        return "Notifications"
    if metadata.category == "flow":
        return "Flow"
    if metadata.category == "assert":
        return "Assertions"
    if metadata.category == "wait":
        return "Waits"
    return "System"


def _display_name(action_name: str) -> str:
    verb, _, subject = action_name.partition(".")
    words = [*subject.split("_"), verb]
    return " ".join(word.capitalize() for word in words if word)


def _description(metadata: ActionMetadata) -> str:
    description = _ACTION_DESCRIPTIONS.get(metadata.action_name)
    if description:
        return description
    fields = ", ".join(metadata.required_params) if metadata.required_params else "no fields"
    return f"{_display_name(metadata.action_name)} action requiring {fields}."


def _safety_warnings(metadata: ActionMetadata) -> tuple[str, ...]:
    warnings: list[str] = []
    if metadata.side_effect_level != "read_only":
        warnings.append(SIDE_EFFECT_LABELS[metadata.side_effect_level])
    if metadata.supported_platforms == ("windows",):
        warnings.append("Windows only")
    if metadata.allowed_in_imported_packs is False:
        warnings.append("Blocked in imported packs")
    if metadata.confirmation_policy == "always":
        warnings.append("Always asks for confirmation")
    elif metadata.confirmation_policy == "required_for_play":
        warnings.append("Clicking text exactly equal to Play requires confirmation")
    if metadata.action_name == "desktop.click_text":
        warnings.append("Requires window_title_contains")
    return tuple(dict.fromkeys(warnings))
