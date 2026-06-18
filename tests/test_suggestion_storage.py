from __future__ import annotations

import json

from ritualist.suggestions.models import Suggestion, SuggestionStatus
from ritualist.suggestions.storage import SuggestionStore


def _suggestion(title: str = "Open Project") -> Suggestion:
    return Suggestion.create(
        kind="shortcut_component",
        title=title,
        description="Review-only shortcut suggestion",
        confidence=0.8,
        evidence_summary="Repeated folder use",
        evidence_count=3,
        sources=("recent_items",),
        proposed_actions=({"kind": "shortcut.folder", "label": title},),
    )


def test_suggestion_store_saves_lists_and_replaces_by_id(tmp_path) -> None:
    store = SuggestionStore(path=tmp_path / "suggestions.jsonl")
    suggestion = _suggestion()

    store.save(suggestion)
    store.save(suggestion.with_status(SuggestionStatus.REVIEWING))

    rows = store.list()
    assert len(rows) == 1
    assert rows[0].id == suggestion.id
    assert rows[0].status is SuggestionStatus.REVIEWING


def test_suggestion_store_handles_corrupted_storage_safely(tmp_path) -> None:
    path = tmp_path / "suggestions.jsonl"
    suggestion = _suggestion("Docs")
    path.write_text(
        "\n".join(
            (
                "{not-json}",
                json.dumps({"schema_version": "other", "suggestion": suggestion.to_dict()}),
                json.dumps({"schema_version": "ritualist.suggestions.storage.v1"}),
                json.dumps(
                    {
                        "schema_version": "ritualist.suggestions.storage.v1",
                        "suggestion": suggestion.to_dict(),
                    }
                ),
            )
        ),
        encoding="utf-8",
    )

    rows = SuggestionStore(path=path).list()

    assert rows == [suggestion]


def test_dismissed_status_persists(tmp_path) -> None:
    path = tmp_path / "suggestions.jsonl"
    store = SuggestionStore(path=path)
    suggestion = store.save(_suggestion())

    dismissed = store.dismiss(suggestion.id)
    restored = SuggestionStore(path=path).get(suggestion.id)

    assert dismissed is not None
    assert dismissed.status is SuggestionStatus.DISMISSED
    assert restored is not None
    assert restored.status is SuggestionStatus.DISMISSED


def test_suggestion_storage_does_not_persist_raw_history_or_code_fields(tmp_path) -> None:
    store = SuggestionStore(path=tmp_path / "suggestions.jsonl")
    suggestion = Suggestion.create(
        kind="ritual_recipe",
        title="Setup https://secret.example/private",
        description="Cluster C:/Users/alice/Secret",
        confidence=0.6,
        evidence_summary="Sanitized domain/app/folder labels only; ran powershell",
        evidence_count=5,
        sources=("open_windows", "recent_items"),
        proposed_actions=(
            {
                "label": "Setup https://secret.example/private",
                "description": "Use C:/Users/alice/Secret",
                "raw_history": ["https://secret.example/private"],
                "url": "https://secret.example/private",
                "path": "C:/Users/alice/Secret",
                "code": "print('no')",
                "command": "powershell -nop",
            },
        ),
    )

    store.save(suggestion)
    text = (tmp_path / "suggestions.jsonl").read_text(encoding="utf-8")

    assert "raw_history" not in text
    assert "\"url\"" not in text
    assert "\"path\"" not in text
    assert "secret.example/private" not in text
    assert "C:/Users/alice" not in text
    assert "print" not in text
    assert "powershell" not in text


def test_delete_all_is_idempotent(tmp_path) -> None:
    store = SuggestionStore(path=tmp_path / "suggestions.jsonl")
    store.save(_suggestion())

    assert store.delete_all() is True
    assert store.list() == []
    assert store.delete_all() is True
