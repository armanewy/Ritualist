from __future__ import annotations

import re
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

from .errors import SafetyError

SAFE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
RISKY_BROWSER_CLICK_TARGETS = frozenset(
    {
        "buy",
        "purchase",
        "pay",
        "send",
        "delete",
        "submit",
        "confirm",
    }
)
_WORD_PATTERN = re.compile(r"[A-Za-z0-9]+")


PredicateType = Literal[
    "value.equals",
    "file.exists",
    "path.exists",
    "process.running",
    "window.exists",
    "window.text_visible",
    "browser.text_visible",
    "target.state",
    "target.readiness_state",
]


class Condition(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    type: PredicateType | None = None
    all: list["Condition"] | None = None
    any: list["Condition"] | None = None
    not_: "Condition | None" = Field(default=None, alias="not")
    path: str | None = None
    process_name: str | None = None
    title_contains: str | None = None
    window_title_contains: str | None = None
    text: str | None = None
    control_type: str | None = None
    exact: bool = True
    left: Any | None = None
    right: Any | None = None
    target: str | None = None
    state: str | None = None
    states: list[str] | None = None
    readiness_state: str | None = None
    readiness_states: list[str] | None = None

    @model_validator(mode="after")
    def validate_condition_shape(self) -> "Condition":
        operators = [
            self.type is not None,
            self.all is not None,
            self.any is not None,
            self.not_ is not None,
        ]
        if sum(operators) != 1:
            raise ValueError("condition must contain exactly one of type, all, any, or not")
        if self.all is not None and not self.all:
            raise ValueError("condition.all must contain at least one condition")
        if self.any is not None and not self.any:
            raise ValueError("condition.any must contain at least one condition")
        if self.type is not None:
            _validate_predicate_fields(self)
        else:
            _validate_composition_fields(self)
        return self


class StepBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    optional: bool = False
    requires_confirmation: bool = False
    timeout_seconds: float | None = Field(default=None, gt=0)
    when: Condition | None = None

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
    clean_start: bool = False
    dismiss_restore_prompt: bool = False
    use_dedicated_profile: bool = True

    @field_validator("profile")
    @classmethod
    def validate_profile(cls, value: str) -> str:
        if not SAFE_ID_PATTERN.fullmatch(value):
            raise ValueError(
                "profile must be a safe filename-like identifier "
                "(letters, numbers, hyphen, underscore)"
            )
        return value

    @field_validator("use_dedicated_profile")
    @classmethod
    def require_dedicated_profile(cls, value: bool) -> bool:
        if not value:
            raise ValueError(
                "use_dedicated_profile must be true; Setpiece only opens managed browser profiles"
            )
        return value


class BrowserOpenNativeStep(StepBase):
    action: Literal["browser.open_native"]
    url: str
    new_window: bool = False

    @field_validator("url")
    @classmethod
    def validate_native_url(cls, value: str) -> str:
        return _required_http_url("browser.open_native", value)


class BrowserMediaStep(StepBase):
    action: Literal["browser.media"]
    selector: str = "video"
    play: bool | None = None
    loop: bool | None = None
    muted: bool | None = None


class BrowserWaitMediaPlayingStep(StepBase):
    action: Literal["browser.wait_media_playing"]
    selector: str = Field(min_length=1)
    sample_seconds: float = Field(default=0.25, gt=0)
    on_timeout: list[Any] = Field(default_factory=list)

    @field_validator("selector")
    @classmethod
    def reject_blank_selector(cls, value: str) -> str:
        return _required_text("selector", value)

    @model_validator(mode="after")
    def validate_on_timeout_steps(self) -> "BrowserWaitMediaPlayingStep":
        self.on_timeout = _validate_workflow_step_list(self.on_timeout, field_name="on_timeout")
        return self


class BrowserWaitTextStep(StepBase):
    action: Literal["browser.wait_text"]
    text: str = Field(min_length=1)
    exact: bool = True
    on_timeout: list[Any] = Field(default_factory=list)

    @field_validator("text")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        return _required_text("text", value)

    @model_validator(mode="after")
    def validate_on_timeout_steps(self) -> "BrowserWaitTextStep":
        self.on_timeout = _validate_workflow_step_list(self.on_timeout, field_name="on_timeout")
        return self


class BrowserWaitTitleStep(StepBase):
    action: Literal["browser.wait_title"]
    title: str | None = None
    title_contains: str | None = None
    on_timeout: list[Any] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_title_matcher(self) -> "BrowserWaitTitleStep":
        _require_one_text_field(
            "browser.wait_title",
            {"title": self.title, "title_contains": self.title_contains},
        )
        self.on_timeout = _validate_workflow_step_list(self.on_timeout, field_name="on_timeout")
        return self


class BrowserWaitUrlStep(StepBase):
    action: Literal["browser.wait_url"]
    url: str | None = None
    url_contains: str | None = None
    on_timeout: list[Any] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_url_matcher(self) -> "BrowserWaitUrlStep":
        _require_one_text_field(
            "browser.wait_url",
            {"url": self.url, "url_contains": self.url_contains},
        )
        self.on_timeout = _validate_workflow_step_list(self.on_timeout, field_name="on_timeout")
        return self


class BrowserElementVisibleStep(StepBase):
    action: Literal["browser.element_visible"]
    text: str | None = None
    role: str | None = None
    accessible_name: str | None = None
    test_id: str | None = None
    exact: bool = True
    on_timeout: list[Any] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_structured_locator(self) -> "BrowserElementVisibleStep":
        _validate_browser_locator(
            "browser.element_visible",
            text=self.text,
            role=self.role,
            accessible_name=self.accessible_name,
            test_id=self.test_id,
        )
        self.on_timeout = _validate_workflow_step_list(self.on_timeout, field_name="on_timeout")
        return self


class BrowserClickTextStep(StepBase):
    action: Literal["browser.click_text"]
    text: str = Field(min_length=1)
    exact: bool = True

    @field_validator("text")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        return _required_text("text", value)

    @model_validator(mode="after")
    def enforce_browser_click_text_safety(self) -> "BrowserClickTextStep":
        _enforce_browser_click_safety("browser.click_text", self.text, self.requires_confirmation)
        return self


class BrowserClickRoleStep(StepBase):
    action: Literal["browser.click_role"]
    role: str = Field(min_length=1)
    accessible_name: str = Field(min_length=1)
    exact: bool = True

    @field_validator("role", "accessible_name")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        return _required_text("target", value)

    @model_validator(mode="after")
    def enforce_browser_click_role_safety(self) -> "BrowserClickRoleStep":
        _enforce_browser_click_safety(
            "browser.click_role",
            self.accessible_name,
            self.requires_confirmation,
        )
        return self


class BrowserClickTestIdStep(StepBase):
    action: Literal["browser.click_test_id"]
    test_id: str = Field(min_length=1)

    @field_validator("test_id")
    @classmethod
    def reject_blank_test_id(cls, value: str) -> str:
        return _required_text("test_id", value)

    @model_validator(mode="after")
    def enforce_browser_click_test_id_safety(self) -> "BrowserClickTestIdStep":
        _enforce_browser_click_safety(
            "browser.click_test_id",
            self.test_id,
            self.requires_confirmation,
        )
        return self


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


class WindowTitleScopeMixin(BaseModel):
    title_contains: str

    @field_validator("title_contains")
    @classmethod
    def require_window_title_scope(cls, value: str) -> str:
        if not value.strip():
            raise SafetyError("window layout actions require title_contains")
        return value


class WindowFocusStep(WindowMatchMixin, StepBase):
    action: Literal["window.focus"]


class WindowMinimizeStep(WindowMatchMixin, StepBase):
    action: Literal["window.minimize"]


class WindowMoveStep(WindowTitleScopeMixin, StepBase):
    action: Literal["window.move"]
    x: int
    y: int


class WindowResizeStep(WindowTitleScopeMixin, StepBase):
    action: Literal["window.resize"]
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class WindowMaximizeStep(WindowMatchMixin, StepBase):
    action: Literal["window.maximize"]


class WindowRestoreStep(WindowTitleScopeMixin, StepBase):
    action: Literal["window.restore"]


class WindowSnapLeftStep(WindowTitleScopeMixin, StepBase):
    action: Literal["window.snap_left"]


class WindowSnapRightStep(WindowTitleScopeMixin, StepBase):
    action: Literal["window.snap_right"]


class WindowSnapTopStep(WindowTitleScopeMixin, StepBase):
    action: Literal["window.snap_top"]


class WindowSnapBottomStep(WindowTitleScopeMixin, StepBase):
    action: Literal["window.snap_bottom"]


class WindowWaitStep(WindowMatchMixin, StepBase):
    action: Literal["window.wait"]
    on_timeout: list[Any] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_on_timeout_steps(self) -> "WindowWaitStep":
        self.on_timeout = _validate_workflow_step_list(self.on_timeout, field_name="on_timeout")
        return self


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
        cleaned = [key.strip() for key in value if key.strip()]
        if not cleaned:
            raise ValueError("keys must contain at least one non-empty key")
        return cleaned


class ConfirmAskStep(StepBase):
    action: Literal["confirm.ask"]
    prompt: str


class TargetInspectStep(StepBase):
    action: Literal["target.inspect"]
    target: str = Field(min_length=1)

    @field_validator("target")
    @classmethod
    def reject_blank_target(cls, value: str) -> str:
        return _required_text("target", value)


class TargetWaitStateStep(StepBase):
    action: Literal["target.wait_state"]
    target: str = Field(min_length=1)
    states: list[str] = Field(default_factory=list)
    readiness_states: list[str] = Field(default_factory=list)

    @field_validator("target")
    @classmethod
    def reject_blank_target(cls, value: str) -> str:
        return _required_text("target", value)

    @field_validator("states", "readiness_states")
    @classmethod
    def normalize_state_names(cls, value: list[str]) -> list[str]:
        return [_required_text("state", item) for item in value]

    @model_validator(mode="after")
    def require_expected_state(self) -> "TargetWaitStateStep":
        if not self.states and not self.readiness_states:
            raise ValueError("target.wait_state requires states or readiness_states")
        return self


class HumanPromptStep(StepBase):
    action: Literal["human.prompt"]
    prompt: str = Field(min_length=1)

    @field_validator("prompt")
    @classmethod
    def reject_blank_prompt(cls, value: str) -> str:
        return _required_text("prompt", value)


class HumanChecklistStep(StepBase):
    action: Literal["human.checklist"]
    prompt: str = Field(min_length=1)
    items: list[str] = Field(min_length=1)

    @field_validator("prompt")
    @classmethod
    def reject_blank_prompt(cls, value: str) -> str:
        return _required_text("prompt", value)

    @field_validator("items")
    @classmethod
    def reject_blank_items(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value]
        if any(not item for item in cleaned):
            raise ValueError("checklist items must not be blank")
        return cleaned


class HumanConfirmEvidenceStep(StepBase):
    action: Literal["human.confirm_evidence"]
    prompt: str = Field(min_length=1)
    evidence: list[str] = Field(min_length=1)

    @field_validator("prompt")
    @classmethod
    def reject_blank_prompt(cls, value: str) -> str:
        return _required_text("prompt", value)

    @field_validator("evidence")
    @classmethod
    def reject_blank_evidence(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value]
        if any(not item for item in cleaned):
            raise ValueError("evidence items must not be blank")
        return cleaned


class NoteAddStep(StepBase):
    action: Literal["note.add"]
    text: str = Field(min_length=1)

    @field_validator("text")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        return _required_text("text", value)


def _required_text(field_name: str, value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name} must not be blank")
    return cleaned


class WaitSecondsStep(StepBase):
    action: Literal["wait.seconds"]
    seconds: float = Field(gt=0)
    on_timeout: list[Any] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_on_timeout_steps(self) -> "WaitSecondsStep":
        self.on_timeout = _validate_workflow_step_list(self.on_timeout, field_name="on_timeout")
        return self


class WaitForUserStep(StepBase):
    action: Literal["wait.for_user"]
    prompt: str = Field(min_length=1)
    on_timeout: list[Any] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_on_timeout_steps(self) -> "WaitForUserStep":
        self.on_timeout = _validate_workflow_step_list(self.on_timeout, field_name="on_timeout")
        return self


class WaitForFileStep(StepBase):
    action: Literal["wait.for_file"]
    path: str = Field(min_length=1)
    on_timeout: list[Any] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_on_timeout_steps(self) -> "WaitForFileStep":
        self.on_timeout = _validate_workflow_step_list(self.on_timeout, field_name="on_timeout")
        return self


class WaitForProcessStep(StepBase):
    action: Literal["wait.for_process"]
    process_name: str = Field(min_length=1)
    on_timeout: list[Any] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_on_timeout_steps(self) -> "WaitForProcessStep":
        self.on_timeout = _validate_workflow_step_list(self.on_timeout, field_name="on_timeout")
        return self


class WaitForProcessExitStep(StepBase):
    action: Literal["wait.for_process_exit"]
    process_name: str = Field(min_length=1)
    on_timeout: list[Any] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_on_timeout_steps(self) -> "WaitForProcessExitStep":
        self.on_timeout = _validate_workflow_step_list(self.on_timeout, field_name="on_timeout")
        return self


class WaitForWindowStep(WindowMatchMixin, StepBase):
    action: Literal["wait.for_window"]
    on_timeout: list[Any] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_on_timeout_steps(self) -> "WaitForWindowStep":
        self.on_timeout = _validate_workflow_step_list(self.on_timeout, field_name="on_timeout")
        return self


class WaitForWindowGoneStep(WindowMatchMixin, StepBase):
    action: Literal["wait.for_window_gone"]
    on_timeout: list[Any] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_on_timeout_steps(self) -> "WaitForWindowGoneStep":
        self.on_timeout = _validate_workflow_step_list(self.on_timeout, field_name="on_timeout")
        return self


class NotifyToastStep(StepBase):
    action: Literal["notify.toast"]
    title: str = Field(min_length=1)
    message: str = Field(min_length=1)


class NotifySoundStep(StepBase):
    action: Literal["notify.sound"]
    path: str | None = None


class NotifyBeepStep(StepBase):
    action: Literal["notify.beep"]


class FlowIfStep(StepBase):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    action: Literal["flow.if"]
    condition: Condition
    then: list[Any] = Field(default_factory=list)
    else_: list[Any] = Field(default_factory=list, alias="else")

    @model_validator(mode="after")
    def validate_branch_steps(self) -> "FlowIfStep":
        self.then = _validate_workflow_step_list(self.then, field_name="then")
        self.else_ = _validate_workflow_step_list(self.else_, field_name="else")
        return self


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
    | BrowserOpenNativeStep
    | BrowserMediaStep
    | BrowserWaitMediaPlayingStep
    | BrowserWaitTextStep
    | BrowserWaitTitleStep
    | BrowserWaitUrlStep
    | BrowserElementVisibleStep
    | BrowserClickTextStep
    | BrowserClickRoleStep
    | BrowserClickTestIdStep
    | AppLaunchStep
    | AppWaitProcessStep
    | WindowFocusStep
    | WindowMinimizeStep
    | WindowMoveStep
    | WindowResizeStep
    | WindowMaximizeStep
    | WindowRestoreStep
    | WindowSnapLeftStep
    | WindowSnapRightStep
    | WindowSnapTopStep
    | WindowSnapBottomStep
    | WindowWaitStep
    | DesktopClickTextStep
    | InputHotkeyStep
    | ConfirmAskStep
    | TargetInspectStep
    | TargetWaitStateStep
    | HumanPromptStep
    | HumanChecklistStep
    | HumanConfirmEvidenceStep
    | NoteAddStep
    | WaitSecondsStep
    | WaitForUserStep
    | WaitForFileStep
    | WaitForProcessStep
    | WaitForProcessExitStep
    | WaitForWindowStep
    | WaitForWindowGoneStep
    | AssertFileExistsStep
    | AssertPathExistsStep
    | AssertProcessRunningStep
    | AssertWindowExistsStep
    | AssertWindowTextVisibleStep
    | AssertBrowserTextVisibleStep
    | AssertRegistryValueStep
    | NotifyToastStep
    | NotifySoundStep
    | NotifyBeepStep
    | FlowIfStep,
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
        return [
            *self.preflight,
            *_flatten_workflow_steps(self.steps),
            *self.verify,
        ]

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


_PREDICATE_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "value.equals": ("left", "right"),
    "file.exists": ("path",),
    "path.exists": ("path",),
    "process.running": ("process_name",),
    "window.exists": (),
    "window.text_visible": ("window_title_contains", "text"),
    "browser.text_visible": ("text",),
    "target.state": ("target",),
    "target.readiness_state": ("target",),
}

