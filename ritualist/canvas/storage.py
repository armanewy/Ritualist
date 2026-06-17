from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from ritualist.errors import RitualistError
from ritualist.paths import canvases_dir, canvases_path
from ritualist.recipe_loader import discover_recipes
from ritualist.target_resolution import builtin_target_catalog

from .models import (
    CANVAS_SCHEMA_VERSION,
    CanvasBindingKind,
    CanvasComponent,
    CanvasComponentBinding,
    CanvasDocument,
)
from .registry import create_component_registry, validate_canvas_document


@dataclass(frozen=True)
class CanvasReference:
    canvas_id: str
    name: str
    path: Path
    source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.canvas_id,
            "name": self.name,
            "path": str(self.path),
            "source": self.source,
        }


@dataclass(frozen=True)
class CanvasWriteResult:
    canvas_id: str
    path: Path
    changed: bool
    message: str

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.canvas_id,
            "path": str(self.path),
            "changed": self.changed,
            "message": self.message,
        }


def list_canvases(*, include_bundled: bool = True) -> list[CanvasReference]:
    rows: dict[str, CanvasReference] = {}
    if include_bundled:
        for path in _bundled_canvas_paths():
            reference = _reference_for_path(path, source="bundled")
            if reference is not None:
                rows[reference.canvas_id] = reference
    for path in sorted(canvases_path().glob("*.yaml")):
        reference = _reference_for_path(path, source="user")
        if reference is not None:
            rows[reference.canvas_id] = reference
    return sorted(rows.values(), key=lambda row: (row.source != "user", row.canvas_id))


def load_canvas(id_or_path: str | Path) -> CanvasDocument:
    path = _resolve_canvas_path(id_or_path)
    return _load_canvas_path(path)


def load_bundled_canvas(canvas_id: str) -> CanvasDocument:
    text = canvas_id.strip()
    if not text:
        raise RitualistError("bundled canvas id must not be blank")
    for bundled in _bundled_canvas_paths():
        if bundled.stem == text:
            return _load_canvas_path(bundled)
    raise RitualistError(f"bundled canvas not found: {text}")


