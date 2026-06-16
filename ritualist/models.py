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


class WaitSecondsStep(StepBase):
    action: Literal["wait.seconds"]
    seconds: float = Field(gt=0)


class WaitForUserStep(StepBase):
    action: Literal["wait.for_user"]
    prompt: str = Field(min_length=1)


class WaitForFileStep(StepBase):
    action: Literal["wait.for_file"]
    path: str = Field(min_length=1)


class WaitForProcessStep(StepBase):
    action: Literal["wait.for_process"]
    process_name: str = Field(min_length=1)


class WaitForProcessExitStep(StepBase):
    action: Literal["wait.for_process_exit"]
    process_name: str = Field(min_length=1)


class WaitForWindowStep(WindowMatchMixin, StepBase):
    action: Literal["wait.for_window"]


class WaitForWindowGoneStep(WindowMatchMixin, StepBase):
    action: Literal["wait.for_window_gone"]


class AssertFileExistsStep(StepBase):
    action: Literal["assert.file_exists"]
    path: str


class AssertPathExistsStep(StepBase):
    action: Literal["assert.path_exists"]
    path: str


class AssertProcessRunningStep(StepBase):
    action: Literal["assert.process_running"]
    process_name: str


class AssertWindowExistsStep(WindowMatchMixin, StepBase):
    action: Literal["assert.window_exists"]


class AssertWindowTextVisibleStep(StepBase):
    action: Literal["assert.window_text_visible"]
    window_title_contains: str
    text: str
    control_type: str | None = None
    exact: bool = True

    @model_validator(mode="after")
    def enforce_window_scope(self) -> "AssertWindowTextVisibleStep":
        if not self.window_title_contains.strip():
            raise SafetyError("assert.window_text_visible requires window_title_contains")
        return self


class AssertBrowserTextVisibleStep(StepBase):
    action: Literal["assert.browser_text_visible"]
    text: str
    exact: bool = True


class AssertRegistryValueStep(StepBase):
    action: Literal["assert.registry_value"]
    key: str
    value_name: str = ""
    expected_value: Any | None = None


AssertionStep = Annotated[
    AssertFileExistsStep
    | AssertPathExistsStep
    | AssertProcessRunningStep
    | AssertWindowExistsStep
    | AssertWindowTextVisibleStep
    | AssertBrowserTextVisibleStep
    | AssertRegistryValueStep,
    Field(discriminator="action"),
]


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
    | ConfirmAskStep
    | WaitSecondsStep
    | WaitForUserStep
    | WaitForFileStep
    | WaitForProcessStep
    | WaitForProcessExitStep
    | WaitForWindowStep
    | WaitForWindowGoneStep,
    Field(discriminator="action"),
]

ExecutableStep = WorkflowStep | AssertionStep


class ExpectedWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title_contains: str | None = None
    process_name: str | None = None

    @model_validator(mode="after")
    def require_window_matcher(self) -> "ExpectedWindow":
        if not self.title_contains and not self.process_name:
            raise ValueError("provide title_contains or process_name")
        return self


class ExpectedLabel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    window_title_contains: str
    text: str
    control_type: str | None = None
    exact: bool = True

    @model_validator(mode="after")
    def enforce_window_scope(self) -> "ExpectedLabel":
        if not self.window_title_contains.strip():
            raise SafetyError("expected_labels requires window_title_contains")
        return self


class EnvironmentContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    os: list[Literal["windows", "macos", "linux"]] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)
    expected_windows: list[ExpectedWindow] = Field(default_factory=list)
    expected_labels: list[ExpectedLabel] = Field(default_factory=list)
    variable_hints: dict[str, str] = Field(default_factory=dict)


class RecipeHomeCardMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = ""
    subtitle: str = ""
    image: str = ""
    accent: str = ""


class RecipeHomeMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str = ""
    card: RecipeHomeCardMetadata = Field(default_factory=RecipeHomeCardMetadata)


class Recipe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = "0.1"
    id: str
    name: str
    description: str | None = None
    variables: dict[str, Any] = Field(default_factory=dict)
    home: RecipeHomeMetadata = Field(default_factory=RecipeHomeMetadata)
    environment: EnvironmentContract = Field(default_factory=EnvironmentContract)
    preflight: list[AssertionStep] = Field(default_factory=list)
    steps: list[WorkflowStep] = Field(min_length=1)
    verify: list[AssertionStep] = Field(default_factory=list)

    @property
    def execution_steps(self) -> list[ExecutableStep]:
        return [*self.preflight, *self.steps, *self.verify]

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
