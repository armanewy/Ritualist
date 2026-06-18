from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Any, Mapping, Sequence
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from . import __version__
from .canvas_packs import (
    CANVAS_PACK_EXTENSION,
    SUITE_PACK_EXTENSION,
    THEME_PACK_EXTENSION,
    VisualPackError,
    import_canvas_pack,
    import_theme_pack,
)
from .canvas_packs import _read_canvas_pack, _read_theme_pack
from .errors import RitualistError
from .models import SAFE_ID_PATTERN
from .packs import PACK_EXTENSION, PackValidationError, import_pack, validate_pack
from .paths import imported_suite_packs_dir, imported_suite_packs_path

SUITE_PACK_SCHEMA = "ritualist.suite_pack.v1"
SUITE_IMPORT_SCHEMA = "ritualist.suite_import.v1"
MANIFEST_NAME = "manifest.yaml"
README_NAME = "README.md"
SUITE_COPY_NAME = "suite.ritualistsuite"
CANVAS_PACK_PREFIX = "packs/canvas/"
THEME_PACK_PREFIX = "packs/theme/"
RITUAL_PACK_PREFIX = "packs/rituals/"
ALLOWED_TOP_LEVEL = {MANIFEST_NAME, README_NAME}


class SuitePackError(RitualistError):
    """Raised when a .ritualistsuite archive or manifest is invalid."""


