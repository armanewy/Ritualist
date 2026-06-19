from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from platformdirs import user_data_dir, user_log_dir

APP_NAME = "Setpiece"
APP_AUTHOR = "Setpiece"
LEGACY_APP_NAME = "Ritualist"
LEGACY_APP_AUTHOR = "Ritualist"
MIGRATION_MARKER = ".setpiece-legacy-migration.json"

_MIGRATION_ATTEMPTED = False


def app_data_dir() -> Path:
    ensure_legacy_data_migrated()
    path = app_data_path()
    path.mkdir(parents=True, exist_ok=True)
    return path


def app_data_path() -> Path:
    e2e_path = _e2e_app_data_path()
    if e2e_path is not None:
        return e2e_path
    return Path(user_data_dir(APP_NAME, APP_AUTHOR))


def config_dir() -> Path:
    path = config_path()
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    return app_data_path() / "config"


def config_file() -> Path:
    return config_dir() / "config.yaml"


def config_file_path() -> Path:
    return config_path() / "config.yaml"


def recipes_dir() -> Path:
    path = recipes_path()
    path.mkdir(parents=True, exist_ok=True)
    return path


def recipes_path() -> Path:
    return app_data_path() / "recipes"


def imported_packs_dir() -> Path:
    path = imported_packs_path()
    path.mkdir(parents=True, exist_ok=True)
    return path


def imported_packs_path() -> Path:
    return app_data_path() / "imported-packs"


def logs_dir() -> Path:
    ensure_legacy_data_migrated()
    path = logs_path()
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_path() -> Path:
    return Path(user_log_dir(APP_NAME, APP_AUTHOR))


def runs_dir() -> Path:
    path = runs_path()
    path.mkdir(parents=True, exist_ok=True)
    return path


def runs_path() -> Path:
    return app_data_path() / "runs"


def layouts_dir() -> Path:
    path = layouts_path()
    path.mkdir(parents=True, exist_ok=True)
    return path


def layouts_path() -> Path:
    return app_data_path() / "layouts"


def canvases_dir() -> Path:
    path = canvases_path()
    path.mkdir(parents=True, exist_ok=True)
    return path


def canvases_path() -> Path:
    return app_data_path() / "canvases"


def imported_canvas_packs_dir() -> Path:
    path = imported_canvas_packs_path()
    path.mkdir(parents=True, exist_ok=True)
    return path


def imported_canvas_packs_path() -> Path:
    return app_data_path() / "imported-canvas-packs"


def themes_dir() -> Path:
    path = themes_path()
    path.mkdir(parents=True, exist_ok=True)
    return path


def themes_path() -> Path:
    return app_data_path() / "themes"


def imported_theme_packs_dir() -> Path:
    path = imported_theme_packs_path()
    path.mkdir(parents=True, exist_ok=True)
    return path


def imported_theme_packs_path() -> Path:
    return app_data_path() / "imported-theme-packs"


def imported_suite_packs_dir() -> Path:
    path = imported_suite_packs_path()
    path.mkdir(parents=True, exist_ok=True)
    return path


def imported_suite_packs_path() -> Path:
    return app_data_path() / "imported-suite-packs"


def browser_profiles_dir() -> Path:
    path = browser_profiles_path()
    path.mkdir(parents=True, exist_ok=True)
    return path


def browser_profiles_path() -> Path:
    return app_data_path() / "browser-profiles"


def learning_journal_path() -> Path:
    return app_data_path() / "activity-journal.jsonl"


def learning_suggestions_path() -> Path:
    return app_data_path() / "learning-suggestions.jsonl"


def default_log_file() -> Path:
    return logs_dir() / "setpiece.log"


def ensure_app_dirs() -> dict[str, Path]:
    ensure_legacy_data_migrated()
    paths = {
        "app_data": app_data_dir(),
        "config": config_dir(),
        "recipes": recipes_dir(),
        "imported_packs": imported_packs_dir(),
        "logs": logs_dir(),
        "runs": runs_dir(),
        "canvases": canvases_dir(),
        "imported_canvas_packs": imported_canvas_packs_dir(),
        "themes": themes_dir(),
        "imported_theme_packs": imported_theme_packs_dir(),
        "imported_suite_packs": imported_suite_packs_dir(),
        "browser_profiles": browser_profiles_dir(),
    }
    return paths


