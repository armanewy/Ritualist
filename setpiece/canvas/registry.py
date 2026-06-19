from __future__ import annotations

from pathlib import Path
from typing import Iterable

from setpiece.recipe_loader import discover_recipes
from setpiece.shortcuts import validate_shortcut_props
from setpiece.target_resolution import builtin_target_catalog

from .models import (
    CanvasBindingKind,
    CanvasComponent,
    CanvasComponentBinding,
    CanvasComponentPropSchema,
    CanvasComponentRisk,
    CanvasComponentType,
    CanvasDocument,
    CanvasImportedPolicy,
    CanvasPerformanceClass,
    CanvasPropType,
    CanvasUpdateBehavior,
    CanvasValidationResult,
)
from .theme_bridge import validate_canvas_theme_selection

_SUSPICIOUS_ASSET_SUFFIXES = {
    ".bat",
    ".cmd",
    ".com",
    ".dll",
    ".exe",
    ".js",
    ".lnk",
    ".msi",
    ".ps1",
    ".py",
    ".scr",
    ".sh",
    ".url",
    ".vbs",
}


class CanvasComponentRegistry:
    def __init__(self, component_types: Iterable[CanvasComponentType] = ()) -> None:
        self._types: dict[str, CanvasComponentType] = {}
        for component_type in component_types:
            self.register(component_type)

    def register(self, component_type: CanvasComponentType) -> None:
        if component_type.type_id in self._types:
            raise ValueError(f"duplicate canvas component type: {component_type.type_id}")
        self._types[component_type.type_id] = component_type

    def has(self, type_id: str) -> bool:
        return type_id in self._types

    def get(self, type_id: str) -> CanvasComponentType:
        return self._types[type_id]

    def all(self) -> tuple[CanvasComponentType, ...]:
        return tuple(self._types[key] for key in sorted(self._types))

    def to_dict(self) -> list[dict[str, object]]:
        return [component_type.to_dict() for component_type in self.all()]


def create_component_registry() -> CanvasComponentRegistry:
    registry = CanvasComponentRegistry()
    for component_type in _builtin_component_types():
        registry.register(component_type)
    return registry


def validate_canvas_document(
    document: CanvasDocument,
    *,
    registry: CanvasComponentRegistry | None = None,
    strict: bool = False,
    imported: bool = False,
    canvas_dir: Path | None = None,
    check_bindings: bool = True,
) -> CanvasValidationResult:
    """Validate a canvas document.

    By default this performs live binding checks against installed recipes and
    known targets. UI code that needs a cheap, side-effect-free check should
    call validate_canvas_structure instead.
    """
    resolved_registry = registry or create_component_registry()
    errors: list[str] = []
    warnings: list[str] = []
    recipe_ids = _installed_recipe_ids() if check_bindings else set()
    target_ids = _target_ids() if check_bindings else set()
    theme = validate_canvas_theme_selection(document)
    errors.extend(f"theme: {error}" for error in theme.errors)
    warnings.extend(f"theme: {warning}" for warning in theme.warnings)

    for component in document.components:
        try:
            spec = resolved_registry.get(component.type)
        except KeyError:
            errors.append(f"{component.id}: unknown component type '{component.type}'")
            continue

        _validate_component_against_spec(
            component,
            spec,
            errors=errors,
            warnings=warnings,
            strict=strict,
            imported=imported,
            canvas_dir=canvas_dir,
            recipe_ids=recipe_ids,
            target_ids=target_ids,
            check_bindings=check_bindings,
        )

    if strict:
        errors.extend(warnings)
        warnings = []
    return CanvasValidationResult(
        canvas_id=document.id,
        valid=not errors,
        strict=strict,
        errors=tuple(errors),
        warnings=tuple(warnings),
        component_count=len(document.components),
    )