class SuitePackSafety(BaseModel):
    model_config = ConfigDict(extra="forbid")

    no_arbitrary_code: bool = True
    no_executable_assets: bool = True
    no_auto_run: bool = True
    no_auto_enable: bool = True
    no_remote_execution: bool = True
    no_remembered_approvals: bool = True
    imports_enter_quarantine: bool = True
    rituals_disabled_until_enabled: bool = True
    marketplace_out_of_scope: bool = True

    @field_validator(
        "no_arbitrary_code",
        "no_executable_assets",
        "no_auto_run",
        "no_auto_enable",
        "no_remote_execution",
        "no_remembered_approvals",
        "imports_enter_quarantine",
        "rituals_disabled_until_enabled",
        "marketplace_out_of_scope",
    )
    @classmethod
    def require_true(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("suite pack safety declarations must be true")
        return value


class SuitePackEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    behavior_bearing: bool = False
    disabled_on_import: bool = True

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return _validate_entry_path(value)

    @field_validator("disabled_on_import")
    @classmethod
    def require_disabled_on_import(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("suite entries must remain disabled/quarantined on import")
        return value


class SuitePackContents(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canvas: SuitePackEntry
    theme: SuitePackEntry | None = None
    rituals: list[SuitePackEntry] = Field(default_factory=list)

    @field_validator("canvas")
    @classmethod
    def validate_canvas_entry(cls, value: SuitePackEntry) -> SuitePackEntry:
        if not value.path.startswith(CANVAS_PACK_PREFIX) or not value.path.endswith(CANVAS_PACK_EXTENSION):
            raise ValueError("suite canvas entry must be a .ritualistcanvas under packs/canvas/")
        if value.behavior_bearing:
            raise ValueError("suite canvas entry must not be marked behavior-bearing")
        return value

    @field_validator("theme")
    @classmethod
    def validate_theme_entry(cls, value: SuitePackEntry | None) -> SuitePackEntry | None:
        if value is None:
            return None
        if not value.path.startswith(THEME_PACK_PREFIX) or not value.path.endswith(THEME_PACK_EXTENSION):
            raise ValueError("suite theme entry must be a .ritualisttheme under packs/theme/")
        if value.behavior_bearing:
            raise ValueError("suite theme entry must not be marked behavior-bearing")
        return value

    @field_validator("rituals")
    @classmethod
    def validate_ritual_entries(cls, value: list[SuitePackEntry]) -> list[SuitePackEntry]:
        seen: set[str] = set()
        for entry in value:
            if not entry.path.startswith(RITUAL_PACK_PREFIX) or not entry.path.endswith(PACK_EXTENSION):
                raise ValueError("suite ritual entries must be .ritualistpack files under packs/rituals/")
            if entry.behavior_bearing is not True:
                raise ValueError("suite ritual entries must disclose behavior_bearing: true")
            key = entry.path.casefold()
            if key in seen:
                raise ValueError("suite ritual entries must not contain duplicates")
            seen.add(key)
        return value


class SuitePackManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_: str = Field(alias="schema")
    pack_type: str = "suite"
    id: str
    name: str
    version: str = "0.1.0"
    description: str = ""
    required_ritualist_version: str = __version__
    contents: SuitePackContents
    behavior_bearing_contents: list[str] = Field(default_factory=list)
    safety: SuitePackSafety = Field(default_factory=SuitePackSafety)

    @property
    def schema(self) -> str:
        return self.schema_

    @field_validator("schema_")
    @classmethod
    def validate_schema(cls, value: str) -> str:
        if value != SUITE_PACK_SCHEMA:
            raise ValueError(f"unsupported suite pack schema '{value}'")
        return value

    @field_validator("pack_type")
    @classmethod
    def validate_pack_type(cls, value: str) -> str:
        if value != "suite":
            raise ValueError("suite pack manifest must have pack_type: suite")
        return value

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not SAFE_ID_PATTERN.fullmatch(value):
            raise ValueError("suite id must be a safe filename-like identifier")
        return value

    @field_validator("name", "version")
    @classmethod
    def validate_nonblank(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("suite manifest fields must not be blank")
        return text


@dataclass(frozen=True)
class NestedPackSummary:
    entry: str
    pack_type: str
    pack_id: str
    name: str
    version: str
    behavior_bearing: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry": self.entry,
            "pack_type": self.pack_type,
            "pack_id": self.pack_id,
            "name": self.name,
            "version": self.version,
            "behavior_bearing": self.behavior_bearing,
        }


@dataclass(frozen=True)
class ValidatedSuitePack:
    path: Path
    manifest: SuitePackManifest
    nested_packs: tuple[NestedPackSummary, ...]
    readme: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SUITE_PACK_SCHEMA,
            "path": str(self.path),
            "manifest": self.manifest.model_dump(mode="json", by_alias=True),
            "nested_packs": [item.to_dict() for item in self.nested_packs],
            "readme": self.readme or "",
            "validation": {
                "valid": True,
                "imports_enter_quarantine": True,
                "auto_run": False,
                "auto_enable": False,
            },
        }


@dataclass(frozen=True)
class SuitePackExportResult:
    output_path: Path
    suite_id: str
    entries: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_path": str(self.output_path),
            "suite_id": self.suite_id,
            "entries": list(self.entries),
        }


@dataclass(frozen=True)
class ImportedSuitePackRecord:
    import_id: str
    suite_id: str
    name: str
    version: str
    status: str
    root: Path
    source: str
    imported_at: str
    canvas_import: dict[str, Any]
    theme_import: dict[str, Any] | None = None
    ritual_imports: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    skipped_rituals: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    @property
    def metadata_path(self) -> Path:
        return self.root / "import.json"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SUITE_IMPORT_SCHEMA,
            "import_id": self.import_id,
            "suite_id": self.suite_id,
            "name": self.name,
            "version": self.version,
            "status": self.status,
            "root": str(self.root),
            "source": self.source,
            "imported_at": self.imported_at,
            "canvas_import": self.canvas_import,
            "theme_import": self.theme_import,
            "ritual_imports": list(self.ritual_imports),
            "skipped_rituals": list(self.skipped_rituals),
            "auto_run": False,
            "auto_enable": False,
            "imports_entered_quarantine": True,
        }

    @classmethod
    def from_dict(cls, root: Path, raw: Mapping[str, Any]) -> "ImportedSuitePackRecord":
        if raw.get("schema_version") != SUITE_IMPORT_SCHEMA:
            raise SuitePackError(f"unsupported suite import schema: {raw.get('schema_version')!r}")
        return cls(
            import_id=_require_safe_id(raw.get("import_id"), "import_id"),
            suite_id=_require_safe_id(raw.get("suite_id"), "suite_id"),
            name=_require_string(raw.get("name"), "suite name"),
            version=_require_string(raw.get("version"), "suite version"),
            status=_require_string(raw.get("status"), "status"),
            root=root,
            source=_require_string(raw.get("source"), "source"),
            imported_at=_require_string(raw.get("imported_at"), "imported_at"),
            canvas_import=_mapping(raw.get("canvas_import")),
            theme_import=_mapping(raw.get("theme_import")) if raw.get("theme_import") else None,
            ritual_imports=tuple(
                _mapping(item) for item in raw.get("ritual_imports", []) if isinstance(item, Mapping)
            ),
            skipped_rituals=tuple(
                _mapping(item) for item in raw.get("skipped_rituals", []) if isinstance(item, Mapping)
            ),
        )


