from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ritualist import themes
from ritualist.errors import RitualistError

from .models import CanvasDocument, CanvasThemeTokens

CANVAS_THEME_BRIDGE_SCHEMA_VERSION = "ritualist.canvas.theme_bridge.v1"
DEFAULT_CANVAS_THEME_IDS = {"", "default", "ritualist_default"}

_DOTTED_TO_QML_TOKEN = {
    "color.background": "background",
    "color.text": "foreground",
    "color.text_muted": "muted",
    "color.surface": "panel",
    "color.surface_alt": "panel_alt",
    "color.success_panel": "success_panel",
    "color.warning_panel": "warning_panel",
    "color.danger_panel": "danger_panel",
    "color.focus_panel": "focus_panel",
    "color.border": "border",
    "color.focus_ring": "focus_ring",
    "color.accent": "accent",
    "color.success": "success",
    "color.warning": "warning",
    "color.danger": "danger",
    "font.family": "font_family",
    "font.size_body": "font_size_body",
    "font.size_title": "font_size_title",
    "radius.sm": "radius_sm",
    "radius.md": "radius_md",
    "radius.lg": "radius_lg",
    "spacing.sm": "spacing_sm",
    "spacing.md": "spacing_md",
    "spacing.lg": "spacing_lg",
    "shadow.card": "shadow",
    "motion.fast_ms": "motion_fast_ms",
    "motion.normal_ms": "motion_normal_ms",
}

_QML_TO_DOTTED_TOKEN = {value: key for key, value in _DOTTED_TO_QML_TOKEN.items()}


@dataclass(frozen=True)
class CanvasThemeSelection:
    theme_id: str
    name: str
    source: str
    valid: bool
    tokens: dict[str, Any]
    resolved_tokens: dict[str, Any]
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    validation: dict[str, Any] = field(default_factory=dict)
    schema_version: str = CANVAS_THEME_BRIDGE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        validation = dict(self.validation)
        validation.setdefault("theme_id", self.theme_id)
        validation.setdefault("valid", self.valid)
        validation.setdefault("errors", list(self.errors))
        validation.setdefault("warnings", list(self.warnings))
        return {
            "schema_version": self.schema_version,
            "id": self.theme_id,
            "name": self.name,
            "source": self.source,
            "valid": self.valid,
            "tokens": self.tokens,
            "resolved_tokens": self.resolved_tokens,
            "validation": validation,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


def resolve_canvas_theme(
    document: CanvasDocument,
    *,
    fail_on_invalid: bool = True,
) -> CanvasThemeSelection:
    """Resolve the Canvas-selected theme into the existing QML token contract."""
    selection = _select_canvas_theme(document)
    if fail_on_invalid and not selection.valid:
        details = "; ".join(selection.errors) or "unknown theme validation error"
        raise RitualistError(f"canvas theme '{selection.theme_id}' is invalid: {details}")
    return selection


def validate_canvas_theme_selection(document: CanvasDocument) -> CanvasThemeSelection:
    return resolve_canvas_theme(document, fail_on_invalid=False)


def _select_canvas_theme(document: CanvasDocument) -> CanvasThemeSelection:
    theme_id = str(document.theme.id or "").strip()
    if theme_id in DEFAULT_CANVAS_THEME_IDS:
        return _embedded_canvas_theme(document)

    try:
        theme = themes.load_theme(theme_id)
        validation = themes.validate_theme(theme_id)
    except RitualistError as exc:
        if "." not in theme_id and not _theme_reference_exists(theme_id):
            return _embedded_canvas_theme(
                document,
                source="embedded_legacy",
                warnings=(f"theme '{theme_id}' was not found; using embedded Canvas tokens",),
            )
        return CanvasThemeSelection(
            theme_id=theme_id,
            name=document.theme.name,
            source="missing",
            valid=False,
            tokens=_default_qml_tokens(),
            resolved_tokens=dict(themes.APP_DEFAULT_TOKENS),
            errors=(str(exc),),
            validation={
                "theme_id": theme_id,
                "valid": False,
                "errors": [str(exc)],
                "warnings": [],
            },
        )

    resolution = themes.resolve_theme_tokens(theme)
    errors = tuple(dict.fromkeys([*validation.errors, *resolution.errors]))
    warnings = tuple(dict.fromkeys([*validation.warnings, *resolution.warnings]))
    valid = not errors
    return CanvasThemeSelection(
        theme_id=theme.id,
        name=theme.name,
        source=_source_for_theme(theme.id),
        valid=valid,
        tokens=_qml_tokens_from_dotted(resolution.tokens),
        resolved_tokens=resolution.tokens,
        errors=errors,
        warnings=warnings,
        validation=validation.to_dict(),
    )


def _embedded_canvas_theme(
    document: CanvasDocument,
    *,
    source: str = "embedded",
    warnings: tuple[str, ...] = (),
) -> CanvasThemeSelection:
    qml_tokens = dict(document.theme.tokens.model_dump(mode="json"))
    resolved_tokens = _dotted_from_qml_tokens(qml_tokens)
    accessibility = themes.theme_accessibility_report(resolved_tokens)
    combined_warnings = tuple(dict.fromkeys([*warnings, *accessibility.get("warnings", ())]))
    return CanvasThemeSelection(
        theme_id=document.theme.id,
        name=document.theme.name,
        source=source,
        valid=True,
        tokens=qml_tokens,
        resolved_tokens=resolved_tokens,
        warnings=combined_warnings,
        validation={
            "theme_id": document.theme.id,
            "valid": True,
            "errors": [],
            "warnings": list(combined_warnings),
            "accessibility": accessibility,
            "token_count": len(qml_tokens),
            "asset_count": 0,
        },
    )


def _qml_tokens_from_dotted(resolved_tokens: Mapping[str, Any]) -> dict[str, Any]:
    qml_tokens = _default_qml_tokens()
    for dotted_name, qml_name in _DOTTED_TO_QML_TOKEN.items():
        if dotted_name in resolved_tokens:
            qml_tokens[qml_name] = resolved_tokens[dotted_name]
    return qml_tokens


def _dotted_from_qml_tokens(qml_tokens: Mapping[str, Any]) -> dict[str, Any]:
    dotted = dict(themes.APP_DEFAULT_TOKENS)
    for qml_name, dotted_name in _QML_TO_DOTTED_TOKEN.items():
        if qml_name in qml_tokens:
            dotted[dotted_name] = qml_tokens[qml_name]
    return dotted


def _default_qml_tokens() -> dict[str, Any]:
    return CanvasThemeTokens().model_dump(mode="json")


def _source_for_theme(theme_id: str) -> str:
    for reference in themes.list_themes(include_bundled=True):
        if reference.theme_id == theme_id:
            return reference.source
    return "theme"


def _theme_reference_exists(theme_id: str) -> bool:
    for reference in themes.list_themes(include_bundled=True):
        if reference.theme_id == theme_id or reference.path.parent.name == theme_id or reference.path.stem == theme_id:
            return True
    return False
