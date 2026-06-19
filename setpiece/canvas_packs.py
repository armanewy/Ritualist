from __future__ import annotations

import json
import hashlib
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

import yaml
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError, field_validator

from . import __version__
from .canvas.models import CanvasComponentProps, CanvasDocument, CanvasTheme
from .canvas.registry import validate_canvas_structure
from .canvas.storage import list_canvases, load_canvas
from .errors import SetpieceError
from .models import SAFE_ID_PATTERN
from .paths import imported_canvas_packs_dir, imported_theme_packs_dir, themes_path

CANVAS_PACK_SCHEMA = "setpiece.canvas_pack.v1"
THEME_PACK_SCHEMA = "setpiece.theme_pack.v1"
LEGACY_CANVAS_PACK_SCHEMA = "ritualist.canvas_pack.v1"
LEGACY_THEME_PACK_SCHEMA = "ritualist.theme_pack.v1"
CANVAS_PACK_SCHEMAS = frozenset({CANVAS_PACK_SCHEMA, LEGACY_CANVAS_PACK_SCHEMA})
THEME_PACK_SCHEMAS = frozenset({THEME_PACK_SCHEMA, LEGACY_THEME_PACK_SCHEMA})
CANVAS_PACK_EXTENSION = ".setpiececanvas"
THEME_PACK_EXTENSION = ".setpiecetheme"
SUITE_PACK_EXTENSION = ".setpiecesuite"
LEGACY_CANVAS_PACK_EXTENSION = ".ritualistcanvas"
LEGACY_THEME_PACK_EXTENSION = ".ritualisttheme"
LEGACY_SUITE_PACK_EXTENSION = ".ritualistsuite"
CANVAS_PACK_EXTENSIONS = frozenset({CANVAS_PACK_EXTENSION, LEGACY_CANVAS_PACK_EXTENSION})
THEME_PACK_EXTENSIONS = frozenset({THEME_PACK_EXTENSION, LEGACY_THEME_PACK_EXTENSION})

MANIFEST_NAME = "manifest.yaml"
CANVAS_NAME = "canvas.yaml"
THEME_NAME = "theme.yaml"
README_NAME = "README.md"
ASSETS_PREFIX = "assets/"
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
_ALLOWED_VISUAL_ASSET_SUFFIXES = {
    ".avif",
    ".bmp",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".png",
    ".webp",
}
_CANVAS_ASSET_PROP_NAMES = {"image", "path", "source"}
_SUSPICIOUS_ASSET_TEXT_MARKERS = (
    "<!doctype",
    "<html",
    "<script",
    "javascript:",
    "vbscript:",
    "#!/bin/",
    "#!/usr/bin/",
    "powershell",
)


class VisualPackError(SetpieceError):
    """Raised when a local visual pack is invalid."""