def export_suite_pack(
    *,
    canvas_pack: str | Path,
    out: str | Path,
    suite_id: str | None = None,
    name: str | None = None,
    version: str = "0.1.0",
    description: str = "",
    theme_pack: str | Path | None = None,
    ritual_packs: Sequence[str | Path] = (),
    readme_path: str | Path | None = None,
) -> SuitePackExportResult:
    """Export a whole-Room suite from already validated pack artifacts."""

    canvas_path = Path(canvas_pack).expanduser()
    theme_path = Path(theme_pack).expanduser() if theme_pack is not None else None
    ritual_paths = tuple(Path(path).expanduser() for path in ritual_packs)

    canvas_summary = _validated_canvas_summary(canvas_path, _suite_entry_name(CANVAS_PACK_PREFIX, canvas_path))
    theme_summary = (
        _validated_theme_summary(theme_path, _suite_entry_name(THEME_PACK_PREFIX, theme_path))
        if theme_path is not None
        else None
    )
    ritual_summaries = tuple(
        _validated_ritual_summary(path, _suite_entry_name(RITUAL_PACK_PREFIX, path))
        for path in ritual_paths
    )

    resolved_id = suite_id or _suite_id_from_canvas(canvas_summary.pack_id)
    if not SAFE_ID_PATTERN.fullmatch(resolved_id):
        raise SuitePackError("suite id must be a safe filename-like identifier")
    resolved_name = (name or f"{canvas_summary.name} Suite").strip()
    if not resolved_name:
        raise SuitePackError("suite name must not be blank")

    contents = SuitePackContents(
        canvas=SuitePackEntry(path=canvas_summary.entry),
        theme=SuitePackEntry(path=theme_summary.entry) if theme_summary is not None else None,
        rituals=[
            SuitePackEntry(path=item.entry, behavior_bearing=True)
            for item in ritual_summaries
        ],
    )
    manifest = SuitePackManifest(
        schema=SUITE_PACK_SCHEMA,
        id=resolved_id,
        name=resolved_name,
        version=version,
        description=description,
        contents=contents,
        behavior_bearing_contents=[item.entry for item in ritual_summaries],
    )

    entries: dict[str, bytes] = {
        MANIFEST_NAME: _dump_yaml(manifest.model_dump(mode="json", by_alias=True)).encode("utf-8"),
        canvas_summary.entry: canvas_path.read_bytes(),
    }
    if theme_path is not None and theme_summary is not None:
        entries[theme_summary.entry] = theme_path.read_bytes()
    for summary, path in zip(ritual_summaries, ritual_paths, strict=True):
        entries[summary.entry] = path.read_bytes()
    if readme_path is not None:
        entries[README_NAME] = _read_text_file(readme_path).encode("utf-8")

    output = _normalize_suite_output_path(out)
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for entry, content in entries.items():
            archive.writestr(entry, content)
    validate_suite_pack(output)
    return SuitePackExportResult(
        output_path=output,
        suite_id=manifest.id,
        entries=tuple(entries),
    )


def validate_suite_pack(path: str | Path) -> ValidatedSuitePack:
    pack_path = Path(path).expanduser()
    raw = _read_suite_zip(pack_path)
    manifest = _parse_manifest(raw)
    _validate_declared_entries(manifest, raw)
    nested = _validate_nested_packs(raw, manifest)
    readme = _read_text_entry(raw, README_NAME) if README_NAME in raw else None
    return ValidatedSuitePack(
        path=pack_path,
        manifest=manifest,
        nested_packs=nested,
        readme=readme,
    )