def validate_canvas_structure(
    document: CanvasDocument,
    *,
    registry: CanvasComponentRegistry | None = None,
    strict: bool = False,
    imported: bool = False,
    canvas_dir: Path | None = None,
) -> CanvasValidationResult:
    """Run cheap structural validation without recipe or target discovery."""
    return validate_canvas_document(
        document,
        registry=registry,
        strict=strict,
        imported=imported,
        canvas_dir=canvas_dir,
        check_bindings=False,
    )


def validate_canvas_bindings(
    document: CanvasDocument,
    *,
    registry: CanvasComponentRegistry | None = None,
    strict: bool = False,
    imported: bool = False,
    canvas_dir: Path | None = None,
) -> CanvasValidationResult:
    """Run full validation, including live recipe and target binding checks."""
    return validate_canvas_document(
        document,
        registry=registry,
        strict=strict,
        imported=imported,
        canvas_dir=canvas_dir,
        check_bindings=True,
    )


def normalize_canvas_bindings(document: CanvasDocument) -> CanvasDocument:
    """Return a copy with legacy binding props mirrored into binding objects."""
    components: list[CanvasComponent] = []
    for component in document.components:
        if component.binding is not None:
            components.append(component)
            continue
        props = component.props_dict()
        binding_kind = _legacy_binding_kind(component, props)
        if binding_kind is None or binding_kind is CanvasBindingKind.STATIC:
            components.append(component)
            continue
        reference = _legacy_binding_reference(binding_kind, props)
        if not reference:
            components.append(component)
            continue
        components.append(component.model_copy(update={"binding": _binding_for(binding_kind, reference)}))
    return document.model_copy(update={"components": tuple(components)}, deep=True)


def _validate_component_against_spec(
    component: CanvasComponent,
    spec: CanvasComponentType,
    *,
    errors: list[str],
    warnings: list[str],
    strict: bool,
    imported: bool,
    canvas_dir: Path | None,
    recipe_ids: set[str],
    target_ids: set[str],
    check_bindings: bool,
) -> None:
    props = component.props_dict()
    if component.width < spec.min_width or component.height < spec.min_height:
        errors.append(
            f"{component.id}: size {component.width:g}x{component.height:g} is below "
            f"minimum {spec.min_width}x{spec.min_height}"
        )
    if spec.max_width is not None and component.width > spec.max_width:
        errors.append(f"{component.id}: width exceeds maximum {spec.max_width}")
    if spec.max_height is not None and component.height > spec.max_height:
        errors.append(f"{component.id}: height exceeds maximum {spec.max_height}")

    for prop in spec.required_props:
        if _blank(props.get(prop)):
            errors.append(f"{component.id}: missing required prop '{prop}'")

    _validate_no_arbitrary_code(component, props, errors)
    _validate_no_auto_run(component, props, errors)
    _validate_image_path(component, props, canvas_dir, errors)
    shortcut_errors, shortcut_warnings = validate_shortcut_props(
        component.id,
        component.type,
        props,
        imported=imported,
    )
    errors.extend(shortcut_errors)
    warnings.extend(shortcut_warnings)

    if imported and (
        not spec.allowed_in_untrusted_packs
        or spec.imported_canvas_policy is CanvasImportedPolicy.BLOCKED
    ):
        errors.append(f"{component.id}: component type '{spec.type_id}' is blocked in imported canvases")
    elif imported and spec.imported_canvas_policy is CanvasImportedPolicy.DISCLOSURE_REQUIRED:
        warnings.append(f"{component.id}: component type '{spec.type_id}' requires import disclosure")

    binding = component.binding
    legacy_binding_kind = _legacy_binding_kind(component, props)
    if binding is None and legacy_binding_kind is None:
        return

    binding_kind = binding.kind if binding is not None else legacy_binding_kind
    if binding_kind not in spec.supported_bindings:
        errors.append(f"{component.id}: {spec.type_id} does not support {binding_kind.value} bindings")
        return
    if binding is None:
        reference = _legacy_binding_reference(binding_kind, props)
        if binding_kind is CanvasBindingKind.RECIPE and check_bindings:
            _warn_unresolved(reference, recipe_ids, component.id, "recipe", warnings)
        elif binding_kind is CanvasBindingKind.TARGET_START and check_bindings:
            _warn_unresolved(reference, target_ids, component.id, "target", warnings)
        elif binding_kind is CanvasBindingKind.APP_LAUNCHER:
            _validate_launcher_binding(reference, component.id, props, errors)
        return

    reference = binding.reference
    if binding.kind is CanvasBindingKind.RECIPE and check_bindings:
        _warn_unresolved(reference, recipe_ids, component.id, "recipe", warnings)
    elif binding.kind is CanvasBindingKind.TARGET_START and check_bindings:
        _warn_unresolved(reference, target_ids, component.id, "target", warnings)
    elif binding.kind is CanvasBindingKind.INTENT and check_bindings:
        _validate_intent_reference(reference, component.id, errors, warnings)
    elif binding.kind is CanvasBindingKind.APP_LAUNCHER:
        _validate_launcher_binding(reference, component.id, props, errors)


