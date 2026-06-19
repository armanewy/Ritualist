from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from importlib.resources import as_file, files
from pathlib import Path
from typing import Any, Iterator

BRAND_PACKAGE = "setpiece.assets.brand"

APP_ICON = "app/setpiece_app_icon.ico"
DESIGN_TOKENS = "setpiece_design_tokens.json"

TRAY_STATES = frozenset(
    {
        "ready",
        "running",
        "waiting",
        "confirmation",
        "failure",
        "recovery",
        "paused",
        "stopped",
    }
)
TRAY_VARIANTS = frozenset({"light", "dark", "monochrome_black", "monochrome_white"})


@dataclass(frozen=True, slots=True)
class TrayIconAsset:
    state: str
    variant: str
    relative_path: str


def load_design_tokens() -> dict[str, Any]:
    with brand_asset_path(DESIGN_TOKENS) as path:
        return json.loads(path.read_text(encoding="utf-8"))


@contextmanager
def brand_asset_path(relative_path: str) -> Iterator[Path]:
    normalized = _normalize_relative_path(relative_path)
    resource = files(BRAND_PACKAGE).joinpath(normalized)
    if not resource.is_file():
        raise FileNotFoundError(f"Setpiece brand asset is missing: {normalized}")
    with as_file(resource) as path:
        yield path


def tray_icon_asset(state: str, *, variant: str = "light") -> TrayIconAsset:
    normalized_state = _normalize_choice(state, TRAY_STATES, "tray state")
    normalized_variant = _normalize_choice(variant, TRAY_VARIANTS, "tray variant")
    relative = (
        f"tray/{normalized_variant}/{normalized_state}/"
        f"setpiece_tray_{normalized_state}.ico"
    )
    return TrayIconAsset(
        state=normalized_state,
        variant=normalized_variant,
        relative_path=relative,
    )


def qt_icon_from_brand_asset(q_icon_type: Any, relative_path: str) -> Any:
    with brand_asset_path(relative_path) as path:
        return q_icon_type(str(path))


def qt_app_icon(q_icon_type: Any) -> Any:
    return qt_icon_from_brand_asset(q_icon_type, APP_ICON)


def apply_qt_application_icon(app: Any, q_icon_type: Any) -> Any:
    icon = qt_app_icon(q_icon_type)
    setter = getattr(app, "setWindowIcon", None)
    if callable(setter):
        setter(icon)
    return icon


def select_tray_variant(app: Any | None = None, *, high_contrast: bool = False) -> str:
    if high_contrast or os.environ.get("SETPIECE_HIGH_CONTRAST") == "1":
        return "monochrome_white"

    scheme_name = ""
    try:
        style_hints = app.styleHints() if app is not None and hasattr(app, "styleHints") else None
        color_scheme = style_hints.colorScheme() if style_hints is not None else None
        scheme_name = str(getattr(color_scheme, "name", color_scheme) or "").lower()
    except Exception:  # noqa: BLE001 - theme detection must not block Agent startup.
        scheme_name = ""

    if "dark" in scheme_name:
        return "dark"
    if "light" in scheme_name:
        return "light"
    return "light"


def _normalize_relative_path(value: str) -> str:
    text = str(value or "").strip().replace("\\", "/")
    if not text or text.startswith("/") or ":" in text:
        raise ValueError("brand asset paths must be package-relative")
    parts = Path(text).parts
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("brand asset paths must not traverse directories")
    return text


def _normalize_choice(value: str, allowed: frozenset[str], label: str) -> str:
    text = str(value or "").strip().lower()
    if text not in allowed:
        raise ValueError(f"unsupported Setpiece {label}: {value}")
    return text