def import_suite_pack(
    path: str | Path,
    *,
    include_rituals: bool = True,
) -> ImportedSuitePackRecord:
    """Validate and import a suite into quarantine without enabling or running anything."""

    validated = validate_suite_pack(path)
    import_id = _next_suite_import_id(validated.manifest.id)
    root = imported_suite_packs_dir() / import_id
    imported_at = _now()
    try:
        root.mkdir(parents=True, exist_ok=False)
        shutil.copy2(validated.path, root / SUITE_COPY_NAME)
        (root / MANIFEST_NAME).write_text(
            _dump_yaml(validated.manifest.model_dump(mode="json", by_alias=True)),
            encoding="utf-8",
        )
        if validated.readme is not None:
            (root / README_NAME).write_text(validated.readme, encoding="utf-8")
        raw = _read_suite_zip(validated.path)
        with TemporaryDirectory(prefix="ritualist-suite-import-") as temp:
            temp_root = Path(temp)
            canvas_record = import_canvas_pack(
                _write_temp_nested_pack(temp_root, validated.manifest.contents.canvas.path, raw)
            )
            theme_record = (
                import_theme_pack(
                    _write_temp_nested_pack(temp_root, validated.manifest.contents.theme.path, raw)
                )
                if validated.manifest.contents.theme is not None
                else None
            )
            ritual_records = []
            skipped_rituals = []
            for ritual_entry in validated.manifest.contents.rituals:
                if not include_rituals:
                    skipped_rituals.append(
                        {
                            "entry": ritual_entry.path,
                            "reason": "visuals_only_import",
                            "behavior_bearing": True,
                        }
                    )
                    continue
                ritual_record = import_pack(_write_temp_nested_pack(temp_root, ritual_entry.path, raw))
                ritual_records.append(ritual_record.to_dict())
        record = ImportedSuitePackRecord(
            import_id=import_id,
            suite_id=validated.manifest.id,
            name=validated.manifest.name,
            version=validated.manifest.version,
            status="quarantined",
            root=root,
            source=str(validated.path),
            imported_at=imported_at,
            canvas_import=canvas_record.to_dict(),
            theme_import=theme_record.to_dict() if theme_record is not None else None,
            ritual_imports=tuple(ritual_records),
            skipped_rituals=tuple(skipped_rituals),
        )
        _write_import_record(record)
        return record
    except Exception:
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        raise


def list_suite_imports() -> list[ImportedSuitePackRecord]:
    root = imported_suite_packs_path()
    if not root.exists():
        return []
    records: list[ImportedSuitePackRecord] = []
    for metadata_path in sorted(root.glob("*/import.json")):
        records.append(_read_import_record(metadata_path.parent))
    return records


def _validate_nested_packs(
    raw: Mapping[str, bytes],
    manifest: SuitePackManifest,
) -> tuple[NestedPackSummary, ...]:
    with TemporaryDirectory(prefix="ritualist-suite-validate-") as temp:
        temp_root = Path(temp)
        nested = [
            _validate_canvas_pack_path(
                _write_temp_nested_pack(temp_root, manifest.contents.canvas.path, raw),
                manifest.contents.canvas.path,
            ),
        ]
        if manifest.contents.theme is not None:
            nested.append(
                _validate_theme_pack_path(
                    _write_temp_nested_pack(temp_root, manifest.contents.theme.path, raw),
                    manifest.contents.theme.path,
                )
            )
        for entry in manifest.contents.rituals:
            nested.append(
                _validate_ritual_pack_path(
                    _write_temp_nested_pack(temp_root, entry.path, raw),
                    entry.path,
                )
            )
        return tuple(nested)


def _validated_canvas_summary(path: Path, entry: str) -> NestedPackSummary:
    with TemporaryDirectory(prefix="ritualist-suite-export-") as temp:
        temp_path = Path(temp) / Path(entry).name
        temp_path.write_bytes(path.read_bytes())
        return _validate_canvas_pack_path(temp_path, entry)


def _validated_theme_summary(path: Path, entry: str) -> NestedPackSummary:
    with TemporaryDirectory(prefix="ritualist-suite-export-") as temp:
        temp_path = Path(temp) / Path(entry).name
        temp_path.write_bytes(path.read_bytes())
        return _validate_theme_pack_path(temp_path, entry)


def _validated_ritual_summary(path: Path, entry: str) -> NestedPackSummary:
    with TemporaryDirectory(prefix="ritualist-suite-export-") as temp:
        temp_path = Path(temp) / Path(entry).name
        temp_path.write_bytes(path.read_bytes())
        return _validate_ritual_pack_path(temp_path, entry)