def _builtin_component_types() -> tuple[CanvasComponentType, ...]:
    return (
        _component(
            "ritual.card",
            "Ritual Card",
            "ritual",
            "Recipe or intent card that can expose runbook actions.",
            supported=(CanvasBindingKind.RECIPE, CanvasBindingKind.INTENT, CanvasBindingKind.TARGET_START),
            required=("title",),
            optional=("subtitle", "description", "recipe_id", "primary_action", "accent", "image"),
            props=(
                _prop("title", CanvasPropType.STRING, required=True, hint="single_line"),
                _prop("subtitle", CanvasPropType.STRING, hint="single_line"),
                _prop("description", CanvasPropType.STRING, hint="multiline"),
                _prop("recipe_id", CanvasPropType.RECIPE_ID, hint="recipe_picker"),
                _prop(
                    "primary_action",
                    CanvasPropType.ENUM,
                    default="run",
                    allowed=("run", "dry_run", "doctor", "preview_plan"),
                    hint="segmented_action",
                ),
                _prop("accent", CanvasPropType.COLOR, hint="color"),
                _prop("image", CanvasPropType.LOCAL_ASSET_PATH, hint="image_asset"),
            ),
            size=(520, 300),
            minimum=(240, 140),
            behavior=CanvasUpdateBehavior.USER_INTERACTION_ONLY,
            risk=CanvasComponentRisk.CONTROLS_UI,
            can_trigger=True,
            display_only=False,
            requires_policy=True,
            actions=(
                "run",
                "dry_run",
                "doctor",
                "view_recipe",
                "edit_setup",
                "edit_recipe",
                "open_yaml",
                "open_logs",
            ),
            untrusted=False,
        ),
        _component(
            "ritual.status",
            "Ritual Status",
            "ritual",
            "Displays current or last run state for a recipe.",
            supported=(CanvasBindingKind.RECIPE, CanvasBindingKind.RUNTIME_STATE),
            optional=("recipe_id", "title"),
            size=(520, 120),
            minimum=(200, 80),
            behavior=CanvasUpdateBehavior.RUNTIME_EVENT_DRIVEN,
        ),
        _component(
            "ritual.controller",
            "Ritual Controller",
            "ritual",
            "Pause, resume, and stop controls for an active ritual.",
            supported=(CanvasBindingKind.RECIPE, CanvasBindingKind.RUNTIME_STATE),
            optional=("recipe_id", "controls"),
            size=(360, 96),
            minimum=(240, 72),
            behavior=CanvasUpdateBehavior.USER_INTERACTION_ONLY,
            risk=CanvasComponentRisk.CONTROLS_UI,
            can_trigger=True,
            display_only=False,
            requires_policy=True,
            actions=("pause", "resume", "stop", "open_run_log"),
            untrusted=False,
        ),
        _component(
            "target.card",
            "Target Card",
            "target",
            "Target start plan card backed by Target Resolution.",
            supported=(CanvasBindingKind.TARGET_START, CanvasBindingKind.INTENT),
            required=("title",),
            optional=("target", "subtitle", "primary_action"),
            props=(
                _prop("title", CanvasPropType.STRING, required=True, hint="single_line"),
                _prop("target", CanvasPropType.TARGET_ID, hint="target_picker"),
                _prop("target_id", CanvasPropType.TARGET_ID, hint="target_picker"),
                _prop("subtitle", CanvasPropType.STRING, hint="single_line"),
                _prop(
                    "primary_action",
                    CanvasPropType.ENUM,
                    default="preview_plan",
                    allowed=("preview_plan",),
                    hint="segmented_action",
                ),
            ),
            size=(360, 220),
            minimum=(220, 120),
            behavior=CanvasUpdateBehavior.USER_INTERACTION_ONLY,
            risk=CanvasComponentRisk.CONTROLS_UI,
            can_trigger=True,
            display_only=False,
            requires_policy=True,
            actions=("preview_plan",),
            untrusted=False,
        ),
        _component(
            "target.status",
            "Target Status",
            "target",
            "Displays target discovery or plan status.",
            supported=(CanvasBindingKind.TARGET_START, CanvasBindingKind.RUNTIME_STATE),
            optional=("target", "title"),
            size=(320, 120),
            minimum=(180, 80),
            behavior=CanvasUpdateBehavior.RUNTIME_EVENT_DRIVEN,
        ),
        _component(
            "category.dock",
            "Category Dock",
            "navigation",
            "Displays local canvas or ritual categories.",
            supported=(CanvasBindingKind.CATEGORY, CanvasBindingKind.STATIC),
            optional=("categories", "orientation"),
            size=(260, 420),
            minimum=(140, 160),
        ),
        _component(
            "app.launcher",
            "App Launcher",
            "launcher",
            "Legacy structured launcher alias for a configured local app shortcut.",
            supported=(CanvasBindingKind.APP_LAUNCHER, CanvasBindingKind.SHORTCUT_APP),
            required=("title",),
            optional=("path", "command", "app_id"),
            props=(
                _prop("title", CanvasPropType.STRING, required=True, hint="single_line"),
                _prop("path", CanvasPropType.LOCAL_APP_PATH, hint="local_app_picker"),
                _prop("command", CanvasPropType.LOCAL_APP_PATH, hint="legacy_local_app_picker"),
                _prop("app_id", CanvasPropType.STRING, hint="single_line"),
            ),
            size=(220, 96),
            minimum=(160, 64),
            behavior=CanvasUpdateBehavior.USER_INTERACTION_ONLY,
            risk=CanvasComponentRisk.LAUNCHES_APP,
            can_trigger=True,
            display_only=False,
            requires_policy=True,
            actions=("launch",),
            untrusted=False,
        ),
        _component(
            "shortcut.folder",
            "Folder Shortcut",
            "shortcut",
            "Instant native handoff that opens a reviewed local folder.",
            supported=(CanvasBindingKind.SHORTCUT_FOLDER, CanvasBindingKind.STATIC),
            required=("title",),
            optional=("path", "folder"),
            props=(
                _prop("title", CanvasPropType.STRING, required=True, hint="single_line"),
                _prop("path", CanvasPropType.LOCAL_FOLDER_PATH, hint="local_folder_picker"),
                _prop("folder", CanvasPropType.LOCAL_FOLDER_PATH, hint="legacy_local_folder_picker"),
            ),
            size=(240, 96),
            minimum=(160, 64),
            behavior=CanvasUpdateBehavior.USER_INTERACTION_ONLY,
            risk=CanvasComponentRisk.LAUNCHES_APP,
            can_trigger=True,
            display_only=False,
            requires_policy=True,
            actions=("open",),
            untrusted=True,
        ),
        _component(
            "shortcut.app",
            "App Shortcut",
            "shortcut",
            "Instant native handoff that launches a reviewed local executable or shortcut.",
            supported=(CanvasBindingKind.SHORTCUT_APP, CanvasBindingKind.APP_LAUNCHER, CanvasBindingKind.STATIC),
            required=("title",),
            optional=("path", "command", "app_id"),
            props=(
                _prop("title", CanvasPropType.STRING, required=True, hint="single_line"),
                _prop("path", CanvasPropType.LOCAL_APP_PATH, hint="local_app_picker"),
                _prop("command", CanvasPropType.LOCAL_APP_PATH, hint="legacy_local_app_picker"),
                _prop("app_id", CanvasPropType.STRING, hint="single_line"),
            ),
            size=(240, 96),
            minimum=(160, 64),
            behavior=CanvasUpdateBehavior.USER_INTERACTION_ONLY,
            risk=CanvasComponentRisk.LAUNCHES_APP,
            can_trigger=True,
            display_only=False,
            requires_policy=True,
            actions=("launch",),
            untrusted=True,
        ),
        _component(
            "shortcut.url",
            "URL Shortcut",
            "shortcut",
            "Instant native handoff that opens an http or https URL in the default browser.",
            supported=(CanvasBindingKind.SHORTCUT_URL, CanvasBindingKind.STATIC),
            required=("title", "url"),
            optional=(),
            props=(
                _prop("title", CanvasPropType.STRING, required=True, hint="single_line"),
                _prop("url", CanvasPropType.URL, required=True, hint="url"),
            ),
            size=(240, 96),
            minimum=(160, 64),
            behavior=CanvasUpdateBehavior.USER_INTERACTION_ONLY,
            risk=CanvasComponentRisk.LAUNCHES_APP,
            can_trigger=True,
            display_only=False,
            requires_policy=True,
            actions=("open",),
            untrusted=True,
        ),
        _component(
            "window.layout_button",
            "Window Layout Button",
            "window",
            "Button for a future reviewed window layout primitive plan.",
            supported=(CanvasBindingKind.WINDOW_LAYOUT, CanvasBindingKind.PRIMITIVE_PLAN_PREVIEW),
            required=("title",),
            optional=("layout_id",),
            size=(220, 96),
            minimum=(160, 64),
            behavior=CanvasUpdateBehavior.USER_INTERACTION_ONLY,
            risk=CanvasComponentRisk.CONTROLS_UI,
            can_trigger=True,
            display_only=False,
            requires_policy=True,
            actions=("preview_layout",),
            untrusted=False,
        ),
        _component(
            "doctor.badge",
            "Doctor Badge",
            "diagnostics",
            "Displays Doctor/policy status.",
            supported=(CanvasBindingKind.RECIPE, CanvasBindingKind.DOCTOR_STATUS, CanvasBindingKind.INTENT),
            optional=("recipe_id", "title"),
            size=(180, 80),
            minimum=(120, 48),
            behavior=CanvasUpdateBehavior.RUNTIME_EVENT_DRIVEN,
            can_trigger=True,
            display_only=False,
            requires_policy=True,
            actions=("doctor",),
            untrusted=False,
        ),
        _component(
            "recent.activity",
            "Recent Activity",
            "runtime",
            "Recent run and runtime activity feed.",
            supported=(CanvasBindingKind.RECENT_RUNS, CanvasBindingKind.RUNTIME_STATE),
            optional=("limit", "title"),
            props=(
                _prop("title", CanvasPropType.STRING, default="Recent Activity", hint="single_line"),
                _prop("limit", CanvasPropType.INT, default=10, hint="number"),
            ),
            size=(520, 180),
            minimum=(260, 100),
            behavior=CanvasUpdateBehavior.RUNTIME_EVENT_DRIVEN,
            performance=CanvasPerformanceClass.MODERATE,
            can_trigger=True,
            display_only=False,
            requires_policy=True,
            actions=("open_logs",),
            untrusted=False,
        ),
        _component(
            "clock",
            "Clock",
            "display",
            "Local clock display.",
            supported=(CanvasBindingKind.STATIC,),
            optional=("format", "timezone"),
            props=(
                _prop("format", CanvasPropType.STRING, default="%H:%M", hint="time_format"),
                _prop("timezone", CanvasPropType.STRING, hint="timezone"),
            ),
            size=(180, 80),
            minimum=(100, 48),
            behavior=CanvasUpdateBehavior.INTERVAL,
        ),
        _component(
            "text.label",
            "Text Label",
            "display",
            "Static text label.",
            supported=(CanvasBindingKind.STATIC,),
            required=("text",),
            optional=("size", "color", "align"),
            props=(
                _prop("text", CanvasPropType.STRING, required=True, hint="multiline"),
                _prop("size", CanvasPropType.INT, default=16, hint="font_size"),
                _prop("color", CanvasPropType.COLOR, hint="color"),
                _prop(
                    "align",
                    CanvasPropType.ENUM,
                    default="left",
                    allowed=("left", "center", "right"),
                    hint="alignment",
                ),
            ),
            size=(240, 64),
            minimum=(80, 32),
        ),
        _component(
            "image",
            "Image",
            "display",
            "Canvas-local image asset.",
            supported=(CanvasBindingKind.STATIC,),
            required=("path",),
            optional=("fit", "alt"),
            props=(
                _prop("path", CanvasPropType.LOCAL_ASSET_PATH, required=True, hint="image_asset"),
                _prop(
                    "fit",
                    CanvasPropType.ENUM,
                    default="cover",
                    allowed=("cover", "contain", "fill"),
                    hint="image_fit",
                ),
                _prop("alt", CanvasPropType.STRING, hint="single_line"),
            ),
            size=(320, 180),
            minimum=(80, 80),
            performance=CanvasPerformanceClass.MODERATE,
        ),
        _component(
            "shape",
            "Shape",
            "display",
            "Static visual shape.",
            supported=(CanvasBindingKind.STATIC,),
            optional=("shape", "fill", "stroke", "radius"),
            size=(160, 100),
            minimum=(32, 32),
        ),
        _component(
            "spacer/divider",
            "Spacer / Divider",
            "layout",
            "Static spacing or divider element.",
            supported=(CanvasBindingKind.STATIC,),
            optional=("orientation", "color"),
            size=(240, 16),
            minimum=(16, 4),
        ),
    )


