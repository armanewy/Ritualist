from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .errors import SafetyError

SAFE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class StepBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    optional: bool = False
    requires_confirmation: bool = False
    timeout_seconds: float | None = Field(default=None, gt=0)

    @property
    def display_name(self) -> str:
        return self.name or self.action


class BrowserOpenStep(StepBase):
    action: Literal["browser.open"]
    url: str
    browser: Literal["chromium", "chrome", "msedge"] = "chromium"
    profile: str = "default"
    new_window: bool = False
    keep_open: bool = False

    @field_validator("profile")
    @classmethod
    def validate_profile(cls, value: str) -> str:
        if not SAFE_ID_PATTERN.fullmatch(value):
            raise ValueError(
                "profile must be a safe filename-like identifier "
                "(letters, numbers, hyphen, underscore)"
            )
        return value


class BrowserMediaStep(StepBase):
    action: Literal["browser.media"]
    selector: str = "video"
    play: bool | None = None
    loop: bool | None = None
    muted: bool | None = None


class AppLaunchStep(StepBase):
    action: Literal["app.launch"]
    command: str
    args: list[str] = Field(default_factory=list)
    cwd: str | None = None
    wait: bool = False
    env: dict[str, str] = Field(default_factory=dict)


class AppWaitProcessStep(StepBase):
    action: Literal["app.wait_process"]
    process_name: str


class WindowMatchMixin(BaseModel):
    title_contains: str | None = None
    process_name: str | None = None

    @model_validator(mode="after")
    def require_window_matcher(self) -> "WindowMatchMixin":
        if not self.title_contains and not self.process_name:
            raise ValueError("provide title_contains or process_name")
        return self


class WindowFocusStep(WindowMatchMixin, StepBase):
    action: Literal["window.focus"]


class WindowMinimizeStep(WindowMatchMixin, StepBase):
    action: Literal["window.minimize"]


class WindowMaximizeStep(WindowMatchMixin, StepBase):
    action: Literal["window.maximize"]


class WindowWaitStep(WindowMatchMixin, StepBase):
    action: Literal["window.wait"]


class DesktopClickTextStep(StepBase):
    action: Literal["desktop.click_text"]
    text: str
    window_title_contains: str
    control_type: str | None = None
    exact: bool = True
    button: Literal["left", "right"] = "left"

    @model_validator(mode="after")
    def enforce_click_safety(self) -> "DesktopClickTextStep":
        if not self.window_title_contains.strip():
            raise SafetyError("desktop.click_text requires window_title_contains in v0.1")
        if self.text.strip().casefold() == "play" and not self.requires_confirmation:
            raise SafetyError("desktop.click_text with text 'Play' requires requires_confirmation: true")
        return self


class InputHotkeyStep(StepBase):
    action: Literal["input.hotkey"]
    keys: list[str] = Field(min_length=1)

    @field_validator("keys")
    @classmethod
    def normalize_keys(cls, value: list[str]) -> list[str]:
        return [key.strip() for key in value if key.strip()]


class ConfirmAskStep(StepBase):
    action: Literal["confirm.ask"]
    prompt: str


WorkflowStep = Annotated[
    BrowserOpenStep
    | BrowserMediaStep
    | AppLaunchStep
    | AppWaitProcessStep
    | WindowFocusStep
    | WindowMinimizeStep
    | WindowMaximizeStep
    | WindowWaitStep
    | DesktopClickTextStep
    | InputHotkeyStep
    | ConfirmAskStep,
    Field(discriminator="action"),
]


class Recipe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = "0.1"
    id: str
    name: str
    description: str | None = None
    variables: dict[str, Any] = Field(default_factory=dict)
    steps: list[WorkflowStep] = Field(min_length=1)

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        if value != "0.1":
            raise ValueError("only recipe version '0.1' is supported")
        return value

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not SAFE_ID_PATTERN.fullmatch(value):
            raise ValueError(
                "id must be a safe filename-like identifier "
                "(letters, numbers, hyphen, underscore)"
            )
        return value