_PREDICATE_ALLOWED_FIELDS: dict[str, set[str]] = {
    "value.equals": {"left", "right"},
    "file.exists": {"path"},
    "path.exists": {"path"},
    "process.running": {"process_name"},
    "window.exists": {"title_contains", "process_name"},
    "window.text_visible": {"window_title_contains", "text", "control_type", "exact"},
    "browser.text_visible": {"text", "exact"},
    "target.state": {"target", "state", "states"},
    "target.readiness_state": {"target", "readiness_state", "readiness_states"},
}


def _validate_predicate_fields(condition: Condition) -> None:
    predicate_type = condition.type
    if predicate_type is None:
        return
    if predicate_type == "value.equals":
        missing = [name for name in ("left", "right") if name not in condition.model_fields_set]
        if missing:
            raise ValueError(f"condition value.equals requires {', '.join(missing)}")
    else:
        required = _PREDICATE_REQUIRED_FIELDS[predicate_type]
        for field_name in required:
            value = getattr(condition, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"condition {predicate_type} requires {field_name}")
    if predicate_type == "window.exists" and not (
        condition.title_contains or condition.process_name
    ):
        raise ValueError("condition window.exists requires title_contains or process_name")
    if predicate_type == "target.state" and not _has_one_or_more_states(
        condition.state,
        condition.states,
    ):
        raise ValueError("condition target.state requires state or states")
    if predicate_type == "target.readiness_state" and not _has_one_or_more_states(
        condition.readiness_state,
        condition.readiness_states,
    ):
        raise ValueError("condition target.readiness_state requires readiness_state or readiness_states")
    allowed = _PREDICATE_ALLOWED_FIELDS[predicate_type]
    for field_name in _provided_condition_fields(condition) - {"type"}:
        if field_name not in allowed:
            raise ValueError(f"condition {predicate_type} does not support {field_name}")
    if condition.control_type is not None and not condition.control_type.strip():
        raise ValueError("condition control_type must not be blank")
    if condition.target is not None and not condition.target.strip():
        raise ValueError("condition target must not be blank")
    for field_name in ("state", "readiness_state"):
        value = getattr(condition, field_name)
        if value is not None and not value.strip():
            raise ValueError(f"condition {field_name} must not be blank")
    for field_name in ("states", "readiness_states"):
        values = getattr(condition, field_name)
        if values is not None and (not values or any(not item.strip() for item in values)):
            raise ValueError(f"condition {field_name} must contain non-blank values")