def _component(
    type_id: str,
    display_name: str,
    category: str,
    description: str,
    *,
    supported: tuple[CanvasBindingKind, ...],
    required: tuple[str, ...] = (),
    optional: tuple[str, ...] = (),
    size: tuple[int, int],
    minimum: tuple[int, int],
    props: tuple[CanvasComponentPropSchema, ...] = (),
    behavior: CanvasUpdateBehavior = CanvasUpdateBehavior.STATIC,
    performance: CanvasPerformanceClass = CanvasPerformanceClass.CHEAP,
    risk: CanvasComponentRisk = CanvasComponentRisk.READ_ONLY,
    can_trigger: bool = False,
    display_only: bool = True,
    requires_policy: bool = False,
    actions: tuple[str, ...] = (),
    untrusted: bool = True,
) -> CanvasComponentType:
    return CanvasComponentType(
        type_id=type_id,
        display_name=display_name,
        category=category,
        description=description,
        supported_bindings=supported,
        required_props=required,
        optional_props=optional,
        prop_schemas=props,
        default_width=size[0],
        default_height=size[1],
        min_width=minimum[0],
        min_height=minimum[1],
        update_behavior=behavior,
        performance_class=performance,
        risk=risk,
        imported_canvas_policy=(
            CanvasImportedPolicy.ALLOWED if untrusted else CanvasImportedPolicy.DISCLOSURE_REQUIRED
        ),
        allowed_in_canvas_packs=True,
        allowed_in_untrusted_packs=untrusted,
        can_trigger_actions=can_trigger,
        display_only=display_only,
        requires_policy_or_doctor_state=requires_policy,
        actions=actions,
    )