def save_canvas(document: CanvasDocument, path: Path | None = None, *, overwrite: bool = True) -> CanvasWriteResult:
    destination = path or (canvases_dir() / f"{document.id}.yaml")
    if destination.exists() and not overwrite:
        return CanvasWriteResult(
            document.id,
            destination,
            False,
            "exists; not overwritten",
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(_dump_canvas(document), encoding="utf-8")
    return CanvasWriteResult(document.id, destination, True, "written")


def validate_canvas(
    canvas: CanvasDocument | str | Path,
    *,
    strict: bool = False,
    imported: bool = False,
    check_bindings: bool = True,
):
    if isinstance(canvas, CanvasDocument):
        document = canvas
        canvas_dir = None
    else:
        path = _resolve_canvas_path(canvas)
        document = _load_canvas_path(path)
        canvas_dir = path.parent
    return validate_canvas_document(
        document,
        strict=strict,
        imported=imported,
        canvas_dir=canvas_dir,
        check_bindings=check_bindings,
    )


def create_default_canvases(*, overwrite: bool = False) -> list[CanvasWriteResult]:
    results: list[CanvasWriteResult] = []
    destination_dir = canvases_dir()
    for bundled in _bundled_canvas_paths():
        document = _load_canvas_path(bundled)
        destination = destination_dir / f"{document.id}.yaml"
        if destination.exists() and not overwrite:
            results.append(
                CanvasWriteResult(document.id, destination, False, "already exists")
            )
            continue
        destination.write_text(bundled.read_text(encoding="utf-8"), encoding="utf-8")
        results.append(CanvasWriteResult(document.id, destination, True, "created"))
    return results


def create_default_canvas_from_recipes() -> CanvasDocument:
    components: list[CanvasComponent] = []
    x = 80
    y = 120
    for index, (_path, recipe, _error) in enumerate(discover_recipes()):
        recipe_id = recipe.id if recipe is not None else f"recipe_{index + 1}"
        title = recipe.name if recipe is not None else recipe_id
        components.append(
            CanvasComponent(
                id=f"recipe_{recipe_id}",
                type="ritual.card",
                x=x,
                y=y + index * 260,
                width=420,
                height=220,
                z=10 + index,
                props={"title": title, "recipe_id": recipe_id},
                binding=CanvasComponentBinding(kind=CanvasBindingKind.RECIPE, recipe_id=recipe_id),
            )
        )
    if not components:
        components.append(
            CanvasComponent(
                id="getting_started",
                type="text.label",
                x=80,
                y=120,
                width=420,
                height=72,
                z=1,
                props={"text": "Run ritualist init to install recipes."},
            )
        )
    return CanvasDocument(
        id="recipes_canvas",
        name="Recipes Canvas",
        description="Generated local recipe canvas.",
        components=tuple(components),
    )


def create_default_canvas_from_targets() -> CanvasDocument:
    components = []
    for index, target in enumerate(builtin_target_catalog().targets):
        components.append(
            CanvasComponent(
                id=f"target_{target.id}",
                type="target.card",
                x=80 + (index % 2) * 400,
                y=120 + (index // 2) * 260,
                width=360,
                height=220,
                z=10 + index,
                props={"title": target.display_name, "target": target.id},
                binding=CanvasComponentBinding(kind=CanvasBindingKind.TARGET_START, target=target.id),
            )
        )
    return CanvasDocument(
        id="targets_canvas",
        name="Targets Canvas",
        description="Generated local target preview canvas.",
        components=tuple(components),
    )


def create_mock_canvas(component_count: int = 100) -> CanvasDocument:
    registry = create_component_registry()
    types = registry.all()
    components: list[CanvasComponent] = []
    for index in range(max(1, component_count)):
        spec = types[index % len(types)]
        components.append(
            CanvasComponent(
                id=f"mock_{index + 1:03d}",
                type=spec.type_id,
                x=float(32 + (index % 8) * 180),
                y=float(32 + (index // 8) * 120),
                width=spec.default_width,
                height=spec.default_height,
                z=index % 100,
                props=_mock_props(spec.type_id),
                binding=_mock_binding(spec.type_id),
            )
        )
    return CanvasDocument(
        id=f"mock_canvas_{component_count}",
        name=f"Mock Canvas {component_count}",
        description="Generated Canvas model for performance smoke.",
        components=tuple(components),
    )


def bundled_canvas_ids() -> tuple[str, ...]:
    return tuple(reference.canvas_id for reference in list_canvases(include_bundled=True) if reference.source == "bundled")


def _mock_props(type_id: str) -> dict[str, object]:
    if type_id in {"ritual.card", "target.card", "app.launcher", "window.layout_button"}:
        return {"title": f"Mock {type_id}", "subtitle": "Generated component"}
    if type_id == "text.label":
        return {"text": "Mock label"}
    if type_id == "image":
        return {"path": "assets/mock.png", "alt": "Mock image"}
    if type_id == "recent.activity":
        return {"title": "Recent activity", "limit": 8}
    if type_id == "clock":
        return {"format": "short"}
    if type_id == "category.dock":
        return {"categories": ["Gaming", "Coding", "Media"]}
    return {}


def _mock_binding(type_id: str) -> CanvasComponentBinding | None:
    if type_id in {"ritual.card", "ritual.status", "ritual.controller", "doctor.badge"}:
        return CanvasComponentBinding(kind=CanvasBindingKind.RECIPE, recipe_id="gaming_mode")
    if type_id in {"target.card", "target.status"}:
        return CanvasComponentBinding(kind=CanvasBindingKind.TARGET_START, target="diablo_iv")
    if type_id == "recent.activity":
        return CanvasComponentBinding(kind=CanvasBindingKind.RECENT_RUNS, id="local")
    if type_id == "app.launcher":
        return CanvasComponentBinding(kind=CanvasBindingKind.APP_LAUNCHER, id="local_app")
    if type_id == "window.layout_button":
        return CanvasComponentBinding(kind=CanvasBindingKind.WINDOW_LAYOUT, id="layout_preview")
    return None


def _resolve_canvas_path(id_or_path: str | Path) -> Path:
    candidate = Path(str(id_or_path)).expanduser()
    if candidate.exists():
        return candidate
    text = str(id_or_path).strip()
    if not text:
        raise RitualistError("canvas id or path must not be blank")
    user_path = canvases_path() / f"{text}.yaml"
    if user_path.exists():
        return user_path
    for bundled in _bundled_canvas_paths():
        if bundled.stem == text:
            return bundled
    raise RitualistError(f"canvas not found: {text}")


def _load_canvas_path(path: Path) -> CanvasDocument:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RitualistError(f"could not read canvas {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise RitualistError(f"canvas must be a mapping: {path}")
    try:
        return CanvasDocument.model_validate(raw)
    except ValidationError as exc:
        raise RitualistError(f"invalid canvas {path}: {exc}") from exc


def _reference_for_path(path: Path, *, source: str) -> CanvasReference | None:
    try:
        document = _load_canvas_path(path)
    except RitualistError:
        return CanvasReference(path.stem, path.stem, path, source)
    return CanvasReference(document.id, document.name, path, source)


def _dump_canvas(document: CanvasDocument) -> str:
    return yaml.safe_dump(
        document.to_dict(),
        sort_keys=False,
        allow_unicode=False,
    )


def _bundled_canvas_paths() -> list[Path]:
    try:
        root = resources.files("ritualist.sample_canvases")
    except ModuleNotFoundError:
        return []
    return sorted(Path(str(path)) for path in root.iterdir() if path.name.endswith(".yaml"))


def canvas_show_payload(document: CanvasDocument, *, strict: bool = False) -> dict[str, Any]:
    validation = validate_canvas_document(document, strict=strict)
    return {
        "schema_version": "ritualist.canvas.show.v1",
        "canvas": document.to_dict(),
        "validation": validation.to_dict(),
    }


def default_canvas_document() -> CanvasDocument:
    try:
        return _load_canvas_path(next(path for path in _bundled_canvas_paths() if path.stem == "gaming_desktop"))
    except StopIteration as exc:
        raise RitualistError("bundled gaming_desktop canvas is missing") from exc