def _has_one_or_more_states(state: str | None, states: list[str] | None) -> bool:
    return bool((isinstance(state, str) and state.strip()) or states)


def _require_one_text_field(action: str, values: dict[str, str | None]) -> None:
    provided = [name for name, value in values.items() if isinstance(value, str) and value.strip()]
    if len(provided) != 1:
        choices = ", ".join(values)
        raise ValueError(f"{action} requires exactly one of {choices}")


def _required_http_url(action: str, value: str) -> str:
    cleaned = _required_text("url", value)
    try:
        parsed = urlsplit(cleaned)
    except ValueError as exc:
        raise ValueError(f"{action} requires an HTTP or HTTPS URL") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{action} requires an HTTP or HTTPS URL")
    return cleaned


def _validate_browser_locator(
    action: str,
    *,
    text: str | None,
    role: str | None,
    accessible_name: str | None,
    test_id: str | None,
) -> None:
    locators = [
        bool(isinstance(text, str) and text.strip()),
        bool(isinstance(role, str) and role.strip()),
        bool(isinstance(test_id, str) and test_id.strip()),
    ]
    if sum(locators) != 1:
        raise ValueError(f"{action} requires exactly one structured locator: text, role, or test_id")
    if role is not None and role.strip():
        if not isinstance(accessible_name, str) or not accessible_name.strip():
            raise ValueError(f"{action} role locator requires accessible_name")
    elif accessible_name is not None:
        raise ValueError(f"{action} accessible_name is only supported with role")