def _prop(
    name: str,
    prop_type: CanvasPropType,
    *,
    required: bool = False,
    default: object | None = None,
    allowed: tuple[str, ...] = (),
    hint: str = "",
) -> CanvasComponentPropSchema:
    return CanvasComponentPropSchema(
        name=name,
        type=prop_type,
        required=required,
        default=default,
        allowed_values=allowed,
        editor_hint=hint,
    )


def _binding_for(kind: CanvasBindingKind, reference: str) -> CanvasComponentBinding:
    if kind is CanvasBindingKind.RECIPE:
        return CanvasComponentBinding(kind=kind, recipe_id=reference)
    if kind is CanvasBindingKind.TARGET_START:
        return CanvasComponentBinding(kind=kind, target=reference)
    if kind is CanvasBindingKind.INTENT:
        return CanvasComponentBinding(kind=kind, intent_id=reference)
    if kind is CanvasBindingKind.APP_LAUNCHER:
        return CanvasComponentBinding(kind=kind, id=reference)
    if kind in {CanvasBindingKind.SHORTCUT_FOLDER, CanvasBindingKind.SHORTCUT_APP}:
        return CanvasComponentBinding(kind=kind, path=reference)
    if kind is CanvasBindingKind.SHORTCUT_URL:
        return CanvasComponentBinding(kind=kind, url=reference)
    return CanvasComponentBinding(kind=kind, id=reference)