class CanvasPackSafety(BaseModel):
    model_config = ConfigDict(extra="forbid")

    visual_only: bool = True
    no_arbitrary_code: bool = True
    no_auto_run: bool = True
    no_remote_execution: bool = True
    imported_canvases_do_not_run_automatically: bool = True

    @field_validator(
        "visual_only",
        "no_arbitrary_code",
        "no_auto_run",
        "no_remote_execution",
        "imported_canvases_do_not_run_automatically",
    )
    @classmethod
    def require_true(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("canvas pack safety declarations must be true")
        return value


class ThemePackSafety(BaseModel):
    model_config = ConfigDict(extra="forbid")

    visual_only: bool = True
    no_actions: bool = True
    no_recipes: bool = True
    no_arbitrary_code: bool = True
    no_remote_execution: bool = True

    @field_validator("visual_only", "no_actions", "no_recipes", "no_arbitrary_code", "no_remote_execution")
    @classmethod
    def require_true(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("theme pack safety declarations must be true")
        return value


class CanvasPackManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_: str = Field(alias="schema")
    pack_type: str = "canvas"
    id: str
    name: str
    version: str = "0.1"
    description: str = ""
    required_setpiece_version: str = Field(
        default=__version__,
        validation_alias=AliasChoices(
            "required_setpiece_version",
            "required_ritualist_version",
        ),
    )
    canvas_id: str
    assets: list[str] = Field(default_factory=list)
    safety: CanvasPackSafety = Field(default_factory=CanvasPackSafety)

    @property
    def schema(self) -> str:
        return self.schema_

    @field_validator("schema_")
    @classmethod
    def validate_schema(cls, value: str) -> str:
        if value not in CANVAS_PACK_SCHEMAS:
            raise ValueError(f"unsupported canvas pack schema '{value}'")
        return value

    @field_validator("id", "canvas_id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not SAFE_ID_PATTERN.fullmatch(value):
            raise ValueError("canvas pack ids must be safe filename-like identifiers")
        return value

    @field_validator("pack_type")
    @classmethod
    def validate_pack_type(cls, value: str) -> str:
        if value != "canvas":
            raise ValueError("canvas pack manifest must have pack_type: canvas")
        return value

    @field_validator("name", "version")
    @classmethod
    def validate_required_string(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("field must be non-empty")
        return text

    @field_validator("assets")
    @classmethod
    def validate_assets(cls, value: list[str]) -> list[str]:
        return _validate_manifest_assets(value)


class ThemePackManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_: str = Field(alias="schema")
    pack_type: str = "theme"
    id: str
    name: str
    version: str = "0.1"
    description: str = ""
    required_setpiece_version: str = Field(
        default=__version__,
        validation_alias=AliasChoices(
            "required_setpiece_version",
            "required_ritualist_version",
        ),
    )
    theme_id: str
    assets: list[str] = Field(default_factory=list)
    safety: ThemePackSafety = Field(default_factory=ThemePackSafety)

    @property
    def schema(self) -> str:
        return self.schema_

    @field_validator("schema_")
    @classmethod
    def validate_schema(cls, value: str) -> str:
        if value not in THEME_PACK_SCHEMAS:
            raise ValueError(f"unsupported theme pack schema '{value}'")
        return value

    @field_validator("id", "theme_id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not SAFE_ID_PATTERN.fullmatch(value):
            raise ValueError("theme pack ids must be safe filename-like identifiers")
        return value

    @field_validator("pack_type")
    @classmethod
    def validate_pack_type(cls, value: str) -> str:
        if value != "theme":
            raise ValueError("theme pack manifest must have pack_type: theme")
        return value

    @field_validator("name", "version")
    @classmethod
    def validate_required_string(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("field must be non-empty")
        return text

    @field_validator("assets")
    @classmethod
    def validate_assets(cls, value: list[str]) -> list[str]:
        return _validate_manifest_assets(value)


@dataclass(frozen=True)
class VisualPackResult:
    output_path: Path
    pack_id: str
    pack_type: str
    entries: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_path": str(self.output_path),
            "pack_id": self.pack_id,
            "pack_type": self.pack_type,
            "entries": list(self.entries),
        }


@dataclass(frozen=True)
class ImportedVisualPackRecord:
    import_id: str
    pack_id: str
    pack_type: str
    name: str
    version: str
    status: str
    root: Path
    imported_at: str
    document_path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "setpiece.visual_pack_import.v1",
            "import_id": self.import_id,
            "pack_id": self.pack_id,
            "pack_type": self.pack_type,
            "name": self.name,
            "version": self.version,
            "status": self.status,
            "root": str(self.root),
            "imported_at": self.imported_at,
            "document_path": self.document_path,
        }


def export_canvas_pack(canvas: str | Path, out: Path, *, readme_path: Path | None = None) -> VisualPackResult:
    document = load_canvas(canvas)
    document, assets = _prepare_canvas_for_export(document, _canvas_source_dir(canvas))
    validation = validate_canvas_structure(document, imported=True, strict=False)
    if not validation.valid:
        raise VisualPackError(f"canvas cannot be exported as a safe canvas pack: {validation.errors}")
    _require_exact_canvas_assets(document, assets)

    manifest = CanvasPackManifest(
        schema=CANVAS_PACK_SCHEMA,
        id=document.id,
        name=document.name,
        version=document.metadata.version,
        description=document.description,
        canvas_id=document.id,
        assets=sorted(assets),
    )
    entries = {
        MANIFEST_NAME: _dump_yaml(manifest.model_dump(mode="json", by_alias=True)),
        CANVAS_NAME: _dump_yaml(document.to_dict()),
    }
    entries.update(assets)
    if readme_path is not None:
        entries[README_NAME] = readme_path.read_text(encoding="utf-8")
    return _write_pack(out, CANVAS_PACK_EXTENSION, manifest.id, "canvas", entries)


def export_theme_pack(theme: str | Path, out: Path, *, readme_path: Path | None = None) -> VisualPackResult:
    document = _load_theme(theme)
    manifest = ThemePackManifest(
        schema=THEME_PACK_SCHEMA,
        id=document.id,
        name=document.name,
        theme_id=document.id,
    )
    entries = {
        MANIFEST_NAME: _dump_yaml(manifest.model_dump(mode="json", by_alias=True)),
        THEME_NAME: _dump_yaml(document.model_dump(mode="json")),
    }
    if readme_path is not None:
        entries[README_NAME] = readme_path.read_text(encoding="utf-8")
    return _write_pack(out, THEME_PACK_EXTENSION, manifest.id, "theme", entries)


def import_canvas_pack(pack: str | Path) -> ImportedVisualPackRecord:
    path = Path(pack).expanduser()
    manifest, document, assets = _read_canvas_pack(path)
    root = imported_canvas_packs_dir() / manifest.id
    _replace_dir(root)
    shutil.copy2(path, root / path.name)
    (root / CANVAS_NAME).write_text(_dump_yaml(document.to_dict()), encoding="utf-8")
    _copy_assets(root, assets)
    record = ImportedVisualPackRecord(
        import_id=manifest.id,
        pack_id=manifest.id,
        pack_type="canvas",
        name=manifest.name,
        version=manifest.version,
        status="quarantined",
        root=root,
        imported_at=_now(),
        document_path=CANVAS_NAME,
    )
    _write_record(root, record)
    return record


def import_theme_pack(pack: str | Path) -> ImportedVisualPackRecord:
    path = Path(pack).expanduser()
    manifest, document, assets = _read_theme_pack(path)
    root = imported_theme_packs_dir() / manifest.id
    _replace_dir(root)
    shutil.copy2(path, root / path.name)
    (root / THEME_NAME).write_text(_dump_yaml(document.model_dump(mode="json")), encoding="utf-8")
    _copy_assets(root, assets)
    record = ImportedVisualPackRecord(
        import_id=manifest.id,
        pack_id=manifest.id,
        pack_type="theme",
        name=manifest.name,
        version=manifest.version,
        status="quarantined",
        root=root,
        imported_at=_now(),
        document_path=THEME_NAME,
    )
    _write_record(root, record)
    return record


def _read_canvas_pack(path: Path) -> tuple[CanvasPackManifest, CanvasDocument, dict[str, bytes]]:
    raw = _read_zip(path, expected_extension=CANVAS_PACK_EXTENSION)
    manifest = _parse_manifest(raw, CanvasPackManifest)
    if CANVAS_NAME not in raw:
        raise VisualPackError("canvas pack is missing canvas.yaml")
    try:
        document = CanvasDocument.model_validate(yaml.safe_load(_read_text_entry(raw, CANVAS_NAME)))
    except (ValidationError, TypeError, ValueError) as exc:
        raise VisualPackError(f"invalid canvas.yaml: {exc}") from exc
    validation = validate_canvas_structure(document, imported=True, canvas_dir=None)
    if not validation.valid:
        raise VisualPackError(f"invalid imported canvas: {validation.errors}")
    if document.id != manifest.canvas_id:
        raise VisualPackError("canvas pack manifest canvas_id does not match canvas.yaml")
    return manifest, document, _declared_asset_entries(
        raw,
        manifest.assets,
        referenced_assets=_canvas_asset_references(document),
        require_references=True,
    )


def _read_theme_pack(path: Path) -> tuple[ThemePackManifest, CanvasTheme, dict[str, bytes]]:
    raw = _read_zip(path, expected_extension=THEME_PACK_EXTENSION)
    manifest = _parse_manifest(raw, ThemePackManifest)
    if THEME_NAME not in raw:
        raise VisualPackError("theme pack is missing theme.yaml")
    try:
        theme = CanvasTheme.model_validate(yaml.safe_load(_read_text_entry(raw, THEME_NAME)))
    except (ValidationError, TypeError, ValueError) as exc:
        raise VisualPackError(f"invalid theme.yaml: {exc}") from exc
    if _document_like_keys(yaml.safe_load(_read_text_entry(raw, THEME_NAME))):
        raise VisualPackError("theme packs must not contain recipes, steps, actions, or components")
    if theme.id != manifest.theme_id:
        raise VisualPackError("theme pack manifest theme_id does not match theme.yaml")
    return manifest, theme, _declared_asset_entries(
        raw,
        manifest.assets,
        referenced_assets=set(),
        require_references=True,
    )


def _read_zip(path: Path, *, expected_extension: str) -> dict[str, bytes]:
    allowed_extensions = _allowed_extensions_for(expected_extension)
    if path.suffix not in allowed_extensions:
        raise VisualPackError(f"expected {expected_extension} archive: {path}")
    allowed_document = CANVAS_NAME if expected_extension == CANVAS_PACK_EXTENSION else THEME_NAME
    allowed_top_level = {MANIFEST_NAME, allowed_document, README_NAME}
    try:
        with ZipFile(path) as archive:
            result: dict[str, bytes] = {}
            seen: set[str] = set()
            for info in archive.infolist():
                name = _validate_zip_name(info.filename)
                if info.is_dir():
                    continue
                normalized = name.casefold()
                if normalized in seen:
                    raise VisualPackError(f"duplicate visual pack entry: {name}")
                seen.add(normalized)
                if name not in allowed_top_level and not name.startswith(ASSETS_PREFIX):
                    raise VisualPackError(f"unexpected visual pack entry: {name}")
                result[name] = archive.read(info)
            return result
    except BadZipFile as exc:
        raise VisualPackError(f"invalid visual pack zip: {exc}") from exc


def _parse_manifest(raw: Mapping[str, bytes], model: type[CanvasPackManifest] | type[ThemePackManifest]):
    if MANIFEST_NAME not in raw:
        raise VisualPackError("visual pack is missing manifest.yaml")
    try:
        data = yaml.safe_load(_read_text_entry(raw, MANIFEST_NAME))
        return model.model_validate(data)
    except (ValidationError, TypeError, ValueError) as exc:
        raise VisualPackError(f"invalid visual pack manifest: {exc}") from exc


def _write_pack(
    out: Path,
    expected_extension: str,
    pack_id: str,
    pack_type: str,
    entries: Mapping[str, str | bytes],
) -> VisualPackResult:
    output = out.expanduser()
    if output.suffix != expected_extension:
        output = output.with_suffix(expected_extension)
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return VisualPackResult(
        output_path=output,
        pack_id=pack_id,
        pack_type=pack_type,
        entries=tuple(entries),
    )


def _allowed_extensions_for(expected_extension: str) -> frozenset[str]:
    if expected_extension == CANVAS_PACK_EXTENSION:
        return CANVAS_PACK_EXTENSIONS
    if expected_extension == THEME_PACK_EXTENSION:
        return THEME_PACK_EXTENSIONS
    return frozenset({expected_extension})


def _load_theme(theme: str | Path) -> CanvasTheme:
    candidate = Path(str(theme)).expanduser()
    if not candidate.exists():
        candidate = themes_path() / f"{theme}.yaml"
    if candidate.exists():
        try:
            return CanvasTheme.model_validate(yaml.safe_load(candidate.read_text(encoding="utf-8")))
        except (ValidationError, OSError, TypeError, ValueError) as exc:
            raise VisualPackError(f"invalid theme {candidate}: {exc}") from exc
    if str(theme).strip() in {"setpiece_default", "default"}:
        return CanvasTheme()
    raise VisualPackError(f"theme not found: {theme}")


def _prepare_canvas_for_export(
    document: CanvasDocument,
    source_dir: Path | None,
) -> tuple[CanvasDocument, dict[str, bytes]]:
    assets: dict[str, bytes] = {}
    components = []
    for component in document.components:
        props = component.props_dict()
        changed = False
        for prop_name in ("image", "path", "source"):
            raw = props.get(prop_name)
            if not isinstance(raw, str) or not raw.strip():
                continue
            asset_path = _resolve_local_asset(raw, source_dir)
            if asset_path is None:
                continue
            asset_name = _asset_archive_name(asset_path, assets)
            props[prop_name] = asset_name
            content = asset_path.read_bytes()
            _validate_visual_asset_content(asset_name, content)
            assets[asset_name] = content
            changed = True
        components.append(
            component.model_copy(update={"props": CanvasComponentProps.model_validate(props)})
            if changed
            else component
        )
    return document.model_copy(update={"components": tuple(components)}, deep=True), assets


def _resolve_local_asset(raw: str, source_dir: Path | None) -> Path | None:
    text = raw.strip()
    if "://" in text:
        raise VisualPackError("remote canvas asset URLs are not allowed in canvas packs")
    candidate = Path(text).expanduser()
    if not candidate.is_absolute() and source_dir is not None:
        candidate = source_dir / candidate
    if not candidate.exists() or not candidate.is_file():
        return None
    if candidate.suffix.casefold() not in _ALLOWED_VISUAL_ASSET_SUFFIXES:
        raise VisualPackError(f"canvas pack assets must be raster image files: {candidate.name}")
    return candidate.resolve()


def _asset_archive_name(path: Path, existing: Mapping[str, bytes]) -> str:
    safe_stem = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in path.stem).strip("_")
    safe_stem = safe_stem or "asset"
    digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:8]
    name = f"{ASSETS_PREFIX}{safe_stem}_{digest}{path.suffix.lower()}"
    _validate_asset_name(name)
    if name not in existing:
        return name
    counter = 2
    while True:
        candidate = f"{ASSETS_PREFIX}{safe_stem}_{digest}_{counter}{path.suffix.lower()}"
        _validate_asset_name(candidate)
        if candidate not in existing:
            return candidate
        counter += 1


def _canvas_source_dir(canvas: str | Path) -> Path | None:
    candidate = Path(str(canvas)).expanduser()
    if candidate.exists() and candidate.is_file():
        return candidate.parent
    text = str(canvas).strip()
    for reference in list_canvases(include_bundled=True):
        if reference.canvas_id == text or reference.path.stem == text:
            return reference.path.parent
    return None


def _validate_zip_name(name: str) -> str:
    if "\\" in name:
        raise VisualPackError(f"unsafe visual pack entry path: {name}")
    posix = PurePosixPath(name)
    if posix.is_absolute() or any(part in {"", ".", ".."} or ":" in part for part in posix.parts):
        raise VisualPackError(f"unsafe visual pack entry path: {name}")
    return posix.as_posix()


def _validate_asset_name(name: str) -> str:
    text = str(name).strip().replace("\\", "/")
    if not text:
        raise ValueError("asset name must not be blank")
    _validate_zip_name(text)
    if not text.startswith(ASSETS_PREFIX):
        raise ValueError("asset names must live under assets/")
    suffix = PurePosixPath(text).suffix.casefold()
    if suffix in _SUSPICIOUS_ASSET_SUFFIXES or suffix not in _ALLOWED_VISUAL_ASSET_SUFFIXES:
        raise ValueError("visual pack assets must be raster image files")
    return text


def _validate_manifest_assets(value: list[str]) -> list[str]:
    assets = [_validate_asset_name(item) for item in value]
    seen: set[str] = set()
    duplicates: list[str] = []
    for asset in assets:
        normalized = asset.casefold()
        if normalized in seen:
            duplicates.append(asset)
        seen.add(normalized)
    if duplicates:
        raise ValueError(f"duplicate visual pack assets: {duplicates}")
    return assets


def _asset_entries(raw: Mapping[str, bytes]) -> dict[str, bytes]:
    return {name: content for name, content in raw.items() if name.startswith(ASSETS_PREFIX)}


def _declared_asset_entries(
    raw: Mapping[str, bytes],
    declared_assets: list[str],
    *,
    referenced_assets: set[str],
    require_references: bool,
) -> dict[str, bytes]:
    assets = _asset_entries(raw)
    declared = set(declared_assets)
    actual = set(assets)
    missing = sorted(declared - actual)
    undeclared = sorted(actual - declared)
    if missing:
        raise VisualPackError(f"visual pack manifest declares missing assets: {missing}")
    if undeclared:
        raise VisualPackError(f"visual pack contains undeclared assets: {undeclared}")
    if require_references:
        unreferenced = sorted(declared - referenced_assets)
        missing_referenced = sorted(referenced_assets - actual)
        if missing_referenced:
            raise VisualPackError(f"canvas pack references missing assets: {missing_referenced}")
        if unreferenced:
            raise VisualPackError(f"visual pack declares unused assets: {unreferenced}")
    for name, content in assets.items():
        _validate_visual_asset_content(name, content)
    return assets


def _require_exact_canvas_assets(document: CanvasDocument, assets: Mapping[str, bytes]) -> None:
    referenced_assets = _canvas_asset_references(document)
    actual_assets = set(assets)
    missing = sorted(referenced_assets - actual_assets)
    unused = sorted(actual_assets - referenced_assets)
    if missing:
        raise VisualPackError(f"canvas pack references missing assets: {missing}")
    if unused:
        raise VisualPackError(f"canvas pack includes unreferenced assets: {unused}")


def _canvas_asset_references(document: CanvasDocument) -> set[str]:
    references: set[str] = set()
    for component in document.components:
        props = component.props_dict()
        for key in _CANVAS_ASSET_PROP_NAMES:
            raw = props.get(key)
            if not isinstance(raw, str) or not raw.strip():
                continue
            text = raw.strip().replace("\\", "/")
            if "://" in text:
                raise VisualPackError("remote canvas asset URLs are not allowed in canvas packs")
            if not text.startswith(ASSETS_PREFIX):
                raise VisualPackError("canvas pack asset references must live under assets/")
            try:
                references.add(_validate_asset_name(text))
            except ValueError as exc:
                raise VisualPackError(str(exc)) from exc
    return references


def _validate_visual_asset_content(name: str, content: bytes) -> None:
    head = content[:4096]
    if head.startswith(b"MZ"):
        raise VisualPackError(f"visual pack asset appears executable: {name}")
    text = head.decode("utf-8", errors="ignore").casefold()
    if any(marker in text for marker in _SUSPICIOUS_ASSET_TEXT_MARKERS):
        raise VisualPackError(f"visual pack asset appears script-like: {name}")


def _copy_assets(root: Path, assets: Mapping[str, bytes]) -> None:
    for name, content in assets.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


def _read_text_entry(raw: Mapping[str, bytes], name: str) -> str:
    try:
        return raw[name].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise VisualPackError(f"{name} must be UTF-8 text") from exc


def _document_like_keys(data: object) -> bool:
    if not isinstance(data, dict):
        return False
    forbidden = {"steps", "preflight", "verify", "actions", "components", "recipes", "intents"}
    return any(key in data for key in forbidden)


def _dump_yaml(data: Mapping[str, Any]) -> str:
    return yaml.safe_dump(dict(data), sort_keys=False, allow_unicode=False)


def _replace_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _write_record(root: Path, record: ImportedVisualPackRecord) -> None:
    (root / "import.json").write_text(
        json.dumps(record.to_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
