from __future__ import annotations

from pathlib import Path
from typing import Sequence

from ritualist.config import load_app_config
from ritualist.errors import RitualistError
from ritualist.learning_service import learning_scan_payload
from ritualist.suggestions.miner import mine_suggestions
from ritualist.suggestions.models import Suggestion, SuggestionPrivacyLevel
from ritualist.suggestions.storage import SuggestionStore


SUGGESTIONS_SCAN_SCHEMA_VERSION = "ritualist.suggestions.scan.v1"
SUGGESTIONS_LIST_SCHEMA_VERSION = "ritualist.suggestions.list.v1"
SUGGESTIONS_SHOW_SCHEMA_VERSION = "ritualist.suggestions.show.v1"
SUGGESTIONS_DISMISS_SCHEMA_VERSION = "ritualist.suggestions.dismiss.v1"
SUGGESTIONS_DELETE_ALL_SCHEMA_VERSION = "ritualist.suggestions.delete_all.v1"


class SuggestionsServiceError(RitualistError):
    """Raised for user-facing suggestion service errors."""


def scan_suggestions_payload(
    *,
    dry_run: bool = False,
    min_confidence: float = 0.0,
    include_sensitive: bool = False,
    max_signals: int = 50,
    store: SuggestionStore | None = None,
    config_path: Path | None = None,
    collectors: Sequence[object] | None = None,
) -> dict[str, object]:
    """Run one on-demand Local Learning scan and optionally persist suggestions."""

    _require_learning_enabled(config_path=config_path)
    storage = store or SuggestionStore()
    scan = learning_scan_payload(
        config_path=config_path,
        collectors=collectors,
        max_signals=max_signals,
    )
    collection = scan.get("collection") if isinstance(scan.get("collection"), dict) else {}
    signals = collection.get("signals") if isinstance(collection, dict) else []
    signal_rows = signals if isinstance(signals, list) else []
    mined = mine_suggestions(signal_rows)
    suggestions = _filter_suggestions(
        mined,
        min_confidence=min_confidence,
        include_sensitive=include_sensitive,
    )
    persisted_count = 0
    if not dry_run and suggestions:
        storage.save_many(suggestions)
        persisted_count = len(suggestions)

    return {
        "schema_version": SUGGESTIONS_SCAN_SCHEMA_VERSION,
        "on_demand": True,
        "background_collection": False,
        "local_learning_required": True,
        "dry_run": bool(dry_run),
        "persisted": not dry_run,
        "persisted_count": persisted_count,
        "min_confidence": _bounded_confidence_threshold(min_confidence),
        "include_sensitive": bool(include_sensitive),
        "storage_path": str(storage.resolved_path),
        "enabled_sources": list(scan.get("enabled_sources") or []),
        "scanned_signal_count": len(signal_rows),
        "mined_count": len(mined),
        "suggestion_count": len(suggestions),
        "warnings": collection.get("warnings", []) if isinstance(collection, dict) else [],
        "suggestions": [suggestion.to_dict() for suggestion in suggestions],
    }


def list_suggestions_payload(
    *,
    min_confidence: float = 0.0,
    include_sensitive: bool = False,
    store: SuggestionStore | None = None,
    config_path: Path | None = None,
) -> dict[str, object]:
    _require_learning_enabled(config_path=config_path)
    storage = store or SuggestionStore()
    suggestions = _filter_suggestions(
        storage.list(),
        min_confidence=min_confidence,
        include_sensitive=include_sensitive,
    )
    return {
        "schema_version": SUGGESTIONS_LIST_SCHEMA_VERSION,
        "local_learning_required": True,
        "min_confidence": _bounded_confidence_threshold(min_confidence),
        "include_sensitive": bool(include_sensitive),
        "storage_path": str(storage.resolved_path),
        "count": len(suggestions),
        "suggestions": [suggestion.to_dict() for suggestion in suggestions],
    }


