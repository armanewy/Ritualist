from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ritualist.errors import RitualistError
from ritualist.paths import themes_path

THEME_SCHEMA_VERSION = "ritualist.theme.v1"
THEME_VALIDATION_SCHEMA_VERSION = "ritualist.theme.validation.v1"

THEME_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$")
TOKEN_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)+$")
HEX_COLOR_PATTERN = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
TOKEN_REFERENCE_PATTERN = re.compile(r"^\{([^{}]+)\}$")

TOKEN_NAMESPACES = {
    "color",
    "font",
    "radius",
    "spacing",
    "shadow",
    "motion",
    "opacity",
    "material",
}
VISUAL_ASSET_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
FORBIDDEN_KEYS = {
    "action",
    "actions",
    "behavior",
    "behaviors",
    "binding",
    "bindings",
    "code",
    "command",
    "commands",
    "exec",
    "html",
    "javascript",
    "on_click",
    "onclick",
    "python",
    "qml",
    "recipe",
    "recipes",
    "script",
    "steps",
}
FORBIDDEN_TEXT_MARKERS = (
    "<script",
    "javascript:",
    "python:",
    "import os",
    "subprocess",
    "eval(",
    "exec(",
    "function(",
    "=>",
)

APP_DEFAULT_TOKENS: dict[str, str | int | float] = {
    "color.background": "#10141c",
    "color.surface": "#101720",
    "color.surface_alt": "#0e151f",
    "color.text": "#f5f7fb",
    "color.text_muted": "#91a2b8",
    "color.border": "#203044",
    "color.accent": "#3dd6a5",
    "color.success": "#3dd6a5",
    "color.warning": "#f5c45b",
    "color.danger": "#ff6b7a",
    "font.family": "Segoe UI",
    "font.size_body": 13,
    "font.size_title": 26,
    "radius.sm": 4,
    "radius.md": 8,
    "radius.lg": 12,
    "spacing.sm": 6,
    "spacing.md": 12,
    "spacing.lg": 18,
    "shadow.card": "simple",
    "motion.fast_ms": 90,
    "motion.normal_ms": 160,
    "opacity.disabled": 0.55,
    "material.surface": "solid",
}


class ThemeDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: str = Field(default=THEME_SCHEMA_VERSION, alias="schema")
    id: str
    name: str
    version: str = "0.1.0"
    tokens: dict[str, Any] = Field(default_factory=dict)
    assets: dict[str, str] = Field(default_factory=dict)
    component_variants: dict[str, dict[str, Any]] = Field(default_factory=dict)

    @field_validator("schema_version")
    @classmethod
    def validate_schema(cls, value: str) -> str:
        if value != THEME_SCHEMA_VERSION:
            raise ValueError(f"theme schema must be {THEME_SCHEMA_VERSION}")
        return value

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        text = value.strip()
        if not THEME_ID_PATTERN.fullmatch(text):
            raise ValueError("theme id must be a safe dotted identifier")
        return text

    @field_validator("name", "version")
    @classmethod
    def validate_nonblank(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("theme fields must not be blank")
        return text

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", by_alias=True)


class ThemeValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    theme_id: str
    valid: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    token_count: int = 0
    asset_count: int = 0
    schema_version: str = THEME_VALIDATION_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


@dataclass(frozen=True)
class ThemeReference:
    theme_id: str
    name: str
    path: Path
    source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.theme_id,
            "name": self.name,
            "path": str(self.path),
            "source": self.source,
        }