def _legacy_binding_kind(component: CanvasComponent, props: dict[str, object]) -> CanvasBindingKind | None:
    if "recipe_id" in props:
        return CanvasBindingKind.RECIPE
    if "target" in props or "target_id" in props:
        return CanvasBindingKind.TARGET_START
    if component.type == "shortcut.folder" and ("path" in props or "folder" in props):
        return CanvasBindingKind.SHORTCUT_FOLDER
    if component.type in {"shortcut.app", "app.launcher"} and (
        "path" in props or "command" in props or "app_id" in props
    ):
        return CanvasBindingKind.SHORTCUT_APP
    if component.type == "shortcut.url" and "url" in props:
        return CanvasBindingKind.SHORTCUT_URL
    if component.type in {"clock", "text.label", "image", "shape", "spacer/divider", "category.dock"}:
        return CanvasBindingKind.STATIC
    return None


def _legacy_binding_reference(kind: CanvasBindingKind, props: dict[str, object]) -> str:
    if kind is CanvasBindingKind.RECIPE:
        return str(props.get("recipe_id") or "").strip()
    if kind is CanvasBindingKind.TARGET_START:
        return str(props.get("target") or props.get("target_id") or "").strip()
    if kind is CanvasBindingKind.APP_LAUNCHER:
        return str(props.get("path") or props.get("command") or props.get("app_id") or "").strip()
    if kind is CanvasBindingKind.SHORTCUT_FOLDER:
        return str(props.get("path") or props.get("folder") or "").strip()
    if kind is CanvasBindingKind.SHORTCUT_APP:
        return str(props.get("path") or props.get("command") or "").strip()
    if kind is CanvasBindingKind.SHORTCUT_URL:
        return str(props.get("url") or "").strip()
    return ""