def legacy_app_data_path() -> Path:
    return Path(user_data_dir(LEGACY_APP_NAME, LEGACY_APP_AUTHOR))


def legacy_logs_path() -> Path:
    return Path(user_log_dir(LEGACY_APP_NAME, LEGACY_APP_AUTHOR))


def ensure_legacy_data_migrated() -> dict[str, object]:
    global _MIGRATION_ATTEMPTED
    if _MIGRATION_ATTEMPTED:
        return {
            "schema_version": "setpiece.legacy_data_migration.v1",
            "status": "already_checked",
            "dry_run": False,
        }
    _MIGRATION_ATTEMPTED = True
    return migrate_legacy_data()


def migrate_legacy_data(
    *,
    dry_run: bool = False,
    legacy_data_root: Path | None = None,
    setpiece_data_root: Path | None = None,
    legacy_log_root: Path | None = None,
    setpiece_log_root: Path | None = None,
) -> dict[str, object]:
    legacy_data = Path(legacy_data_root) if legacy_data_root is not None else legacy_app_data_path()
    canonical_data = Path(setpiece_data_root) if setpiece_data_root is not None else app_data_path()
    legacy_logs = Path(legacy_log_root) if legacy_log_root is not None else legacy_logs_path()
    canonical_logs = Path(setpiece_log_root) if setpiece_log_root is not None else logs_path()

    report: dict[str, object] = {
        "schema_version": "setpiece.legacy_data_migration.v1",
        "dry_run": dry_run,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "legacy_data_root": str(legacy_data),
        "setpiece_data_root": str(canonical_data),
        "legacy_log_root": str(legacy_logs),
        "setpiece_log_root": str(canonical_logs),
        "status": "not_needed",
        "operations": [],
        "errors": [],
    }
    operations: list[dict[str, str]] = []
    errors: list[str] = []
    report["operations"] = operations
    report["errors"] = errors

    _copy_missing_tree(
        legacy_data,
        canonical_data,
        label="app_data",
        dry_run=dry_run,
        operations=operations,
        errors=errors,
    )
    _copy_missing_tree(
        legacy_logs,
        canonical_logs,
        label="logs",
        dry_run=dry_run,
        operations=operations,
        errors=errors,
    )

    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    if errors:
        report["status"] = "failed"
    elif operations:
        report["status"] = "migrated" if not dry_run else "would_migrate"
    else:
        report["status"] = "not_needed"

    if not dry_run and (operations or canonical_data.exists()):
        _write_migration_marker(canonical_data, report)
    return report


def _copy_missing_tree(
    source: Path,
    destination: Path,
    *,
    label: str,
    dry_run: bool,
    operations: list[dict[str, str]],
    errors: list[str],
) -> None:
    if not source.exists():
        return
    try:
        if source.is_file():
            _copy_missing_file(source, destination, label=label, dry_run=dry_run, operations=operations)
            return
        for path in sorted(source.rglob("*")):
            if path.is_dir():
                continue
            relative = path.relative_to(source)
            _copy_missing_file(
                path,
                destination / relative,
                label=label,
                dry_run=dry_run,
                operations=operations,
            )
    except OSError as exc:
        errors.append(f"{label} migration failed: {exc}")


def _copy_missing_file(
    source: Path,
    destination: Path,
    *,
    label: str,
    dry_run: bool,
    operations: list[dict[str, str]],
) -> None:
    operation = {
        "operation": "copy_missing",
        "label": label,
        "source": str(source),
        "destination": str(destination),
    }
    if destination.exists():
        operation["status"] = "skipped_existing_setpiece_authoritative"
        operations.append(operation)
        return
    operation["status"] = "planned" if dry_run else "copied"
    operations.append(operation)
    if dry_run:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _write_migration_marker(root: Path, report: dict[str, object]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    marker = root / MIGRATION_MARKER
    marker.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")


def _e2e_app_data_path() -> Path | None:
    e2e_enabled = os.environ.get("SETPIECE_E2E") == "1"
    legacy_e2e_enabled = os.environ.get("RITUALIST_E2E") == "1"
    if not e2e_enabled and not legacy_e2e_enabled:
        return None
    text = os.environ.get("SETPIECE_E2E_APP_DATA_DIR", "").strip()
    if not text and legacy_e2e_enabled:
        text = os.environ.get("RITUALIST_E2E_APP_DATA_DIR", "").strip()
    if not text:
        return None
    return Path(text)
