from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ritualist.models import SAFE_ID_PATTERN

CANVAS_SCHEMA_VERSION = "ritualist.canvas.v1"
CANVAS_VALIDATION_SCHEMA_VERSION = "ritualist.canvas.validation.v1"


class CanvasLayoutMode(StrEnum):
    DESKTOP_CANVAS = "desktop_canvas"
    IMMERSIVE_CANVAS = "immersive_canvas"


class CanvasResponsivePolicy(StrEnum):
    RESPONSIVE = "responsive"
    FIXED = "fixed"


class CanvasBindingKind(StrEnum):
    RECIPE = "recipe"
    INTENT = "intent"
    TARGET_START = "target.start"
    PRIMITIVE_PLAN_PREVIEW = "primitive_plan_preview"
    APP_LAUNCHER = "app.launcher"
    WINDOW_LAYOUT = "window.layout"
    RUNTIME_STATE = "runtime_state"
    DOCTOR_STATUS = "doctor_status"
    RECENT_RUNS = "recent_runs"
    CATEGORY = "category"
    STATIC = "static"


class CanvasUpdateBehavior(StrEnum):
    STATIC = "static"
    RUNTIME_EVENT_DRIVEN = "runtime_event_driven"
    INTERVAL = "interval"
    USER_INTERACTION_ONLY = "user_interaction_only"


class CanvasPerformanceClass(StrEnum):
    CHEAP = "cheap"
    MODERATE = "moderate"
    HEAVY = "heavy"


class CanvasComponentRisk(StrEnum):
    READ_ONLY = "read_only"
    LAUNCHES_APP = "launches_app"
    CONTROLS_UI = "controls_ui"
    MODIFIES_FILES = "modifies_files"
    RISKY = "risky"


class CanvasImportedPolicy(StrEnum):
    ALLOWED = "allowed"
    DISCLOSURE_REQUIRED = "disclosure_required"
    BLOCKED = "blocked"


class CanvasPropType(StrEnum):
    STRING = "string"
    BOOL = "bool"
    INT = "int"
    FLOAT = "float"
    ENUM = "enum"
    COLOR = "color"
    LOCAL_ASSET_PATH = "local_asset_path"
    RECIPE_ID = "recipe_id"
    TARGET_ID = "target_id"


class CanvasComponentPropSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    type: CanvasPropType
    required: bool = False
    default: Any | None = None
    allowed_values: tuple[str, ...] = ()
    editor_hint: str = ""

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("canvas component prop schema name must not be blank")
        return text

    @field_validator("allowed_values", mode="before")
    @classmethod
    def normalize_allowed_values(cls, value: object) -> tuple[str, ...]:
        return _string_tuple(value)

    @field_validator("editor_hint")
    @classmethod
    def normalize_editor_hint(cls, value: str) -> str:
        return value.strip()


class CanvasMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = "0.1"
    author: str = ""
    tags: tuple[str, ...] = ()
    use_mode_label: str = "Use Mode"
    edit_mode_label: str = "Edit Mode"

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, value: object) -> tuple[str, ...]:
        return _string_tuple(value)


class CanvasPackMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pack_id: str = ""
    imported: bool = False
    source: str = "local"
    remembered_approvals: tuple[str, ...] = ()

    @field_validator("remembered_approvals", mode="before")
    @classmethod
    def normalize_approvals(cls, value: object) -> tuple[str, ...]:
        approvals = _string_tuple(value)
        if approvals:
            raise ValueError("canvas packs must not carry remembered approvals")
        return approvals


