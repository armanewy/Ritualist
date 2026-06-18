from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable

from ritualist.paths import learning_suggestions_path

from .models import SUGGESTION_SCHEMA_VERSION, Suggestion, SuggestionStatus


SUGGESTION_STORAGE_SCHEMA_VERSION = "ritualist.suggestions.storage.v1"
MAX_STORED_SUGGESTIONS = 1000


@dataclass(frozen=True)
class SuggestionStore:
    path: Path | None = None

    @property
    def resolved_path(self) -> Path:
        return self.path or learning_suggestions_path()

    def list(self, *, include_corrupt: bool = False) -> list[Suggestion]:
        del include_corrupt
        return _read_suggestions(self.resolved_path)

    def get(self, suggestion_id: str) -> Suggestion | None:
        for suggestion in self.list():
            if suggestion.id == suggestion_id:
                return suggestion
        return None

    def save(self, suggestion: Suggestion) -> Suggestion:
        suggestions = [item for item in self.list() if item.id != suggestion.id]
        suggestions.append(suggestion)
        _write_suggestions(self.resolved_path, suggestions[-MAX_STORED_SUGGESTIONS:])
        return suggestion

    def save_many(self, suggestions: Iterable[Suggestion]) -> list[Suggestion]:
        existing = {item.id: item for item in self.list()}
        for suggestion in suggestions:
            existing[suggestion.id] = suggestion
        ordered = list(existing.values())[-MAX_STORED_SUGGESTIONS:]
        _write_suggestions(self.resolved_path, ordered)
        return ordered

    def update_status(
        self,
        suggestion_id: str,
        status: SuggestionStatus | str,
    ) -> Suggestion | None:
        current = self.get(suggestion_id)
        if current is None:
            return None
        updated = current.with_status(status)
        self.save(updated)
        return updated

    def dismiss(self, suggestion_id: str) -> Suggestion | None:
        return self.update_status(suggestion_id, SuggestionStatus.DISMISSED)

    def delete_all(self) -> bool:
        try:
            self.resolved_path.unlink(missing_ok=True)
        except OSError:
            return False
        return True


def _read_suggestions(path: Path) -> list[Suggestion]:
    if not path.exists():
        return []
    suggestions: list[Suggestion] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                suggestion = _parse_line(line)
                if suggestion is not None:
                    suggestions.append(suggestion)
    except OSError:
        return []
    return suggestions[-MAX_STORED_SUGGESTIONS:]


def _write_suggestions(path: Path, suggestions: Iterable[Suggestion]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        json.dumps(_storage_record(suggestion), ensure_ascii=False, sort_keys=True)
        for suggestion in suggestions
    ]
    path.write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")


def _parse_line(line: str) -> Suggestion | None:
    if not line.strip():
        return None
    try:
        raw = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, dict):
        return None
    if raw.get("schema_version") == SUGGESTION_STORAGE_SCHEMA_VERSION:
        raw_suggestion = raw.get("suggestion")
        if not isinstance(raw_suggestion, dict):
            return None
        raw = raw_suggestion
    if raw.get("schema_version") not in {None, SUGGESTION_SCHEMA_VERSION}:
        return None
    try:
        return Suggestion.from_mapping(raw)
    except (TypeError, ValueError):
        return None


def _storage_record(suggestion: Suggestion) -> dict[str, object]:
    return {
        "schema_version": SUGGESTION_STORAGE_SCHEMA_VERSION,
        "suggestion": suggestion.to_dict(),
    }


__all__ = [
    "MAX_STORED_SUGGESTIONS",
    "SUGGESTION_STORAGE_SCHEMA_VERSION",
    "SuggestionStore",
]