def _validate_no_arbitrary_code(
    component: CanvasComponent,
    props: dict[str, object],
    errors: list[str],
) -> None:
    forbidden = ("script", "javascript", "qml", "html", "webview", "code", "onclick", "on_click")
    for key, value in _walk_mapping(props):
        normalized = key.casefold()
        if any(marker in normalized for marker in forbidden):
            errors.append(f"{component.id}: arbitrary component code is not allowed ({key})")
        if isinstance(value, str) and "<script" in value.casefold():
            errors.append(f"{component.id}: script-like component content is not allowed")


def _validate_no_auto_run(
    component: CanvasComponent,
    props: dict[str, object],
    errors: list[str],
) -> None:
    for key in ("auto_run", "autorun", "run_on_load", "launch_on_load"):
        if bool(props.get(key)):
            errors.append(f"{component.id}: hidden auto-run behavior is not allowed")


def _validate_image_path(
    component: CanvasComponent,
    props: dict[str, object],
    canvas_dir: Path | None,
    errors: list[str],
) -> None:
    if component.type != "image":
        return
    raw = str(props.get("path") or "").strip()
    if not raw:
        return
    if "://" in raw:
        errors.append(f"{component.id}: remote image URLs are not allowed in Canvas v1")
        return
    path = Path(raw)
    if path.suffix.casefold() in _SUSPICIOUS_ASSET_SUFFIXES:
        errors.append(f"{component.id}: executable or script-like image asset paths are not allowed")
        return
    if not path.is_absolute() and any(":" in part for part in path.parts):
        errors.append(f"{component.id}: ambiguous drive-relative or stream-like image paths are not allowed")
        return
    if canvas_dir is None:
        if path.is_absolute() or ".." in path.parts:
            errors.append(f"{component.id}: image path must be a relative canvas asset path")
        return

    allowed_root = (canvas_dir / "assets").resolve()
    candidate = path
    if not path.is_absolute():
        candidate = canvas_dir / path if path.parts and path.parts[0] == "assets" else allowed_root / path
    try:
        resolved = candidate.resolve()
    except OSError:
        resolved = candidate.absolute()
    if resolved != allowed_root and allowed_root not in resolved.parents:
        errors.append(f"{component.id}: image path must stay inside the canvas assets folder")