class CanvasBackground(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = "solid"
    value: str = "#10141c"

    @field_validator("type", "value")
    @classmethod
    def nonblank(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("canvas background fields must not be blank")
        return text


class CanvasGrid(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    size: int = Field(default=16, ge=1, le=256)


class CanvasThemeTokens(BaseModel):
    model_config = ConfigDict(extra="forbid")

    background: str = "#10141c"
    foreground: str = "#f5f7fb"
    accent: str = "#3dd6a5"
    warning: str = "#f5c45b"
    danger: str = "#ff6b7a"


class CanvasTheme(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = "ritualist_default"
    name: str = "Ritualist Default"
    tokens: CanvasThemeTokens = Field(default_factory=CanvasThemeTokens)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not SAFE_ID_PATTERN.fullmatch(value):
            raise ValueError("canvas theme id must be a safe filename-like identifier")
        return value


class CanvasComponentProps(BaseModel):
    model_config = ConfigDict(extra="allow")

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__pydantic_extra__ or {})

    def get(self, key: str, default: Any = None) -> Any:
        return self.to_dict().get(key, default)


class CanvasComponentBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: CanvasBindingKind
    id: str | None = None
    recipe_id: str | None = None
    intent_id: str | None = None
    target: str | None = None
    target_id: str | None = None
    primitive_plan_id: str | None = None
    runtime_run_id: str | None = None
    category: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "id",
        "recipe_id",
        "intent_id",
        "target",
        "target_id",
        "primitive_plan_id",
        "runtime_run_id",
        "category",
    )
    @classmethod
    def strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @property
    def reference(self) -> str:
        if self.kind is CanvasBindingKind.RECIPE:
            return self.recipe_id or self.id or ""
        if self.kind is CanvasBindingKind.INTENT:
            return self.intent_id or self.id or ""
        if self.kind is CanvasBindingKind.TARGET_START:
            return self.target or self.target_id or self.id or ""
        if self.kind is CanvasBindingKind.PRIMITIVE_PLAN_PREVIEW:
            return self.primitive_plan_id or self.id or ""
        if self.kind is CanvasBindingKind.RUNTIME_STATE:
            return self.runtime_run_id or self.id or ""
        if self.kind is CanvasBindingKind.CATEGORY:
            return self.category or self.id or ""
        return self.id or ""

    def to_dict(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        return {key: value for key, value in data.items() if value not in (None, {}, ())}


class CanvasComponent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: str
    x: float = 0
    y: float = 0
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    z: int = 0
    props: CanvasComponentProps = Field(default_factory=CanvasComponentProps)
    binding: CanvasComponentBinding | None = None
    visible: bool = True
    locked: bool = False

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not SAFE_ID_PATTERN.fullmatch(value):
            raise ValueError("canvas component id must be a safe filename-like identifier")
        return value

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("canvas component type must not be blank")
        return text

    @field_validator("z")
    @classmethod
    def validate_z(cls, value: int) -> int:
        if value < -10000 or value > 10000:
            raise ValueError("canvas component z must be between -10000 and 10000")
        return value

    def props_dict(self) -> dict[str, Any]:
        return self.props.to_dict()

    def to_dict(self) -> dict[str, Any]:
        data = self.model_dump(mode="json", exclude={"props", "binding"})
        data["props"] = self.props.to_dict()
        if self.binding is not None:
            data["binding"] = self.binding.to_dict()
        return data


class CanvasComponentType(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type_id: str
    display_name: str
    category: str
    description: str
    supported_bindings: tuple[CanvasBindingKind, ...] = ()
    required_props: tuple[str, ...] = ()
    optional_props: tuple[str, ...] = ()
    prop_schemas: tuple[CanvasComponentPropSchema, ...] = ()
    default_width: int = Field(gt=0)
    default_height: int = Field(gt=0)
    min_width: int = Field(gt=0)
    min_height: int = Field(gt=0)
    max_width: int | None = None
    max_height: int | None = None
    update_behavior: CanvasUpdateBehavior = CanvasUpdateBehavior.STATIC
    performance_class: CanvasPerformanceClass = CanvasPerformanceClass.CHEAP
    risk: CanvasComponentRisk = CanvasComponentRisk.READ_ONLY
    imported_canvas_policy: CanvasImportedPolicy = CanvasImportedPolicy.ALLOWED
    allowed_in_canvas_packs: bool = True
    allowed_in_untrusted_packs: bool = True
    can_trigger_actions: bool = False
    display_only: bool = True
    requires_policy_or_doctor_state: bool = False
    actions: tuple[str, ...] = ()

    @field_validator("type_id")
    @classmethod
    def validate_type_id(cls, value: str) -> str:
        text = value.strip()
        if not text or any(marker in text.casefold() for marker in ("script", "webview", "html", "qml", "javascript")):
            raise ValueError("canvas component type id is not allowed")
        return text

    @field_validator("required_props", "optional_props", "actions", mode="before")
    @classmethod
    def normalize_strings(cls, value: object) -> tuple[str, ...]:
        return _string_tuple(value)

    @field_validator("prop_schemas", mode="before")
    @classmethod
    def normalize_prop_schemas(cls, value: object) -> tuple[object, ...]:
        if value is None:
            return ()
        if not isinstance(value, (list, tuple)):
            raise ValueError("canvas component prop schemas must be a list")
        return tuple(value)

    @field_validator("supported_bindings", mode="before")
    @classmethod
    def normalize_bindings(cls, value: object) -> tuple[CanvasBindingKind, ...]:
        if value is None:
            return ()
        rows = [value] if isinstance(value, str) else list(value) if isinstance(value, (list, tuple)) else value
        if not isinstance(rows, list):
            raise ValueError("supported bindings must be a list")
        return tuple(CanvasBindingKind(str(row)) for row in rows)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class CanvasDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: str = Field(default=CANVAS_SCHEMA_VERSION, alias="schema")
    id: str
    name: str
    description: str = ""
    mode: CanvasLayoutMode = CanvasLayoutMode.DESKTOP_CANVAS
    resolution_policy: CanvasResponsivePolicy = CanvasResponsivePolicy.RESPONSIVE
    metadata: CanvasMetadata = Field(default_factory=CanvasMetadata)
    pack: CanvasPackMetadata = Field(default_factory=CanvasPackMetadata)
    theme: CanvasTheme = Field(default_factory=CanvasTheme)
    background: CanvasBackground = Field(default_factory=CanvasBackground)
    grid: CanvasGrid = Field(default_factory=CanvasGrid)
    components: tuple[CanvasComponent, ...] = ()

    @field_validator("schema_version")
    @classmethod
    def validate_schema(cls, value: str) -> str:
        if value != CANVAS_SCHEMA_VERSION:
            raise ValueError(f"canvas schema must be {CANVAS_SCHEMA_VERSION}")
        return value

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not SAFE_ID_PATTERN.fullmatch(value):
            raise ValueError("canvas id must be a safe filename-like identifier")
        return value

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("canvas name must not be blank")
        return text

    @field_validator("components", mode="before")
    @classmethod
    def normalize_components(cls, value: object) -> tuple[object, ...]:
        if value is None:
            return ()
        if not isinstance(value, (list, tuple)):
            raise ValueError("canvas components must be a list")
        return tuple(value)

    @model_validator(mode="after")
    def validate_unique_component_ids(self) -> CanvasDocument:
        ids = [component.id for component in self.components]
        if len(ids) != len(set(ids)):
            raise ValueError("canvas component ids must be unique")
        return self

    def to_dict(self) -> dict[str, Any]:
        data = self.model_dump(mode="json", by_alias=True, exclude={"components"})
        data["components"] = [component.to_dict() for component in self.components]
        return data


class CanvasValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canvas_id: str
    valid: bool
    strict: bool = False
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    component_count: int = 0
    schema_version: str = CANVAS_VALIDATION_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class CanvasTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str = ""
    document: CanvasDocument

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not SAFE_ID_PATTERN.fullmatch(value):
            raise ValueError("canvas template id must be a safe filename-like identifier")
        return value


def _string_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    values = [value] if isinstance(value, str) else list(value) if isinstance(value, (list, tuple)) else value
    if not isinstance(values, list):
        raise ValueError("value must be a string or string list")
    return tuple(str(item).strip() for item in values if str(item).strip())
