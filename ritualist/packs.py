from __future__ import annotations

import json
import re
import shutil
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Mapping
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile, ZipInfo

import yaml
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError, field_validator

from . import __version__
from .actions.metadata import ALLOWED_CAPABILITIES, ALLOWED_PLATFORMS
from .actions.registry import ActionRegistry, create_default_registry
from .doctor import build_doctor_report
from .errors import RecipeValidationError, RitualistError
from .models import SAFE_ID_PATTERN, Recipe
from .paths import imported_packs_dir, imported_packs_path, recipes_dir
from .policy import (
    PolicyProfile,
    blocked_policy_messages,
    build_policy_report_for_recipe,
    detect_never_importable_raw,
)
from .recipe_loader import load_recipe_document, load_recipe_for_diagnostics

PACK_SCHEMA_V1 = "ritualist.pack.v1"
SUPPORTED_PACK_SCHEMAS = frozenset({PACK_SCHEMA_V1, "v1"})

MANIFEST_NAME = "manifest.yaml"
RECIPE_NAME = "recipe.yaml"
README_NAME = "README.md"
ASSETS_PREFIX = "assets/"
PACK_EXTENSION = ".ritualistpack"
IMPORT_RECORD_SCHEMA = "ritualist.import.v1"
VARIABLE_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")

ARBITRARY_CODE_ACTION_PREFIXES = ("python.", "javascript.", "js.", "shell.")
ARBITRARY_CODE_ACTIONS = frozenset(
    {
        "command.run",
        "process.run",
        "process.spawn",
        "powershell.run",
    }
)
COORDINATE_CLICK_ACTIONS = frozenset(
    {
        "desktop.click_at",
        "desktop.click_coordinates",
        "desktop.click_xy",
        "input.click_at",
        "input.click_coordinates",
        "mouse.click",
        "mouse.click_at",
        "mouse.click_coordinates",
    }
)
RECORD_REPLAY_ACTION_PREFIXES = (
    "macro.",
    "record.",
    "recorder.",
    "recording.",
    "replay.",
    "watch-me.",
    "watch_me.",
)
RECORD_REPLAY_ACTIONS = frozenset(
    {
        "macro.record",
        "macro.replay",
        "record.start",
        "record.stop",
        "recorder.start",
        "recording.start",
        "replay.run",
        "watch-me.start",
        "watch_me.start",
    }
)


class PackValidationError(RecipeValidationError):
    """Raised when a .ritualistpack archive or manifest is invalid."""


class PackImportError(RitualistError):
    """Raised when a recipe pack cannot enter or leave quarantine."""


