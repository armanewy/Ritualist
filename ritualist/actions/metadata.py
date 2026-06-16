from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal, get_args


CapabilityName = Literal[
    "playwright",
    "windows_uia",
    "app_launch",
    "browser_control",
    "window_management",
    "keyboard_input",
    "file_read",
    "file_write",
    "registry_read",
    "registry_write",
    "process_inspection",
]

PlatformName = Literal["windows", "macos", "linux"]
CategoryName = Literal[
    "app",
    "assert",
    "browser",
    "confirm",
    "desktop",
    "human",
    "input",
    "note",
    "notify",
    "flow",
    "wait",
    "window",
]
SideEffectLevel = Literal[
    "read_only",
    "launches_app",
    "controls_ui",
    "types_input",
    "modifies_files",
    "risky",
]
ConfirmationPolicy = Literal["never", "optional", "required_for_play", "always"]

ALL_PLATFORMS: tuple[PlatformName, ...] = ("windows", "macos", "linux")
WINDOWS_ONLY: tuple[PlatformName, ...] = ("windows",)

ALLOWED_CATEGORIES = frozenset(get_args(CategoryName))
ALLOWED_CAPABILITIES = frozenset(get_args(CapabilityName))
ALLOWED_PLATFORMS = frozenset(get_args(PlatformName))
ALLOWED_SIDE_EFFECT_LEVELS = frozenset(get_args(SideEffectLevel))
ALLOWED_CONFIRMATION_POLICIES = frozenset(get_args(ConfirmationPolicy))


@dataclass(frozen=True, init=False)
class ActionMetadata:
    action_name: str
    schema_version: str
    category: CategoryName
    required_params: tuple[str, ...]
    optional_params: tuple[str, ...]
    required_capabilities: tuple[CapabilityName, ...]
    supported_platforms: tuple[PlatformName, ...]
    side_effect_level: SideEffectLevel
    confirmation_policy: ConfirmationPolicy
    allowed_in_imported_packs: bool

    def __init__(
        self,
        *,
        action_name: str | None = None,
        action: str | None = None,
        schema_version: str,
        category: CategoryName | None = None,
        required_params: tuple[str, ...],
        optional_params: tuple[str, ...],
        required_capabilities: tuple[CapabilityName, ...],
        supported_platforms: tuple[PlatformName, ...] | None = None,
        platform_support: tuple[PlatformName, ...] | None = None,
        side_effect_level: SideEffectLevel,
        confirmation_policy: ConfirmationPolicy,
        allowed_in_imported_packs: bool,
    ) -> None:
        resolved_action = action_name or action
        if resolved_action is None:
            raise ValueError("action_name must be provided")
        resolved_platforms = supported_platforms or platform_support
        if resolved_platforms is None:
            raise ValueError("supported_platforms must be provided")
        resolved_category = category or _category_from_action(resolved_action)

        object.__setattr__(self, "action_name", resolved_action)
        object.__setattr__(self, "schema_version", schema_version)
        object.__setattr__(self, "category", resolved_category)
        object.__setattr__(self, "required_params", required_params)
        object.__setattr__(self, "optional_params", optional_params)
        object.__setattr__(self, "required_capabilities", required_capabilities)
        object.__setattr__(self, "supported_platforms", resolved_platforms)
        object.__setattr__(self, "side_effect_level", side_effect_level)
        object.__setattr__(self, "confirmation_policy", confirmation_policy)
        object.__setattr__(self, "allowed_in_imported_packs", allowed_in_imported_packs)
        self.__post_init__()

    def __post_init__(self) -> None:
        _require_non_empty_string("action_name", self.action_name)
        _require_non_empty_string("schema_version", self.schema_version)
        _require_allowed("category", self.category, ALLOWED_CATEGORIES)
        _require_string_tuple("required_params", self.required_params)
        _require_string_tuple("optional_params", self.optional_params)
        _require_allowed_tuple(
            "required_capabilities",
            self.required_capabilities,
            ALLOWED_CAPABILITIES,
            allow_empty=True,
        )
        _require_allowed_tuple(
            "supported_platforms",
            self.supported_platforms,
            ALLOWED_PLATFORMS,
            allow_empty=False,
        )
        _require_allowed("side_effect_level", self.side_effect_level, ALLOWED_SIDE_EFFECT_LEVELS)
        _require_allowed(
            "confirmation_policy",
            self.confirmation_policy,
            ALLOWED_CONFIRMATION_POLICIES,
        )
        if not isinstance(self.allowed_in_imported_packs, bool):
            raise ValueError("allowed_in_imported_packs must be a bool")

    @property
    def action(self) -> str:
        return self.action_name

    @property
    def platform_support(self) -> tuple[PlatformName, ...]:
        return self.supported_platforms

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        for key, value in data.items():
            if isinstance(value, tuple):
                data[key] = list(value)
        data["action"] = self.action_name
        data["platform_support"] = list(self.supported_platforms)
        return data


def _require_non_empty_string(field_name: str, value: object) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")


def _require_string_tuple(field_name: str, value: object) -> None:
    if not isinstance(value, tuple):
        raise ValueError(f"{field_name} must be a tuple")
    for item in value:
        if not isinstance(item, str) or not item:
            raise ValueError(f"{field_name} must contain only non-empty strings")


def _require_allowed(field_name: str, value: object, allowed: frozenset[str]) -> None:
    if value not in allowed:
        raise ValueError(f"{field_name} must be one of {sorted(allowed)}")


def _require_allowed_tuple(
    field_name: str,
    value: object,
    allowed: frozenset[str],
    *,
    allow_empty: bool,
) -> None:
    if not isinstance(value, tuple):
        raise ValueError(f"{field_name} must be a tuple")
    if not allow_empty and not value:
        raise ValueError(f"{field_name} must not be empty")
    for item in value:
        _require_allowed(field_name, item, allowed)


def _category_from_action(action_name: str) -> CategoryName:
    category = action_name.split(".", 1)[0]
    _require_allowed("category", category, ALLOWED_CATEGORIES)
    return category  # type: ignore[return-value]