@dataclass(frozen=True)
class ThemeResolution:
    tokens: dict[str, Any]
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def valid(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "tokens": self.tokens,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


def list_themes(*, include_bundled: bool = True) -> list[ThemeReference]:
    rows: dict[str, ThemeReference] = {}
    if include_bundled:
        for path in _bundled_theme_paths():
            reference = _reference_for_path(path, source="bundled")
            rows[reference.theme_id] = reference
    for path in sorted(themes_path().glob("*/theme.yaml")):
        reference = _reference_for_path(path, source="user")
        rows[reference.theme_id] = reference
    for path in sorted(themes_path().glob("*.yaml")):
        reference = _reference_for_path(path, source="user")
        rows[reference.theme_id] = reference
    return sorted(rows.values(), key=lambda row: (row.source != "bundled", row.theme_id))


def load_theme(id_or_path: str | Path) -> ThemeDocument:
    path = _resolve_theme_path(id_or_path)
    return _load_theme_path(path)


def theme_show_payload(theme: ThemeDocument, *, theme_dir: Path | None = None) -> dict[str, Any]:
    validation = validate_theme_document(theme, theme_dir=theme_dir)
    resolution = resolve_theme_tokens(theme)
    return {
        "schema_version": "ritualist.theme.show.v1",
        "theme": theme.to_dict(),
        "validation": validation.to_dict(),
        "resolution": resolution.to_dict(),
    }


def validate_theme(theme: ThemeDocument | str | Path) -> ThemeValidationResult:
    if isinstance(theme, ThemeDocument):
        return validate_theme_document(theme)
    path = _resolve_theme_path(theme)
    document = _load_theme_path(path)
    return validate_theme_document(document, theme_dir=path.parent)


def validate_theme_document(
    theme: ThemeDocument,
    *,
    theme_dir: Path | None = None,
) -> ThemeValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    _validate_no_forbidden_fields(theme.to_dict(), errors, path="$")
    _validate_tokens(theme.tokens, errors)
    _validate_assets(theme.assets, errors, warnings, theme_dir=theme_dir)
    _validate_component_variants(theme.component_variants, errors)
    resolution = resolve_theme_tokens(theme)
    errors.extend(resolution.errors)
    warnings.extend(resolution.warnings)
    return ThemeValidationResult(
        theme_id=theme.id,
        valid=not errors,
        errors=tuple(dict.fromkeys(errors)),
        warnings=tuple(dict.fromkeys(warnings)),
        token_count=len(theme.tokens),
        asset_count=len(theme.assets),
    )


def resolve_theme_tokens(
    theme: ThemeDocument,
    *,
    canvas_overrides: Mapping[str, Any] | None = None,
    component_overrides: Mapping[str, Any] | None = None,
    runtime_state_overrides: Mapping[str, Any] | None = None,
    app_defaults: Mapping[str, Any] | None = None,
) -> ThemeResolution:
    errors: list[str] = []
    warnings: list[str] = []
    merged: dict[str, Any] = dict(app_defaults or APP_DEFAULT_TOKENS)
    touched_names: set[str] = set()
    for label, values in (
        ("theme", theme.tokens),
        ("canvas", canvas_overrides or {}),
        ("component", component_overrides or {}),
        ("runtime_state", runtime_state_overrides or {}),
    ):
        touched_names.update(str(name) for name in dict(values))
        local_errors: list[str] = []
        _validate_tokens(dict(values), local_errors)
        errors.extend(f"{label}: {error}" for error in local_errors)
        merged.update(dict(values))

    resolved: dict[str, Any] = {}
    for name in sorted(merged):
        _resolve_token(name, merged, resolved, [], errors)
    for name in sorted(touched_names):
        if name in resolved:
            _validate_token_value(name, resolved[name], errors, allow_reference=False)
    return ThemeResolution(tokens=resolved, errors=tuple(dict.fromkeys(errors)), warnings=tuple(warnings))


def _resolve_token(
    name: str,
    source: Mapping[str, Any],
    resolved: dict[str, Any],
    stack: list[str],
    errors: list[str],
) -> Any:
    if name in resolved:
        return resolved[name]
    if name in stack:
        cycle = " -> ".join([*stack, name])
        errors.append(f"recursive token reference: {cycle}")
        return source.get(name)
    if name not in source:
        errors.append(f"missing token reference: {name}")
        return None
    value = source[name]
    reference = _token_reference(value)
    if reference is None:
        resolved[name] = value
        return value
    if reference not in source:
        errors.append(f"{name}: missing token reference: {reference}")
        resolved[name] = value
        return value
    resolved[name] = _resolve_token(reference, source, resolved, [*stack, name], errors)
    return resolved[name]


def _validate_tokens(tokens: dict[str, Any], errors: list[str]) -> None:
    if not isinstance(tokens, dict):
        errors.append("tokens must be a mapping")
        return
    for name, value in tokens.items():
        text = str(name).strip()
        if not TOKEN_NAME_PATTERN.fullmatch(text):
            errors.append(f"{text}: invalid token name")
            continue
        namespace = text.split(".", 1)[0]
        if namespace not in TOKEN_NAMESPACES:
            errors.append(f"{text}: unsupported token namespace")
            continue
        _validate_token_value(text, value, errors, allow_reference=True)


def _validate_token_value(name: str, value: Any, errors: list[str], *, allow_reference: bool) -> None:
    namespace = name.split(".", 1)[0]
    if allow_reference and _token_reference(value) is not None:
        return
    _validate_no_remote_or_code_text(value, errors, path=name)
    if namespace == "color":
        if not isinstance(value, str) or not HEX_COLOR_PATTERN.fullmatch(value.strip()):
            errors.append(f"{name}: color tokens must be #RGB or #RRGGBB")
    elif namespace in {"radius", "spacing"}:
        _validate_number(value, errors, path=name, minimum=0, maximum=512)
    elif namespace == "motion":
        _validate_number(value, errors, path=name, minimum=0, maximum=10000)
    elif namespace == "opacity":
        _validate_number(value, errors, path=name, minimum=0, maximum=1)
    elif namespace == "font":
        if not isinstance(value, (str, int, float)):
            errors.append(f"{name}: font tokens must be strings or numbers")
    elif namespace in {"shadow", "material"} and not isinstance(value, str):
        errors.append(f"{name}: {namespace} tokens must be strings")


def _validate_number(value: Any, errors: list[str], *, path: str, minimum: float, maximum: float) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        errors.append(f"{path}: token must be numeric")
        return
    number = float(value)
    if number < minimum or number > maximum:
        errors.append(f"{path}: token must be between {minimum:g} and {maximum:g}")


def _validate_assets(
    assets: dict[str, str],
    errors: list[str],
    warnings: list[str],
    *,
    theme_dir: Path | None,
) -> None:
    if not isinstance(assets, dict):
        errors.append("assets must be a mapping")
        return
    for name, raw_path in assets.items():
        try:
            _validate_asset_name(str(name))
        except ValueError as exc:
            errors.append(f"{name}: {exc}")
            continue
        if not isinstance(raw_path, str) or not raw_path.strip():
            errors.append(f"{name}: asset path must be a nonblank string")
            continue
        if _has_remote_url(raw_path):
            errors.append(f"{name}: remote asset URLs are not allowed")
            continue
        path = PurePosixPath(raw_path.replace("\\", "/"))
        if path.is_absolute() or any(part in {"", ".", ".."} or ":" in part for part in path.parts):
            errors.append(f"{name}: asset path must stay inside the theme pack")
            continue
        if path.suffix.casefold() not in VISUAL_ASSET_SUFFIXES:
            errors.append(f"{name}: theme assets must be raster image files")
            continue
        if theme_dir is not None and not (theme_dir / Path(*path.parts)).is_file():
            warnings.append(f"{name}: asset file is missing: {raw_path}")


def _validate_asset_name(name: str) -> str:
    text = name.strip().replace("\\", "/")
    if not text:
        raise ValueError("asset name must not be blank")
    path = PurePosixPath(text)
    if path.is_absolute() or any(part in {"", ".", ".."} or ":" in part for part in path.parts):
        raise ValueError("asset name must stay inside the theme pack")
    if path.suffix.casefold() and path.suffix.casefold() not in VISUAL_ASSET_SUFFIXES:
        raise ValueError("asset name must be a raster image asset")
    return text


def _validate_component_variants(variants: dict[str, dict[str, Any]], errors: list[str]) -> None:
    if not isinstance(variants, dict):
        errors.append("component_variants must be a mapping")
        return
    for component_type, rows in variants.items():
        if not isinstance(rows, dict):
            errors.append(f"{component_type}: component variant config must be a mapping")
            continue
        _validate_no_forbidden_fields(rows, errors, path=f"component_variants.{component_type}")
        for variant_id, value in rows.items():
            if not re.fullmatch(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$", str(variant_id)):
                errors.append(f"{component_type}.{variant_id}: invalid component variant id")
            _validate_no_remote_or_code_text(value, errors, path=f"component_variants.{component_type}.{variant_id}")


def _validate_no_forbidden_fields(value: Any, errors: list[str], *, path: str) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).strip().casefold().replace("-", "_")
            if normalized in FORBIDDEN_KEYS:
                errors.append(f"{path}.{key}: executable or behavior fields are not allowed in themes")
            _validate_no_forbidden_fields(item, errors, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _validate_no_forbidden_fields(item, errors, path=f"{path}[{index}]")
    else:
        _validate_no_remote_or_code_text(value, errors, path=path)


def _validate_no_remote_or_code_text(value: Any, errors: list[str], *, path: str) -> None:
    if not isinstance(value, str):
        return
    text = value.strip().casefold()
    if _has_remote_url(value):
        errors.append(f"{path}: remote URLs are not allowed in themes")
    if any(marker in text for marker in FORBIDDEN_TEXT_MARKERS):
        errors.append(f"{path}: script-like text is not allowed in themes")


def _has_remote_url(value: str) -> bool:
    text = value.strip().casefold()
    return "://" in text or text.startswith("//") or text.startswith("data:")


def _token_reference(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    match = TOKEN_REFERENCE_PATTERN.fullmatch(value.strip())
    if not match:
        return None
    return match.group(1).strip()


def _resolve_theme_path(id_or_path: str | Path) -> Path:
    candidate = Path(str(id_or_path)).expanduser()
    if candidate.exists():
        return candidate / "theme.yaml" if candidate.is_dir() else candidate
    text = str(id_or_path).strip()
    if not text:
        raise RitualistError("theme id or path must not be blank")
    for reference in list_themes(include_bundled=True):
        if reference.theme_id == text or reference.path.parent.name == text or reference.path.stem == text:
            return reference.path
    raise RitualistError(f"theme not found: {text}")


def _load_theme_path(path: Path) -> ThemeDocument:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RitualistError(f"could not read theme {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise RitualistError(f"theme must be a mapping: {path}")
    try:
        return ThemeDocument.model_validate(raw)
    except ValidationError as exc:
        raise RitualistError(f"invalid theme {path}: {exc}") from exc


def _reference_for_path(path: Path, *, source: str) -> ThemeReference:
    try:
        document = _load_theme_path(path)
        return ThemeReference(document.id, document.name, path, source)
    except RitualistError:
        return ThemeReference(path.parent.name or path.stem, path.parent.name or path.stem, path, source)


def _bundled_theme_paths() -> list[Path]:
    root = Path(__file__).resolve().parent.parent / "themes"
    if not root.exists():
        return []
    paths = sorted(root.glob("*/theme.yaml"))
    paths.extend(sorted(root.glob("*.yaml")))
    return paths
