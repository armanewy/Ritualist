from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import shutil
from typing import Any, Mapping, Sequence

import yaml

from .activity_journal import read_journal
from .activity_signals import (
    ActivityCollectionResult,
    ActivityWarning,
)
from .config import load_app_config
from .errors import SetpieceError
from .learning_config import LEARNING_CONSENT_VERSION, LearningConsentRecord, LocalLearningConfig
from .learning_sources import (
    get_learning_source,
    is_forbidden_learning_source,
    learning_source_registry,
    normalize_learning_source_id,
)
from .local_activity_scan import LocalActivityScanRequest, scan_local_activity
from .paths import config_file_path, learning_journal_path, learning_suggestions_path, recipes_path


LEARNING_STATUS_SCHEMA_VERSION = "setpiece.learning.status.v1"
LEARNING_SOURCES_SCHEMA_VERSION = "setpiece.learning.sources.v1"
LEARNING_SCAN_SCHEMA_VERSION = "setpiece.learning.scan.v1"
LEARNING_JOURNAL_SCHEMA_VERSION = "setpiece.learning.journal.v1"
LEARNING_DELETE_SCHEMA_VERSION = "setpiece.learning.delete_data.v1"

LOCAL_ONLY_EXPLANATION = (
    "Local Learning stays on this device, uses only explicitly selected sources, "
    "and does not start background collection."
)
FORBIDDEN_CAPABILITY_SUMMARY = (
    "No Watch Me, recording, screenshots, OCR, keylogging, coordinate capture, "
    "browser-history collection, cloud sync, remote execution, or auto-run behavior."
)


class LearningServiceError(SetpieceError):
    """Raised for user-facing Local Learning lifecycle errors."""


def learning_status_payload(*, config_path: Path | None = None) -> dict[str, object]:
    config = load_app_config(config_path)
    return _status_payload(config.learning, config_path=config_path)


def learning_sources_payload(*, config_path: Path | None = None) -> dict[str, object]:
    config = load_app_config(config_path)
    enabled = set(config.learning.enabled_source_ids)
    selected = set(config.learning.source_ids)
    consented = set(config.learning.consent.source_ids if config.learning.consent else ())
    sources: list[dict[str, object]] = []
    for source in learning_source_registry().values():
        sources.append(
            {
                "id": source.id,
                "label": source.label,
                "description": source.description,
                "selected": source.id in selected,
                "consented": source.id in consented,
                "enabled": source.id in enabled,
                "enabled_by_default": source.enabled_by_default,
                "requires_explicit_selection": True,
                "background_collection": False,
            }
        )
    return {
        "schema_version": LEARNING_SOURCES_SCHEMA_VERSION,
        "local_only": True,
        "background_collection": False,
        "sources": sources,
    }