def _validate_canvas_pack_path(path: Path, entry: str) -> NestedPackSummary:
    try:
        manifest, _document, _assets = _read_canvas_pack(path)
    except VisualPackError as exc:
        raise SuitePackError(f"invalid nested canvas pack {entry}: {exc}") from exc
    return NestedPackSummary(
        entry=entry,
        pack_type="canvas",
        pack_id=manifest.id,
        name=manifest.name,
        version=manifest.version,
        behavior_bearing=False,
    )


def _validate_theme_pack_path(path: Path, entry: str) -> NestedPackSummary:
    try:
        manifest, _document, _assets = _read_theme_pack(path)
    except VisualPackError as exc:
        raise SuitePackError(f"invalid nested theme pack {entry}: {exc}") from exc
    return NestedPackSummary(
        entry=entry,
        pack_type="theme",
        pack_id=manifest.id,
        name=manifest.name,
        version=manifest.version,
        behavior_bearing=False,
    )


def _validate_ritual_pack_path(path: Path, entry: str) -> NestedPackSummary:
    try:
        pack = validate_pack(path)
    except PackValidationError as exc:
        raise SuitePackError(f"invalid nested ritual pack {entry}: {exc}") from exc
    return NestedPackSummary(
        entry=entry,
        pack_type="ritual",
        pack_id=pack.manifest.id,
        name=pack.manifest.name,
        version=pack.manifest.version,
        behavior_bearing=True,
    )


def _read_suite_zip(path: Path) -> dict[str, bytes]:
    if path.suffix.casefold() != SUITE_PACK_EXTENSION:
        raise SuitePackError(f"expected {SUITE_PACK_EXTENSION} archive: {path}")
    try:
        with ZipFile(path) as archive:
            raw: dict[str, bytes] = {}
            seen: set[str] = set()
            for info in archive.infolist():
                name = _validate_zip_name(info.filename)
                if info.is_dir():
                    continue
                key = name.casefold()
                if key in seen:
                    raise SuitePackError(f"duplicate suite pack entry: {name}")
                seen.add(key)
                if not _entry_allowed_by_layout(name):
                    raise SuitePackError(f"unexpected suite pack entry: {name}")
                raw[name] = archive.read(info)
            return raw
    except BadZipFile as exc:
        raise SuitePackError(f"invalid suite pack zip: {exc}") from exc
    except OSError as exc:
        raise SuitePackError(f"could not read suite pack '{path}': {exc}") from exc


def _parse_manifest(raw: Mapping[str, bytes]) -> SuitePackManifest:
    if MANIFEST_NAME not in raw:
        raise SuitePackError("suite pack is missing manifest.yaml")
    try:
        data = yaml.safe_load(_read_text_entry(raw, MANIFEST_NAME))
        manifest = SuitePackManifest.model_validate(data)
    except (ValidationError, TypeError, ValueError) as exc:
        raise SuitePackError(f"invalid suite pack manifest: {exc}") from exc
    expected_behavior = [entry.path for entry in manifest.contents.rituals]
    if sorted(manifest.behavior_bearing_contents) != sorted(expected_behavior):
        raise SuitePackError("suite manifest must disclose every behavior-bearing ritual pack")
    return manifest


def _validate_declared_entries(
    manifest: SuitePackManifest,
    raw: Mapping[str, bytes],
) -> None:
    declared = {
        MANIFEST_NAME,
        manifest.contents.canvas.path,
        *[entry.path for entry in manifest.contents.rituals],
    }
    if manifest.contents.theme is not None:
        declared.add(manifest.contents.theme.path)
    if README_NAME in raw:
        declared.add(README_NAME)
    actual = set(raw)
    missing = sorted(declared - actual)
    extra = sorted(actual - declared)
    if missing:
        raise SuitePackError(f"suite manifest declares missing entries: {missing}")
    if extra:
        raise SuitePackError(f"suite pack contains undeclared entries: {extra}")


def _write_temp_nested_pack(temp_root: Path, entry: str, raw: Mapping[str, bytes]) -> Path:
    path = temp_root / Path(entry).name
    path.write_bytes(raw[entry])
    return path