def _validate_intent_reference(
    reference: str,
    component_id: str,
    errors: list[str],
    warnings: list[str],
) -> None:
    if not reference:
        warnings.append(f"{component_id}: intent binding is unresolved")
        return
    if reference in {"diagnostics.collect:minimal", "workspace.prepare:basic", "target.start:placeholder"}:
        return
    if reference.startswith("target.start:") and reference.removeprefix("target.start:").strip():
        return
    if "." not in reference:
        errors.append(f"{component_id}: intent binding '{reference}' is not a known fixture or intent kind")
    else:
        warnings.append(f"{component_id}: intent binding '{reference}' is not known locally yet")


def _validate_launcher_binding(
    reference: str,
    component_id: str,
    props: dict[str, object],
    errors: list[str],
) -> None:
    command = str(props.get("command") or reference or "").strip()
    if command.startswith(("http://", "https://")):
        errors.append(f"{component_id}: remote launcher URLs are not allowed")


def _warn_unresolved(
    reference: str,
    known: set[str],
    component_id: str,
    label: str,
    warnings: list[str],
) -> None:
    if not reference or reference not in known:
        warnings.append(f"{component_id}: {label} binding '{reference or '<missing>'}' is unresolved")


def _installed_recipe_ids() -> set[str]:
    ids: set[str] = set()
    for path, recipe, _error in discover_recipes():
        if recipe is not None:
            ids.add(recipe.id)
        else:
            ids.add(path.stem)
    return ids


def _target_ids() -> set[str]:
    return {target.id for target in builtin_target_catalog().targets}


def _blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _walk_mapping(value: object) -> list[tuple[str, object]]:
    rows: list[tuple[str, object]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            rows.append((str(key), item))
            rows.extend(_walk_mapping(item))
    elif isinstance(value, list):
        for item in value:
            rows.extend(_walk_mapping(item))
    return rows