def enable_learning(
    source_ids: Sequence[str],
    *,
    config_path: Path | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    selected = _resolve_selected_sources(source_ids)
    timestamp = _utc_timestamp(now)
    learning = LocalLearningConfig(
        enabled=True,
        source_ids=selected,
        consent=LearningConsentRecord(
            timestamp=timestamp,
            version=LEARNING_CONSENT_VERSION,
            source_ids=selected,
        ),
        background_collection=False,
    )
    _update_learning_config(learning, config_path=config_path)
    payload = _status_payload(learning, config_path=config_path)
    payload["message"] = "Local Learning enabled."
    return payload


def disable_learning(*, config_path: Path | None = None) -> dict[str, object]:
    config = load_app_config(config_path)
    learning = LocalLearningConfig(
        enabled=False,
        source_ids=config.learning.source_ids,
        consent=config.learning.consent,
        background_collection=False,
    )
    _update_learning_config(learning, config_path=config_path)
    payload = _status_payload(learning, config_path=config_path)
    payload["message"] = "Local Learning disabled. Existing local learning data was preserved."
    return payload


def learning_scan_payload(
    *,
    config_path: Path | None = None,
    collectors: Sequence[object] | None = None,
    max_signals: int = 50,
) -> dict[str, object]:
    config = load_app_config(config_path)
    enabled_sources = config.learning.enabled_source_ids

    if not config.learning.effective_enabled:
        result = ActivityCollectionResult(
            collector_id="activity_collection",
            supported=False,
            warnings=(
                ActivityWarning(
                    code="local_learning_disabled",
                    message="Local Learning is disabled or missing source-level consent.",
                ),
            ),
        )
    elif not enabled_sources:
        result = ActivityCollectionResult(
            collector_id="activity_collection",
            supported=False,
            warnings=(
                ActivityWarning(
                    code="no_learning_sources_enabled",
                    message="No Local Learning sources are enabled.",
                ),
            ),
        )
    else:
        result = scan_local_activity(
            LocalActivityScanRequest(
                source_ids=enabled_sources,
                max_signals=max_signals,
                max_recent_items=max_signals,
                recent_item_roots=(recipes_path(),),
                include_default_windows_recent=False,
                journal_path=learning_journal_path(),
            ),
            collectors=collectors,
        )

    return {
        "schema_version": LEARNING_SCAN_SCHEMA_VERSION,
        "on_demand": True,
        "background_collection": False,
        "enabled_sources": list(enabled_sources),
        "collection": result.to_dict(),
    }


def learning_journal_payload(*, limit: int = 100) -> dict[str, object]:
    path = learning_journal_path()
    events = read_journal(path, limit=limit)
    return {
        "schema_version": LEARNING_JOURNAL_SCHEMA_VERSION,
        "path": str(path),
        "count": len(events),
        "events": [
            {
                "event_type": event.event_type,
                "payload": event.payload,
            }
            for event in events
        ],
    }


def delete_learning_data() -> dict[str, object]:
    paths = {
        "journal": learning_journal_path(),
        "suggestions": learning_suggestions_path(),
    }
    results = {name: _delete_data_path(path) for name, path in paths.items()}
    return {
        "schema_version": LEARNING_DELETE_SCHEMA_VERSION,
        "deleted_count": sum(1 for item in results.values() if item["deleted"] is True),
        "paths": results,
    }


def _status_payload(
    learning: LocalLearningConfig,
    *,
    config_path: Path | None,
) -> dict[str, object]:
    consent = learning.consent
    data_paths = {
        "journal": learning_journal_path(),
        "suggestions": learning_suggestions_path(),
    }
    return {
        "schema_version": LEARNING_STATUS_SCHEMA_VERSION,
        "enabled": learning.enabled,
        "effective_enabled": learning.effective_enabled,
        "selected_sources": list(learning.source_ids),
        "enabled_sources": list(learning.enabled_source_ids),
        "consented_sources": list(consent.source_ids if consent else ()),
        "consent_version": consent.version if consent else "",
        "consent_timestamp": consent.timestamp if consent else "",
        "local_only": True,
        "background_collection": False,
        "config_path": str(config_path or config_file_path()),
        "data_paths": {
            name: {
                "path": str(path),
                "exists": path.exists(),
            }
            for name, path in data_paths.items()
        },
        "local_only_explanation": LOCAL_ONLY_EXPLANATION,
        "forbidden_capability_summary": FORBIDDEN_CAPABILITY_SUMMARY,
    }


def _resolve_selected_sources(source_ids: Sequence[str]) -> tuple[str, ...]:
    if not source_ids:
        raise LearningServiceError(
            "enable requires explicit source selection, for example "
            "--source setpiece_journal."
        )

    selected: list[str] = []
    seen: set[str] = set()
    invalid: list[str] = []
    forbidden: list[str] = []
    for source_id in source_ids:
        normalized = normalize_learning_source_id(source_id)
        if not normalized:
            invalid.append(str(source_id))
            continue
        if is_forbidden_learning_source(normalized):
            forbidden.append(str(source_id))
            continue
        source = get_learning_source(normalized)
        if source is None:
            invalid.append(str(source_id))
            continue
        if source.id in seen:
            continue
        seen.add(source.id)
        selected.append(source.id)

    if forbidden:
        raise LearningServiceError(
            "forbidden Local Learning source requested: " + ", ".join(forbidden)
        )
    if invalid:
        raise LearningServiceError(
            "unsupported Local Learning source requested: " + ", ".join(invalid)
        )
    if not selected:
        raise LearningServiceError("enable requires at least one supported Local Learning source.")
    return tuple(selected)


def _update_learning_config(
    learning: LocalLearningConfig,
    *,
    config_path: Path | None,
) -> None:
    path = config_path or config_file_path()
    raw = _read_config_mapping(path)
    raw["learning"] = learning.to_dict()
    _write_config_mapping(path, raw)


def _read_config_mapping(path: Path) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except yaml.YAMLError as exc:
        raise LearningServiceError(f"cannot update Local Learning config: invalid YAML ({exc})") from exc
    except OSError as exc:
        raise LearningServiceError(f"cannot read Local Learning config: {exc}") from exc
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        return {}
    return dict(raw)


def _write_config_mapping(path: Path, raw: Mapping[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(dict(raw), sort_keys=False, allow_unicode=False),
            encoding="utf-8",
        )
    except OSError as exc:
        raise LearningServiceError(f"cannot write Local Learning config: {exc}") from exc


def _delete_data_path(path: Path) -> dict[str, object]:
    existed = path.exists()
    deleted = False
    error = ""
    if existed:
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            deleted = True
        except OSError as exc:
            error = str(exc)
    return {
        "path": str(path),
        "existed": existed,
        "deleted": deleted,
        "error": error,
    }


def _utc_timestamp(now: datetime | None) -> str:
    resolved = now or datetime.now(timezone.utc)
    if resolved.tzinfo is None:
        resolved = resolved.replace(tzinfo=timezone.utc)
    return resolved.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