class PackSafetyDeclarations(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    no_arbitrary_code: bool
    no_coordinate_clicks: bool
    no_remote_execution: bool
    imported_recipes_must_not_run_automatically: bool = Field(
        validation_alias=AliasChoices(
            "imported_recipes_must_not_run_automatically",
            "imports_require_manual_run",
            "manual_import_required",
        )
    )

    @field_validator(
        "no_arbitrary_code",
        "no_coordinate_clicks",
        "no_remote_execution",
        "imported_recipes_must_not_run_automatically",
    )
    @classmethod
    def require_true(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("pack safety declarations must be true")
        return value


class PackManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_: str = Field(alias="schema")
    id: str
    name: str
    version: str
    author: str | None = None
    description: str | None = None
    required_ritualist_version: str
    supported_os: list[str] = Field(min_length=1)
    required_capabilities: list[str]
    required_actions: list[str] = Field(min_length=1)
    variables: dict[str, Any]
    safety: PackSafetyDeclarations = Field(
        validation_alias=AliasChoices("safety", "safety_declarations")
    )

    @property
    def schema(self) -> str:
        return self.schema_

    @field_validator("schema_")
    @classmethod
    def validate_schema(cls, value: str) -> str:
        if value not in SUPPORTED_PACK_SCHEMAS:
            raise ValueError(f"unsupported pack schema '{value}'")
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

    @field_validator("name", "version", "required_ritualist_version")
    @classmethod
    def validate_required_string(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must be a non-empty string")
        return value

    @field_validator("author", "description")
    @classmethod
    def validate_optional_string(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("field must be a non-empty string when provided")
        return value

    @field_validator("supported_os")
    @classmethod
    def validate_supported_os(cls, value: list[str]) -> list[str]:
        _require_unique("supported_os", value)
        for os_name in value:
            if os_name not in ALLOWED_PLATFORMS:
                raise ValueError(f"supported_os contains unsupported OS '{os_name}'")
        return value

    @field_validator("required_capabilities")
    @classmethod
    def validate_required_capabilities(cls, value: list[str]) -> list[str]:
        _require_unique("required_capabilities", value)
        for capability in value:
            if capability not in ALLOWED_CAPABILITIES:
                raise ValueError(
                    f"required_capabilities contains unsupported capability '{capability}'"
                )
        return value

    @field_validator("required_actions")
    @classmethod
    def validate_required_actions(cls, value: list[str]) -> list[str]:
        _require_unique("required_actions", value)
        for action in value:
            if not isinstance(action, str) or not action.strip():
                raise ValueError("required_actions must contain non-empty strings")
        return value

    @field_validator("variables")
    @classmethod
    def validate_variables(cls, value: dict[str, Any]) -> dict[str, Any]:
        for name in value:
            if not _is_safe_variable_name(name):
                raise ValueError(f"variables contains unsafe variable name '{name}'")
        return value


@dataclass(frozen=True)
class RitualistPack:
    path: Path
    manifest: PackManifest
    recipe: Recipe
    readme: str | None = None
    asset_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class PackExportResult:
    output_path: Path
    recipe_id: str
    entries: tuple[str, ...]


@dataclass(frozen=True)
class ImportedRecipe:
    recipe_id: str
    name: str
    path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "recipe_id": self.recipe_id,
            "name": self.name,
            "path": self.path,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ImportedRecipe":
        return cls(
            recipe_id=_require_safe_id(data.get("recipe_id"), "recipe_id"),
            name=_require_string(data.get("name"), "recipe name"),
            path=_require_string(data.get("path"), "recipe path"),
        )


@dataclass(frozen=True)
class ImportedPackRecord:
    import_id: str
    pack_id: str
    name: str
    version: str
    status: str
    source: str
    imported_at: str
    root: Path
    recipes: tuple[ImportedRecipe, ...] = field(default_factory=tuple)
    enabled_at: str | None = None

    @property
    def metadata_path(self) -> Path:
        return self.root / "import.json"

    @property
    def recipe_path(self) -> Path:
        return self.root / RECIPE_NAME

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "schema_version": IMPORT_RECORD_SCHEMA,
            "import_id": self.import_id,
            "pack_id": self.pack_id,
            "name": self.name,
            "version": self.version,
            "status": self.status,
            "source": self.source,
            "imported_at": self.imported_at,
            "recipes": [recipe.to_dict() for recipe in self.recipes],
        }
        if self.enabled_at is not None:
            data["enabled_at"] = self.enabled_at
        return data

    @classmethod
    def from_dict(cls, root: Path, data: Mapping[str, Any]) -> "ImportedPackRecord":
        schema_version = data.get("schema_version")
        if schema_version != IMPORT_RECORD_SCHEMA:
            raise PackImportError(f"unsupported import record schema: {schema_version!r}")
        recipes = data.get("recipes")
        if not isinstance(recipes, list) or not recipes:
            raise PackImportError("import record must include at least one recipe")
        return cls(
            import_id=_require_safe_id(data.get("import_id"), "import_id"),
            pack_id=_require_safe_id(data.get("pack_id"), "pack_id"),
            name=_require_string(data.get("name"), "pack name"),
            version=_require_string(data.get("version"), "pack version"),
            status=_require_string(data.get("status"), "status"),
            source=_require_string(data.get("source"), "source"),
            imported_at=_require_string(data.get("imported_at"), "imported_at"),
            enabled_at=data.get("enabled_at") if isinstance(data.get("enabled_at"), str) else None,
            root=root,
            recipes=tuple(ImportedRecipe.from_dict(item) for item in recipes),
        )


def validate_pack(
    path: str | Path,
    *,
    registry: ActionRegistry | None = None,
) -> RitualistPack:
    """Validate a .ritualistpack archive without extracting or executing its contents."""

    pack_path = Path(path)
    registry = registry or create_default_registry()

    try:
        with ZipFile(pack_path) as archive:
            entries = _validate_zip_layout(archive.infolist())
            if MANIFEST_NAME not in entries:
                raise PackValidationError("pack is missing manifest.yaml")
            if RECIPE_NAME not in entries:
                raise PackValidationError("pack is missing recipe.yaml")

            manifest_raw = _read_yaml_mapping(archive, MANIFEST_NAME)
            recipe_raw = _read_yaml_mapping(archive, RECIPE_NAME)
            readme = _read_optional_text(archive, README_NAME) if README_NAME in entries else None
            asset_names = _asset_names(archive.infolist())
    except BadZipFile as exc:
        raise PackValidationError(f"invalid .ritualistpack zip: {exc}") from exc
    except OSError as exc:
        raise PackValidationError(f"could not read pack '{pack_path}': {exc}") from exc

    return _build_validated_pack(
        pack_path,
        manifest_raw=manifest_raw,
        recipe_raw=recipe_raw,
        readme=readme,
        asset_names=asset_names,
        registry=registry,
    )


def validate_ritualist_pack(
    path: str | Path,
    *,
    registry: ActionRegistry | None = None,
) -> RitualistPack:
    return validate_pack(path, registry=registry)


def load_pack(
    path: str | Path,
    *,
    registry: ActionRegistry | None = None,
) -> RitualistPack:
    return validate_pack(path, registry=registry)


def export_recipe_pack(
    recipe_id_or_path: str | Path,
    out_path: str | Path,
    *,
    readme_path: str | Path | None = None,
    registry: ActionRegistry | None = None,
) -> PackExportResult:
    """Export a validated recipe into a portable Ritualist pack archive."""

    recipe, raw_recipe, missing_variables = load_recipe_for_diagnostics(recipe_id_or_path)
    output_path = _normalize_pack_output_path(out_path)
    readme_text = _read_optional_file(readme_path, "README") if readme_path is not None else None
    exportable_recipe, generated_variables = _exportable_recipe_raw(
        raw_recipe,
        missing_variables=missing_variables,
    )
    manifest = build_pack_manifest(
        recipe=recipe,
        raw_recipe=raw_recipe,
        missing_variables=missing_variables,
        extra_variable_declarations=generated_variables,
        registry=registry,
    )

    entries = [MANIFEST_NAME, RECIPE_NAME]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output_path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(
            MANIFEST_NAME,
            yaml.safe_dump(
                manifest.model_dump(mode="json", by_alias=True),
                sort_keys=False,
                allow_unicode=True,
            ),
        )
        archive.writestr(
            RECIPE_NAME,
            yaml.safe_dump(exportable_recipe, sort_keys=False, allow_unicode=True),
        )
        if readme_text is not None:
            archive.writestr(README_NAME, readme_text)
            entries.append(README_NAME)

    validate_pack(output_path, registry=registry)
    return PackExportResult(
        output_path=output_path,
        recipe_id=recipe.id,
        entries=tuple(entries),
    )


def build_pack_manifest(
    *,
    recipe: Recipe,
    raw_recipe: Mapping[str, Any],
    missing_variables: list[str] | tuple[str, ...] = (),
    extra_variable_declarations: Mapping[str, Any] | None = None,
    registry: ActionRegistry | None = None,
) -> PackManifest:
    registry = registry or create_default_registry()
    actions = _unique_preserving_order(_collect_recipe_actions(raw_recipe))
    capabilities = _unique_preserving_order(
        [
            *(
                capability
                for action in actions
                for capability in registry.metadata(action).required_capabilities
            ),
            *_collect_condition_capabilities(raw_recipe),
        ]
    )
    supported_os = _supported_os_for_capabilities(
        _supported_os_for_actions(actions, registry),
        capabilities,
    )
    variables = _manifest_variable_declarations(raw_recipe, missing_variables)
    variables.update(extra_variable_declarations or {})
    return PackManifest(
        schema=PACK_SCHEMA_V1,
        id=recipe.id,
        name=recipe.name,
        version="1.0.0",
        description=recipe.description,
        required_ritualist_version=f">={__version__}",
        supported_os=supported_os,
        required_capabilities=capabilities,
        required_actions=actions,
        variables=variables,
        safety=PackSafetyDeclarations(
            no_arbitrary_code=True,
            no_coordinate_clicks=True,
            no_remote_execution=True,
            imported_recipes_must_not_run_automatically=True,
        ),
    )


def import_pack(pack: str | Path, *, registry: ActionRegistry | None = None) -> ImportedPackRecord:
    """Validate and copy a .ritualistpack into quarantine without running it."""

    validated = validate_pack(pack, registry=registry)
    import_id = _next_import_id(validated.manifest.id)
    root = imported_packs_dir() / import_id
    imported_at = datetime.now(timezone.utc).isoformat()
    try:
        root.mkdir(parents=True, exist_ok=False)
        _extract_validated_pack(validated.path, root)
        _write_materialized_recipe_for_enable(root, validated.manifest)
        record = ImportedPackRecord(
            import_id=import_id,
            pack_id=validated.manifest.id,
            name=validated.manifest.name,
            version=validated.manifest.version,
            status="disabled",
            source=str(validated.path),
            imported_at=imported_at,
            root=root,
            recipes=(
                ImportedRecipe(
                    recipe_id=validated.recipe.id,
                    name=validated.recipe.name,
                    path=RECIPE_NAME,
                ),
            ),
        )
        _write_import_record(record)
        return record
    except Exception:
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        raise


def list_imports() -> list[ImportedPackRecord]:
    root = imported_packs_path()
    if not root.exists():
        return []
    records: list[ImportedPackRecord] = []
    for metadata_path in sorted(root.glob("*/import.json")):
        records.append(_read_import_record(metadata_path.parent))
    return records


def get_import(import_id: str) -> ImportedPackRecord:
    root = imported_packs_dir() / _require_safe_id(import_id, "import_id")
    if not root.exists():
        raise PackImportError(f"import not found: {import_id}")
    return _read_import_record(root)


def enable_import(import_id: str, *, registry: ActionRegistry | None = None) -> ImportedPackRecord:
    """Validate a quarantined pack and copy its recipe into enabled recipes without running it."""

    record = get_import(import_id)
    if record.status == "enabled":
        raise PackImportError(f"import already enabled: {import_id}")
    if record.status != "disabled":
        raise PackImportError(f"import is not disabled: {import_id}")

    resolved_registry = registry or create_default_registry()
    pack = validate_imported_pack(record.root, registry=resolved_registry)
    policy_report = build_policy_report_for_recipe(
        pack.recipe,
        target=str(record.root),
        profile=PolicyProfile.CONSUMER_SAFE,
        imported=True,
        private_or_local=False,
        registry=resolved_registry,
    )
    blocked = blocked_policy_messages(policy_report)
    if blocked:
        raise PackImportError(
            "imported pack is blocked by primitive policy: " + "; ".join(blocked)
        )
    doctor_report = build_doctor_report(pack.recipe, registry=resolved_registry)
    blocking_doctor_errors = _blocking_import_doctor_errors(doctor_report)
    if blocking_doctor_errors:
        raise PackImportError(
            f"doctor validation failed for {pack.recipe.id}; run 'ritualist doctor {record.recipe_path}'"
        )

    destination = recipes_dir() / f"{pack.recipe.id}.yaml"
    if destination.exists():
        raise PackImportError(f"enabled recipe already exists: {destination}")
    shutil.copyfile(record.recipe_path, destination)

    enabled = ImportedPackRecord(
        import_id=record.import_id,
        pack_id=record.pack_id,
        name=record.name,
        version=record.version,
        status="enabled",
        source=record.source,
        imported_at=record.imported_at,
        enabled_at=datetime.now(timezone.utc).isoformat(),
        root=record.root,
        recipes=record.recipes,
    )
    _write_import_record(enabled)
    return enabled


def _blocking_import_doctor_errors(doctor_report: Any) -> list[Any]:
    """Return Doctor errors that should block enabling a quarantined pack.

    Pack import already validates schema, action metadata, declared capabilities,
    platform compatibility, and primitive policy. Playwright availability still
    belongs in Doctor output, but it should not prevent a safe read-only browser
    wait recipe from leaving quarantine in environments where browser extras are
    not installed yet.
    """

    return [
        check
        for check in doctor_report.checks
        if check.status == "error" and not _is_non_blocking_import_doctor_error(check)
    ]


def _is_non_blocking_import_doctor_error(check: Any) -> bool:
    return (
        check.section == "Capabilities"
        and getattr(check, "details", {}).get("module") == "playwright.sync_api"
    )


def validate_imported_pack(
    root: str | Path,
    *,
    registry: ActionRegistry | None = None,
) -> RitualistPack:
    root_path = Path(root)
    manifest_raw = _read_yaml_mapping_path(root_path / MANIFEST_NAME)
    recipe_raw = _read_yaml_mapping_path(root_path / RECIPE_NAME)
    readme_path = root_path / README_NAME
    readme = readme_path.read_text(encoding="utf-8") if readme_path.exists() else None
    asset_names = tuple(
        sorted(
            path.relative_to(root_path).as_posix()
            for path in (root_path / "assets").rglob("*")
            if path.is_file()
        )
    ) if (root_path / "assets").exists() else ()
    return _build_validated_pack(
        root_path,
        manifest_raw=manifest_raw,
        recipe_raw=recipe_raw,
        readme=readme,
        asset_names=asset_names,
        registry=registry or create_default_registry(),
    )


def _build_validated_pack(
    pack_path: Path,
    *,
    manifest_raw: Mapping[str, Any],
    recipe_raw: dict[str, Any],
    readme: str | None,
    asset_names: tuple[str, ...],
    registry: ActionRegistry,
) -> RitualistPack:
    manifest = _parse_manifest(manifest_raw)
    never_importable = detect_never_importable_raw(
        recipe_raw,
        manifest_raw=manifest_raw,
        asset_names=asset_names,
    )
    if never_importable:
        messages = "; ".join(
            f"{finding.primitive_id} at {finding.source}" for finding in never_importable
        )
        raise PackValidationError(f"never-importable pack content is blocked: {messages}")
    _validate_manifest_actions(manifest, registry)

    raw_recipe_actions = _collect_recipe_actions(recipe_raw)
    _validate_recipe_action_policy(raw_recipe_actions, registry)
    _validate_required_action_declarations(manifest, raw_recipe_actions)
    _validate_required_capabilities(manifest, registry)
    _validate_required_condition_capabilities(manifest, recipe_raw)
    _validate_supported_os(manifest, registry)

    recipe = _parse_recipe(recipe_raw, manifest)
    return RitualistPack(
        path=pack_path,
        manifest=manifest,
        recipe=recipe,
        readme=readme,
        asset_names=asset_names,
    )


def _parse_manifest(raw: Mapping[str, Any]) -> PackManifest:
    try:
        return PackManifest.model_validate(raw)
    except ValidationError as exc:
        raise PackValidationError(f"invalid manifest.yaml: {exc}") from exc


def _parse_recipe(raw: dict[str, Any], manifest: PackManifest) -> Recipe:
    try:
        return load_recipe_document(_recipe_raw_with_manifest_variables(raw, manifest.variables))
    except RecipeValidationError as exc:
        raise PackValidationError(f"invalid recipe.yaml: {exc}") from exc


def _read_yaml_mapping(archive: ZipFile, name: str) -> dict[str, Any]:
    text = _read_text(archive, name)
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise PackValidationError(f"invalid YAML in {name}: {exc}") from exc
    if not isinstance(raw, dict):
        raise PackValidationError(f"{name} must be a YAML mapping")
    return raw


def _read_yaml_mapping_path(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PackValidationError(f"could not read {path.name}: {exc}") from exc
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise PackValidationError(f"invalid YAML in {path.name}: {exc}") from exc
    if not isinstance(raw, dict):
        raise PackValidationError(f"{path.name} must be a YAML mapping")
    return raw


def _write_materialized_recipe_for_enable(root: Path, manifest: PackManifest) -> None:
    recipe_path = root / RECIPE_NAME
    recipe_raw = _read_yaml_mapping_path(recipe_path)
    materialized = _recipe_raw_with_manifest_variables(recipe_raw, manifest.variables)
    recipe_path.write_text(
        yaml.safe_dump(materialized, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _read_optional_text(archive: ZipFile, name: str) -> str:
    return _read_text(archive, name)


def _read_text(archive: ZipFile, name: str) -> str:
    try:
        data = archive.read(name)
    except KeyError as exc:
        raise PackValidationError(f"pack is missing {name}") from exc
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PackValidationError(f"{name} must be UTF-8 text") from exc


def _validate_zip_layout(infos: list[ZipInfo]) -> set[str]:
    entries: set[str] = set()
    for info in infos:
        name = _normalize_zip_name(info.filename)
        if name in entries and not info.is_dir():
            raise PackValidationError(f"duplicate pack entry: {name}")
        entries.add(name)

        if name == "assets":
            if not info.is_dir():
                raise PackValidationError("assets must be a directory")
            continue
        if name.startswith(ASSETS_PREFIX):
            continue
        if name in {MANIFEST_NAME, RECIPE_NAME, README_NAME}:
            if info.is_dir():
                raise PackValidationError(f"{name} must be a file")
            continue
        raise PackValidationError(f"unexpected top-level pack entry: {name}")
    return entries


def _normalize_zip_name(raw_name: str) -> str:
    if not raw_name:
        raise PackValidationError("zip entry has an empty path")
    if "\\" in raw_name:
        raise PackValidationError(f"zip entry uses backslashes: {raw_name}")
    if raw_name.startswith("/"):
        raise PackValidationError(f"zip entry is absolute: {raw_name}")
    if PureWindowsPath(raw_name).drive:
        raise PackValidationError(f"zip entry is absolute: {raw_name}")
    if "//" in raw_name:
        raise PackValidationError(f"zip entry contains an empty path segment: {raw_name}")

    path = PurePosixPath(raw_name)
    parts = path.parts
    if not parts:
        raise PackValidationError("zip entry has an empty path")
    if any(part in {"", ".", ".."} for part in parts):
        raise PackValidationError(f"zip entry contains path traversal: {raw_name}")
    return "/".join(parts)


def _asset_names(infos: list[ZipInfo]) -> tuple[str, ...]:
    names = []
    for info in infos:
        name = _normalize_zip_name(info.filename)
        if not info.is_dir() and name.startswith(ASSETS_PREFIX):
            names.append(name)
    return tuple(sorted(names))


def _validate_manifest_actions(manifest: PackManifest, registry: ActionRegistry) -> None:
    for action in manifest.required_actions:
        _validate_action_name(action)
        _metadata_for_action(action, registry)


def _validate_recipe_action_policy(actions: list[str], registry: ActionRegistry) -> None:
    for action in actions:
        _validate_action_name(action)
        _metadata_for_action(action, registry)


def _validate_required_action_declarations(
    manifest: PackManifest,
    recipe_actions: list[str],
) -> None:
    declared = set(manifest.required_actions)
    used = set(recipe_actions)
    missing = sorted(used - declared)
    if missing:
        raise PackValidationError(
            "manifest required_actions must include recipe actions: " + ", ".join(missing)
        )


def _validate_required_capabilities(
    manifest: PackManifest,
    registry: ActionRegistry,
) -> None:
    declared = set(manifest.required_capabilities)
    required = {
        capability
        for action in manifest.required_actions
        for capability in registry.metadata(action).required_capabilities
    }
    missing = sorted(required - declared)
    if missing:
        raise PackValidationError(
            "manifest required_capabilities must include action capabilities: "
            + ", ".join(missing)
        )


def _validate_required_condition_capabilities(
    manifest: PackManifest,
    recipe_raw: Mapping[str, Any],
) -> None:
    declared = set(manifest.required_capabilities)
    required = set(_collect_condition_capabilities(recipe_raw))
    missing = sorted(required - declared)
    if missing:
        raise PackValidationError(
            "manifest required_capabilities must include condition capabilities: "
            + ", ".join(missing)
        )


def _validate_supported_os(manifest: PackManifest, registry: ActionRegistry) -> None:
    supported = set(manifest.supported_os)
    for action in manifest.required_actions:
        action_platforms = set(registry.metadata(action).supported_platforms)
        unsupported = sorted(supported - action_platforms)
        if unsupported:
            raise PackValidationError(
                f"manifest supported_os includes OS not supported by {action}: "
                + ", ".join(unsupported)
            )
    for capability in manifest.required_capabilities:
        capability_platforms = set(_supported_os_for_capability(capability))
        unsupported = sorted(supported - capability_platforms)
        if unsupported:
            raise PackValidationError(
                f"manifest supported_os includes OS not supported by {capability}: "
                + ", ".join(unsupported)
            )


def _metadata_for_action(action: str, registry: ActionRegistry):
    try:
        return registry.metadata(action)
    except KeyError as exc:
        raise PackValidationError(f"unknown action in pack: {action}") from exc


def _validate_action_name(action: str) -> None:
    if _is_arbitrary_code_action(action):
        raise PackValidationError(f"arbitrary code actions are not allowed in packs: {action}")
    if _is_coordinate_click_action(action):
        raise PackValidationError(f"coordinate click actions are not allowed in packs: {action}")
    if _is_record_replay_action(action):
        raise PackValidationError(f"record/replay actions are not allowed in packs: {action}")


def _blocked_import_actions(actions: list[str], registry: ActionRegistry) -> list[str]:
    return sorted(
        {
            action
            for action in actions
            if not registry.metadata(action).allowed_in_imported_packs
        }
    )


def _collect_recipe_actions(raw: Mapping[str, Any]) -> list[str]:
    actions: list[str] = []
    for section in ("preflight", "steps", "verify"):
        steps = raw.get(section, [])
        if steps is None:
            continue
        if not isinstance(steps, list):
            continue
        actions.extend(_collect_step_actions(steps, path=section))
    return actions


def _collect_condition_capabilities(raw: Mapping[str, Any]) -> list[str]:
    capabilities: list[str] = []
    for section in ("preflight", "steps", "verify"):
        steps = raw.get(section, [])
        if not isinstance(steps, list):
            continue
        capabilities.extend(_collect_step_condition_capabilities(steps))
    return _unique_preserving_order(capabilities)


def _collect_step_condition_capabilities(steps: list[Any]) -> list[str]:
    capabilities: list[str] = []
    for step in steps:
        if not isinstance(step, Mapping):
            continue
        when = step.get("when")
        if isinstance(when, Mapping):
            capabilities.extend(_condition_capabilities(when))
        condition = step.get("condition")
        if isinstance(condition, Mapping):
            capabilities.extend(_condition_capabilities(condition))
        for child_key in ("then", "else", "on_timeout"):
            children = step.get(child_key)
            if isinstance(children, list):
                capabilities.extend(_collect_step_condition_capabilities(children))
    return capabilities


def _condition_capabilities(condition: Mapping[str, Any]) -> list[str]:
    if isinstance(condition.get("all"), list):
        return [
            capability
            for child in condition["all"]
            if isinstance(child, Mapping)
            for capability in _condition_capabilities(child)
        ]
    if isinstance(condition.get("any"), list):
        return [
            capability
            for child in condition["any"]
            if isinstance(child, Mapping)
            for capability in _condition_capabilities(child)
        ]
    if isinstance(condition.get("not"), Mapping):
        return _condition_capabilities(condition["not"])
    predicate_type = condition.get("type")
    if predicate_type in {"file.exists", "path.exists"}:
        return ["file_read"]
    if predicate_type == "process.running":
        return ["process_inspection"]
    if predicate_type == "window.exists":
        return ["windows_uia", "window_management"]
    if predicate_type == "window.text_visible":
        return ["windows_uia"]
    if predicate_type == "browser.text_visible":
        return ["playwright", "browser_control"]
    return []


def _collect_step_actions(steps: list[Any], *, path: str) -> list[str]:
    actions: list[str] = []
    for index, step in enumerate(steps):
        if not isinstance(step, Mapping):
            continue
        action = step.get("action")
        if action is not None:
            if not isinstance(action, str):
                raise PackValidationError(f"{path}[{index}].action must be a string")
            actions.append(action)
        for child_key in ("then", "else", "on_timeout"):
            children = step.get(child_key)
            if children is None:
                continue
            if not isinstance(children, list):
                continue
            actions.extend(_collect_step_actions(children, path=f"{path}[{index}].{child_key}"))
    return actions


def _recipe_raw_with_manifest_variables(
    raw: dict[str, Any],
    manifest_variables: Mapping[str, Any],
) -> dict[str, Any]:
    variable_defaults = _manifest_variable_defaults(manifest_variables)
    if not variable_defaults:
        return raw

    recipe_variables = raw.get("variables") or {}
    if not isinstance(recipe_variables, dict):
        return raw

    merged = dict(variable_defaults)
    merged.update(recipe_variables)

    merged_raw = dict(raw)
    merged_raw["variables"] = merged
    return merged_raw


def _manifest_variable_defaults(variables: Mapping[str, Any]) -> dict[str, Any]:
    defaults: dict[str, Any] = {}
    for name, value in variables.items():
        default_set = False
        default: Any = None
        if isinstance(value, Mapping):
            if "default" in value:
                default = value["default"]
                default_set = True
            elif "value" in value:
                default = value["value"]
                default_set = True
            elif "validation_default" in value:
                default = value["validation_default"]
                default_set = True
        else:
            default = value
            default_set = True
        if default_set:
            _set_variable_value(defaults, str(name), default)
    return defaults


def _exportable_recipe_raw(
    raw_recipe: Mapping[str, Any],
    *,
    missing_variables: list[str] | tuple[str, ...],
) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = deepcopy(dict(raw_recipe))
    generated_variables: dict[str, Any] = {}
    sanitized_variables: dict[str, Any] = {}
    recipe_variables = raw.get("variables") or {}
    if isinstance(recipe_variables, Mapping):
        sanitized_variables.update(_sanitize_variable_values(recipe_variables))
    for name in missing_variables:
        _set_variable_value(sanitized_variables, name, _validation_default_for_variable(name, None))
    _sanitize_literal_action_values(
        raw,
        sanitized_variables=sanitized_variables,
        generated_variables=generated_variables,
    )
    if sanitized_variables:
        raw["variables"] = sanitized_variables
    else:
        raw.pop("variables", None)
    return raw, generated_variables


def _sanitize_literal_action_values(
    raw: dict[str, Any],
    *,
    sanitized_variables: dict[str, Any],
    generated_variables: dict[str, Any],
) -> None:
    for section in ("preflight", "steps", "verify"):
        steps = raw.get(section)
        if not isinstance(steps, list):
            continue
        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            for key, value in list(step.items()):
                if key == "action":
                    continue
                step[key] = _sanitize_literal_value(
                    value,
                    base_name=f"{section}_{index}_{_safe_variable_part(str(key))}",
                    field_name=str(key),
                    sanitized_variables=sanitized_variables,
                    generated_variables=generated_variables,
                )


def _sanitize_literal_value(
    value: Any,
    *,
    base_name: str,
    field_name: str,
    sanitized_variables: dict[str, Any],
    generated_variables: dict[str, Any],
) -> Any:
    if _should_export_literal_as_variable(field_name, value):
        variable_name = _unique_export_variable_name(base_name, sanitized_variables)
        sanitized_variables[variable_name] = _validation_default_for_variable(
            variable_name,
            value,
        )
        generated_variables[variable_name] = _variable_declaration(variable_name, value)
        return "{{ " + variable_name + " }}"

    if isinstance(value, dict):
        return {
            key: _sanitize_literal_value(
                child,
                base_name=f"{base_name}_{_safe_variable_part(str(key))}",
                field_name=str(key),
                sanitized_variables=sanitized_variables,
                generated_variables=generated_variables,
            )
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [
            _sanitize_literal_value(
                item,
                base_name=f"{base_name}_{index}",
                field_name=field_name,
                sanitized_variables=sanitized_variables,
                generated_variables=generated_variables,
            )
            for index, item in enumerate(value)
        ]
    return value


def _should_export_literal_as_variable(field_name: str, value: Any) -> bool:
    if value is None:
        return False
    normalized_field = field_name.casefold().replace("-", "_")
    if _is_secret_like_field(normalized_field):
        return isinstance(value, str | int | float | bool)
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text or "{{" in text or "}}" in text:
        return False
    return _looks_like_local_path(text)


def _is_secret_like_field(field_name: str) -> bool:
    return any(
        token in field_name
        for token in ("password", "passwd", "secret", "token", "credential", "api_key")
    )


def _looks_like_local_path(value: str) -> bool:
    if re.match(r"^[A-Za-z]:[\\/]", value):
        return True
    if value.startswith(("\\\\", "//", "~", "/")) and not re.match(r"^[a-z]+://", value, re.I):
        return True
    if re.match(r"^%[A-Za-z_][A-Za-z0-9_]*%[\\/]", value):
        return True
    if re.match(r"^\$[A-Za-z_][A-Za-z0-9_]*[\\/]", value):
        return True
    return False


def _unique_export_variable_name(base_name: str, variables: Mapping[str, Any]) -> str:
    name = _safe_variable_part(base_name)
    if name not in variables:
        return name
    index = 2
    while f"{name}_{index}" in variables:
        index += 1
    return f"{name}_{index}"


def _safe_variable_part(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_")
    if not text:
        text = "value"
    if text[0].isdigit():
        text = f"value_{text}"
    return text


def _manifest_variable_declarations(
    raw_recipe: Mapping[str, Any],
    missing_variables: list[str] | tuple[str, ...],
) -> dict[str, Any]:
    declarations: dict[str, Any] = {}
    recipe_variables = raw_recipe.get("variables") or {}
    if isinstance(recipe_variables, Mapping):
        for name, value in recipe_variables.items():
            declarations[str(name)] = _variable_declaration(str(name), value)
    for name in missing_variables:
        declarations.setdefault(str(name), _variable_declaration(str(name), None))
    return declarations


def _sanitize_variable_values(values: Mapping[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for name, value in values.items():
        if isinstance(value, Mapping):
            sanitized[str(name)] = _sanitize_variable_values(value)
        else:
            sanitized[str(name)] = _validation_default_for_variable(str(name), value)
    return sanitized


def _variable_declaration(name: str, value: Any) -> dict[str, Any]:
    return {
        "required": True,
        "type": _variable_type(value),
        "validation_default": _validation_default_for_variable(name, value),
    }


def _variable_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, list):
        return "list"
    if isinstance(value, Mapping):
        return "mapping"
    return "string"


def _validation_default_for_variable(name: str, value: Any) -> Any:
    if isinstance(value, bool):
        return False
    if isinstance(value, int) and not isinstance(value, bool):
        return 1
    if isinstance(value, float):
        return 1.0
    if isinstance(value, list):
        return []
    if isinstance(value, Mapping):
        return _sanitize_variable_values(value)
    safe_name = re.sub(r"[^A-Za-z0-9_]+", "_", name).strip("_") or "value"
    if _looks_like_url_variable(name, value):
        return f"https://example.invalid/ritualist-required/{safe_name}"
    return f"__REQUIRED_{safe_name}__"


def _looks_like_url_variable(name: str, value: Any) -> bool:
    lowered = name.casefold()
    if lowered == "url" or lowered.endswith("_url") or lowered.endswith("-url"):
        return True
    if isinstance(value, str):
        return value.startswith(("http://", "https://"))
    return False


def _set_variable_value(target: dict[str, Any], name: str, value: Any) -> None:
    current = target
    parts = name.split(".")
    for part in parts[:-1]:
        existing = current.get(part)
        if not isinstance(existing, dict):
            existing = {}
            current[part] = existing
        current = existing
    current[parts[-1]] = value


def _supported_os_for_actions(actions: list[str], registry: ActionRegistry) -> list[str]:
    if not actions:
        return list(ALLOWED_PLATFORMS)
    supported = set(registry.metadata(actions[0]).supported_platforms)
    for action in actions[1:]:
        supported &= set(registry.metadata(action).supported_platforms)
    return sorted(supported) if supported else sorted(ALLOWED_PLATFORMS)


def _supported_os_for_capabilities(supported_os: list[str], capabilities: list[str]) -> list[str]:
    supported = set(supported_os)
    for capability in capabilities:
        supported &= set(_supported_os_for_capability(capability))
    return sorted(supported) if supported else supported_os


def _supported_os_for_capability(capability: str) -> list[str]:
    windows_only = {
        "windows_uia",
        "window_management",
        "keyboard_input",
        "registry_read",
        "registry_write",
        "hardware_inventory",
    }
    if capability in windows_only:
        return ["windows"]
    return sorted(ALLOWED_PLATFORMS)


def _unique_preserving_order(values) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value)
        if text in seen:
            continue
        unique.append(text)
        seen.add(text)
    return unique


def _normalize_pack_output_path(out_path: str | Path) -> Path:
    path = Path(out_path)
    if path.suffix.lower() != PACK_EXTENSION:
        raise PackValidationError(f"pack output path must end with {PACK_EXTENSION}")
    return path


def _read_optional_file(path: str | Path, label: str) -> str:
    file_path = Path(path)
    if not file_path.is_file():
        raise PackValidationError(f"{label} path is not a file: {file_path}")
    try:
        return file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise PackValidationError(f"{label} must be UTF-8 text") from exc
    except OSError as exc:
        raise PackValidationError(f"could not read {label} '{file_path}': {exc}") from exc


def _extract_validated_pack(pack_path: Path, root: Path) -> None:
    with ZipFile(pack_path) as archive:
        infos = archive.infolist()
        _validate_zip_layout(infos)
        for info in infos:
            name = _normalize_zip_name(info.filename)
            if info.is_dir():
                (root / name).mkdir(parents=True, exist_ok=True)
                continue
            destination = root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive.read(info.filename))


def _next_import_id(pack_id: str) -> str:
    root = imported_packs_path()
    if not (root / pack_id).exists():
        return pack_id
    index = 2
    while True:
        suffix = f"-{index}"
        candidate = f"{pack_id[:64 - len(suffix)]}{suffix}"
        if not (root / candidate).exists():
            return candidate
        index += 1


def _read_import_record(root: Path) -> ImportedPackRecord:
    path = root / "import.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise PackImportError(f"could not read import record '{path}': {exc}") from exc
    except json.JSONDecodeError as exc:
        raise PackImportError(f"invalid import record '{path}': {exc}") from exc
    if not isinstance(raw, dict):
        raise PackImportError("import record must be a JSON object")
    return ImportedPackRecord.from_dict(root, raw)


def _write_import_record(record: ImportedPackRecord) -> None:
    record.metadata_path.write_text(
        json.dumps(record.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _require_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PackImportError(f"{field_name} must be a non-empty string")
    return value


def _require_safe_id(value: object, field_name: str) -> str:
    text = _require_string(value, field_name)
    if not SAFE_ID_PATTERN.fullmatch(text):
        raise PackImportError(f"{field_name} must be a safe filename-like identifier")
    return text


def _is_arbitrary_code_action(action: str) -> bool:
    return action in ARBITRARY_CODE_ACTIONS or action.startswith(ARBITRARY_CODE_ACTION_PREFIXES)


def _is_coordinate_click_action(action: str) -> bool:
    if action in COORDINATE_CLICK_ACTIONS:
        return True
    return "click" in action and "coordinate" in action


def _is_record_replay_action(action: str) -> bool:
    return action in RECORD_REPLAY_ACTIONS or action.startswith(RECORD_REPLAY_ACTION_PREFIXES)


def _is_safe_variable_name(name: str) -> bool:
    return bool(VARIABLE_NAME_PATTERN.fullmatch(name))


def _require_unique(field_name: str, values: list[str]) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise ValueError(f"{field_name} must not contain duplicates")
        seen.add(value)