def show_suggestion_payload(
    suggestion_id: str,
    *,
    include_sensitive: bool = False,
    store: SuggestionStore | None = None,
    config_path: Path | None = None,
) -> dict[str, object]:
    _require_learning_enabled(config_path=config_path)
    storage = store or SuggestionStore()
    suggestion = storage.get(suggestion_id)
    if suggestion is None:
        raise SuggestionsServiceError(f"suggestion not found: {suggestion_id}")
    if _is_sensitive(suggestion) and not include_sensitive:
        raise SuggestionsServiceError(
            "suggestion is marked sensitive; rerun with --include-sensitive to show it."
        )
    return {
        "schema_version": SUGGESTIONS_SHOW_SCHEMA_VERSION,
        "local_learning_required": True,
        "include_sensitive": bool(include_sensitive),
        "storage_path": str(storage.resolved_path),
        "suggestion": suggestion.to_dict(),
    }


def dismiss_suggestion_payload(
    suggestion_id: str,
    *,
    store: SuggestionStore | None = None,
    config_path: Path | None = None,
) -> dict[str, object]:
    _require_learning_enabled(config_path=config_path)
    storage = store or SuggestionStore()
    suggestion = storage.dismiss(suggestion_id)
    if suggestion is None:
        raise SuggestionsServiceError(f"suggestion not found: {suggestion_id}")
    return {
        "schema_version": SUGGESTIONS_DISMISS_SCHEMA_VERSION,
        "local_learning_required": True,
        "storage_path": str(storage.resolved_path),
        "dismissed": True,
        "suggestion": suggestion.to_dict(),
    }


def delete_all_suggestions_payload(
    *,
    dry_run: bool = False,
    store: SuggestionStore | None = None,
    config_path: Path | None = None,
) -> dict[str, object]:
    _require_learning_enabled(config_path=config_path)
    storage = store or SuggestionStore()
    existing_count = len(storage.list())
    deleted = False
    if not dry_run:
        deleted = storage.delete_all()
    return {
        "schema_version": SUGGESTIONS_DELETE_ALL_SCHEMA_VERSION,
        "local_learning_required": True,
        "storage_path": str(storage.resolved_path),
        "dry_run": bool(dry_run),
        "deleted": deleted,
        "deleted_count": existing_count if deleted else 0,
        "would_delete_count": existing_count,
    }


def _require_learning_enabled(*, config_path: Path | None) -> None:
    learning = load_app_config(config_path).learning
    if not learning.effective_enabled or not learning.enabled_source_ids:
        raise SuggestionsServiceError(
            "Local Learning must be enabled with explicit source consent before "
            "using suggestions."
        )


def _filter_suggestions(
    suggestions: Sequence[Suggestion],
    *,
    min_confidence: float,
    include_sensitive: bool,
) -> list[Suggestion]:
    threshold = _bounded_confidence_threshold(min_confidence)
    return [
        suggestion
        for suggestion in suggestions
        if suggestion.confidence >= threshold
        and (include_sensitive or not _is_sensitive(suggestion))
    ]


def _is_sensitive(suggestion: Suggestion) -> bool:
    return suggestion.privacy_level is SuggestionPrivacyLevel.SENSITIVE


def _bounded_confidence_threshold(value: float) -> float:
    try:
        resolved = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, resolved))


__all__ = [
    "SUGGESTIONS_DELETE_ALL_SCHEMA_VERSION",
    "SUGGESTIONS_DISMISS_SCHEMA_VERSION",
    "SUGGESTIONS_LIST_SCHEMA_VERSION",
    "SUGGESTIONS_SCAN_SCHEMA_VERSION",
    "SUGGESTIONS_SHOW_SCHEMA_VERSION",
    "SuggestionsServiceError",
    "delete_all_suggestions_payload",
    "dismiss_suggestion_payload",
    "list_suggestions_payload",
    "scan_suggestions_payload",
    "show_suggestion_payload",
]
