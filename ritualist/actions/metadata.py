from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


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


@dataclass(frozen=True)
class ActionMetadata:
    action: str
    schema_version: str
    required_params: tuple[str, ...]
    optional_params: tuple[str, ...]
    required_capabilities: tuple[CapabilityName, ...]
    platform_support: tuple[PlatformName, ...]
    side_effect_level: SideEffectLevel
    confirmation_policy: ConfirmationPolicy
    allowed_in_imported_packs: bool

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        for key, value in data.items():
            if isinstance(value, tuple):
                data[key] = list(value)
        return data