def _entry_allowed_by_layout(name: str) -> bool:
    if name in ALLOWED_TOP_LEVEL:
        return True
    if name.startswith(CANVAS_PACK_PREFIX):
        return name.endswith(CANVAS_PACK_EXTENSION)
    if name.startswith(THEME_PACK_PREFIX):
        return name.endswith(THEME_PACK_EXTENSION)
    if name.startswith(RITUAL_PACK_PREFIX):
        return name.endswith(PACK_EXTENSION)
    return False


def _validate_entry_path(value: str) -> str:
    text = str(value or "").strip().replace("\\", "/")
    if not text:
        raise ValueError("suite entry path must not be blank")
    _validate_zip_name(text)
    if text in ALLOWED_TOP_LEVEL:
        raise ValueError("suite content entries must live under packs/")
    if not _entry_allowed_by_layout(text):
        raise ValueError("suite content entries must be supported nested pack files")
    return text


def _validate_zip_name(name: str) -> str:
    if "\\" in name:
        raise SuitePackError(f"unsafe suite pack entry path: {name}")
    posix = PurePosixPath(name)
    if posix.is_absolute() or any(part in {"", ".", ".."} or ":" in part for part in posix.parts):
        raise SuitePackError(f"unsafe suite pack entry path: {name}")
    return posix.as_posix()


def _suite_entry_name(prefix: str, path: Path) -> str:
    if not path.is_file():
        raise SuitePackError(f"nested pack path is not a file: {path}")
    name = path.name
    entry = f"{prefix}{name}"
    _validate_entry_path(entry)
    return entry


def _suite_id_from_canvas(canvas_pack_id: str) -> str:
    text = f"{canvas_pack_id}_suite"
    if SAFE_ID_PATTERN.fullmatch(text):
        return text
    return "room_suite"


def _normalize_suite_output_path(out: str | Path) -> Path:
    path = Path(out).expanduser()
    if path.suffix.casefold() != SUITE_PACK_EXTENSION:
        path = path.with_suffix(SUITE_PACK_EXTENSION)
    return path


def _next_suite_import_id(suite_id: str) -> str:
    root = imported_suite_packs_path()
    if not (root / suite_id).exists():
        return suite_id
    index = 2
    while True:
        suffix = f"-{index}"
        candidate = f"{suite_id[:64 - len(suffix)]}{suffix}"
        if not (root / candidate).exists():
            return candidate
        index += 1


def _read_import_record(root: Path) -> ImportedSuitePackRecord:
    path = root / "import.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SuitePackError(f"could not read suite import record '{path}': {exc}") from exc
    except json.JSONDecodeError as exc:
        raise SuitePackError(f"invalid suite import record '{path}': {exc}") from exc
    if not isinstance(raw, Mapping):
        raise SuitePackError("suite import record must be a mapping")
    return ImportedSuitePackRecord.from_dict(root, raw)


def _write_import_record(record: ImportedSuitePackRecord) -> None:
    record.metadata_path.write_text(
        json.dumps(record.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_text_entry(raw: Mapping[str, bytes], name: str) -> str:
    try:
        return raw[name].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SuitePackError(f"{name} must be UTF-8 text") from exc


def _read_text_file(path: str | Path) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise SuitePackError("suite README must be UTF-8 text") from exc
    except OSError as exc:
        raise SuitePackError(f"could not read suite README: {exc}") from exc


def _dump_yaml(data: Mapping[str, Any]) -> str:
    return yaml.safe_dump(dict(data), sort_keys=False, allow_unicode=False)


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _require_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SuitePackError(f"{field_name} must be a non-empty string")
    return value


def _require_safe_id(value: object, field_name: str) -> str:
    text = _require_string(value, field_name)
    if not SAFE_ID_PATTERN.fullmatch(text):
        raise SuitePackError(f"{field_name} must be a safe filename-like identifier")
    return text


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "ImportedSuitePackRecord",
    "SUITE_IMPORT_SCHEMA",
    "SUITE_PACK_SCHEMA",
    "SuitePackError",
    "SuitePackExportResult",
    "SuitePackManifest",
    "ValidatedSuitePack",
    "export_suite_pack",
    "import_suite_pack",
    "list_suite_imports",
    "validate_suite_pack",
]