def _enforce_browser_click_safety(
    action: str,
    target: str,
    requires_confirmation: bool,
) -> None:
    normalized = target.strip().casefold()
    if not normalized:
        raise ValueError(f"{action} target must not be blank")
    if is_risky_browser_click_target(normalized) and not requires_confirmation:
        raise SafetyError(
            f"{action} with target '{target.strip()}' requires requires_confirmation: true"
        )


def is_risky_browser_click_target(target: str) -> bool:
    tokens = {token.casefold() for token in _WORD_PATTERN.findall(target)}
    return bool(tokens.intersection(RISKY_BROWSER_CLICK_TARGETS))


def _validate_composition_fields(condition: Condition) -> None:
    operator = "all" if condition.all is not None else "any" if condition.any is not None else "not"
    provided = _provided_condition_fields(condition)
    if provided - {operator}:
        unsupported = ", ".join(sorted(provided - {operator}))
        raise ValueError(f"condition.{operator} does not support {unsupported}")


def _provided_condition_fields(condition: Condition) -> set[str]:
    fields: set[str] = set()
    for field_name in condition.model_fields_set:
        fields.add("not" if field_name == "not_" else field_name)
    return fields


def _validate_workflow_step_list(raw_steps: list[Any], *, field_name: str) -> list[Any]:
    if not raw_steps:
        return []
    try:
        return TypeAdapter(list[WorkflowStep]).validate_python(raw_steps)
    except Exception as exc:  # noqa: BLE001 - preserve pydantic context in message.
        raise ValueError(f"{field_name} must contain valid Setpiece steps: {exc}") from exc


def _flatten_workflow_steps(steps: list[Any]) -> list[ExecutableStep]:
    flattened: list[ExecutableStep] = []
    for step in steps:
        flattened.append(step)
        if isinstance(step, FlowIfStep):
            flattened.extend(_flatten_workflow_steps(step.then))
            flattened.extend(_flatten_workflow_steps(step.else_))
        timeout_steps = getattr(step, "on_timeout", None) or []
        flattened.extend(_flatten_workflow_steps(timeout_steps))
    return flattened
