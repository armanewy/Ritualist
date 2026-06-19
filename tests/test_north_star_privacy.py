from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

import pytest
import yaml

from setpiece.actions.registry import create_default_registry
from setpiece.config import load_app_config
from setpiece.learning_config import LocalLearningConfig
from setpiece.learning_service import (
    delete_learning_data,
    enable_learning,
    learning_sources_payload,
)
from setpiece.learning_sources import (
    ALLOWED_LEARNING_SOURCE_IDS,
    get_learning_source,
    is_forbidden_learning_source,
    learning_source_registry,
)
from setpiece.packs import PACK_SCHEMA_V1, PackValidationError, import_pack, validate_pack
from setpiece.rooms import list_rooms
from setpiece.suggestions.drafts_recipe import build_draft_recipe
from setpiece.suggestions.models import Suggestion, SuggestionStatus
from setpiece.suggestions.review import (
    approve_suggestion,
    can_create_draft,
    require_approval_for_draft,
    SuggestionReviewRequiredError,
)
from setpiece.suggestions.service import scan_suggestions_payload
from setpiece.suggestions.storage import SuggestionStore


REVIEWED_AT = "2026-06-18T10:11:12Z"
SAFETY = {
    "no_arbitrary_code": True,
    "no_coordinate_clicks": True,
    "no_remote_execution": True,
    "imported_recipes_must_not_run_automatically": True,
}


def test_privacy_contract_keeps_exactly_three_promoted_hero_rooms() -> None:
    rooms = list_rooms()

    assert [room.name for room in rooms] == [
        "Gaming Room",
        "Project Room",
        "Support Desk",
    ]
    assert [room.room_id for room in rooms] == ["gaming", "project", "support_desk"]


def test_no_watch_me_recording_or_replay_surfaces_are_registered() -> None:
    registry = create_default_registry()
    forbidden_terms = (
        "watch_me",
        "watch-me",
        "watch me",
        "recording",
        "recorder",
        "record/replay",
        "replay",
        "macro",
        "teach by watching",
    )

    for action_type in registry.action_types():
        metadata_text = json.dumps(
            registry.metadata(action_type).to_dict(),
            sort_keys=True,
        ).casefold()
        assert all(term not in action_type.casefold() for term in forbidden_terms)
        assert all(term not in metadata_text for term in forbidden_terms)


def test_learning_registry_excludes_history_capture_screenshot_ocr_and_keystroke_sources() -> None:
    registry = learning_source_registry()

    assert tuple(registry) == ALLOWED_LEARNING_SOURCE_IDS
    assert tuple(registry) == ("setpiece_journal", "open_windows", "recent_items")
    assert all(source.enabled_by_default is False for source in registry.values())
    assert all(source.background_collection is False for source in registry.values())

    forbidden_sources = (
        "watch_me",
        "watch-me",
        "teach_by_watching",
        "browser_history",
        "browser history",
        "history",
        "windows_recall",
        "recall",
        "screenshots",
        "screenshot",
        "screen_capture",
        "ocr",
        "screen_recording",
        "recording",
        "keystrokes",
        "keylogging",
        "coordinate_capture",
        "click_coordinates",
    )
    for source_id in forbidden_sources:
        assert get_learning_source(source_id) is None
        assert is_forbidden_learning_source(source_id) is True


def test_learning_sources_payload_is_local_opt_in_and_has_no_browser_history_source(
    tmp_path: Path,
) -> None:
    payload = learning_sources_payload(config_path=tmp_path / "config.yaml")

    assert payload["local_only"] is True
    assert payload["background_collection"] is False
    assert [source["id"] for source in payload["sources"]] == [
        "setpiece_journal",
        "open_windows",
        "recent_items",
    ]
    assert all(source["requires_explicit_selection"] is True for source in payload["sources"])
    assert all(source["enabled_by_default"] is False for source in payload["sources"])
    assert "history" not in json.dumps(payload, sort_keys=True).casefold()


def test_suggestion_storage_does_not_persist_raw_urls_history_or_capture_fields(
    tmp_path: Path,
) -> None:
    store_path = tmp_path / "suggestions.jsonl"
    store = SuggestionStore(path=store_path)
    suggestion = Suggestion.create(
        kind="ritual_recipe",
        title="Review https://secret.example/customer-a?token=abc",
        description="Use repeated docs from https://secret.example/private",
        confidence=0.8,
        evidence_summary={
            "url": "https://secret.example/customer-a?token=abc",
            "window_title": "Project Room",
            "browser_history": ["https://secret.example/raw"],
            "screenshot": "pixels",
            "ocr_text": "private text",
            "keystrokes": "hunter2",
        },
        evidence_count=3,
        sources=("recent_items", "browser_history", "screenshots", "open_windows"),
        proposed_actions=(
            {
                "action": "review_ritual_recipe",
                "kind": "ritual_recipe",
                "label": "Review project ritual",
                "url": "https://secret.example/customer-a?token=abc",
                "raw_history": ["https://secret.example/raw"],
                "screenshot_path": "C:/Users/alice/screen.png",
                "ocr": "private text",
                "keystrokes": "abc",
                "command": "powershell -nop",
            },
        ),
    )

    saved = store.save(suggestion)
    stored_text = store_path.read_text(encoding="utf-8")

    assert saved.sources == ("recent_items", "open_windows")
    assert "https://secret.example" not in stored_text
    assert "customer-a" not in stored_text
    assert "token=abc" not in stored_text
    assert "raw_history" not in stored_text
    assert "browser_history" not in stored_text
    assert "screenshot" not in stored_text
    assert "ocr" not in stored_text
    assert "keystrokes" not in stored_text
    assert "powershell" not in stored_text


def test_imported_packs_cannot_enable_learning_or_run_on_import(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "config.yaml"
    imported_root = tmp_path / "imported-packs"
    recipes_root = tmp_path / "recipes"
    monkeypatch.setattr("setpiece.packs.imported_packs_path", lambda: imported_root)
    monkeypatch.setattr(
        "setpiece.packs.imported_packs_dir",
        lambda: imported_root.mkdir(parents=True, exist_ok=True) or imported_root,
    )
    monkeypatch.setattr(
        "setpiece.packs.recipes_dir",
        lambda: recipes_root.mkdir(parents=True, exist_ok=True) or recipes_root,
    )
    config_path.write_text(
        yaml.safe_dump({"learning": LocalLearningConfig().to_dict()}),
        encoding="utf-8",
    )
    pack_path = _write_pack(tmp_path, manifest=_manifest(), recipe=_recipe())

    record = import_pack(pack_path)
    config = load_app_config(config_path)

    assert record.status == "disabled"
    assert record.to_dict().get("auto_run") is None
    assert config.learning.effective_enabled is False
    assert not (recipes_root / "demo_recipe.yaml").exists()


def test_pack_manifest_cannot_smuggle_learning_or_arbitrary_code(
    tmp_path: Path,
) -> None:
    learning_manifest = {**_manifest(), "learning": {"enabled": True}}
    learning_pack = _write_pack(tmp_path, manifest=learning_manifest, recipe=_recipe())

    with pytest.raises(PackValidationError):
        validate_pack(learning_pack)

    code_pack = _write_pack(
        tmp_path,
        manifest=_manifest(required_actions=["shell.run"]),
        recipe={
            "version": "0.1",
            "id": "demo_recipe",
            "name": "Demo",
            "steps": [{"action": "shell.run", "command": "echo unsafe"}],
        },
        name="code.setpiecepack",
    )

    with pytest.raises(PackValidationError, match="arbitrary code actions"):
        validate_pack(code_pack)


def test_suggestions_are_review_only_and_never_auto_run_or_auto_create(
    tmp_path: Path,
) -> None:
    store = SuggestionStore(path=tmp_path / "suggestions.jsonl")
    config_path = tmp_path / "config.yaml"
    enable_learning(
        ["recent_items"],
        config_path=config_path,
        now=None,
    )
    collectors = (
        _StaticCollector(
            "recent_items",
            signals=[
                {
                    "kind": "recent_reference",
                    "source_id": "recent_items",
                    "label": "Project",
                    "value": "Project",
                    "metadata": {"reference_type": "folder", "target": "Project"},
                },
                {
                    "kind": "recent_reference",
                    "source_id": "recent_items",
                    "label": "Project",
                    "value": "Project",
                    "metadata": {"reference_type": "folder", "target": "Project"},
                },
            ],
        ),
    )

    payload = scan_suggestions_payload(
        store=store,
        config_path=config_path,
        collectors=collectors,
    )

    assert payload["on_demand"] is True
    assert payload["background_collection"] is False
    assert payload["persisted"] is True
    assert payload["persisted_count"] == 1
    assert payload["suggestions"][0]["status"] == SuggestionStatus.NEW.value
    assert payload["suggestions"][0]["drafted_artifact_ref"] == ""
    assert payload["suggestions"][0]["proposed_actions"][0]["action"].startswith("review_")
    assert store.list()[0].status is SuggestionStatus.NEW


def test_drafts_require_review_and_remain_disabled_after_creation(
    tmp_path: Path,
) -> None:
    store = SuggestionStore(path=tmp_path / "suggestions.jsonl")
    suggestion = store.save(_recipe_suggestion())

    assert can_create_draft(suggestion) is False
    with pytest.raises(SuggestionReviewRequiredError):
        require_approval_for_draft(suggestion)
    with pytest.raises(SuggestionReviewRequiredError):
        build_draft_recipe(suggestion)

    approved = approve_suggestion(
        store,
        suggestion.id,
        reviewed_by="operator",
        reviewed_at=REVIEWED_AT,
    )
    draft = build_draft_recipe(approved)

    assert draft["status"] == "disabled"
    assert draft["requires_doctor_before_enable"] is True
    assert draft["creation_side_effects"] == {
        "installed": False,
        "enabled": False,
        "ran": False,
        "wrote_files": False,
    }
    assert store.get(suggestion.id).status is SuggestionStatus.APPROVED
    assert {child.name for child in tmp_path.iterdir()} == {"suggestions.jsonl"}


def test_learning_data_deletion_removes_journal_and_suggestions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journal = tmp_path / "activity-journal.jsonl"
    suggestions = tmp_path / "learning-suggestions.jsonl"
    journal.write_text('{"event_type":"room_opened"}\n', encoding="utf-8")
    suggestions.write_text('{"suggestion":{}}\n', encoding="utf-8")
    monkeypatch.setattr("setpiece.learning_service.learning_journal_path", lambda: journal)
    monkeypatch.setattr(
        "setpiece.learning_service.learning_suggestions_path",
        lambda: suggestions,
    )

    payload = delete_learning_data()

    assert payload["deleted_count"] == 2
    assert payload["paths"]["journal"]["deleted"] is True
    assert payload["paths"]["suggestions"]["deleted"] is True
    assert not journal.exists()
    assert not suggestions.exists()


class _StaticCollector:
    def __init__(self, collector_id: str, signals: list[dict[str, object]]) -> None:
        self.collector_id = collector_id
        self.signals = signals

    def collect(self, *, context=None):
        del context
        from setpiece.activity_signals import ActivityCollectionResult, ActivitySignal

        return ActivityCollectionResult(
            collector_id=self.collector_id,
            signals=tuple(ActivitySignal(**signal) for signal in self.signals),
        )


def _recipe_suggestion() -> Suggestion:
    return Suggestion.create(
        kind="ritual_recipe",
        title="Project setup",
        description="Review-only recipe draft suggestion",
        confidence=0.8,
        evidence_summary="Repeated project setup pattern",
        evidence_count=3,
        sources=("setpiece_journal", "recent_items"),
        proposed_actions=(
            {
                "action": "review_ritual_recipe",
                "kind": "ritual_recipe",
                "title": "Project setup",
                "recipe_id": "project_setup",
            },
        ),
        missing_inputs=("recipe_review",),
    )


def _manifest(
    *,
    required_actions: list[str] | None = None,
    required_capabilities: list[str] | None = None,
) -> dict[str, object]:
    return {
        "schema": PACK_SCHEMA_V1,
        "id": "demo_pack",
        "name": "Demo Pack",
        "version": "1.0.0",
        "required_setpiece_version": ">=0.1.0-alpha.1",
        "supported_os": ["windows", "macos", "linux"],
        "required_capabilities": required_capabilities or [],
        "required_actions": required_actions or ["wait.seconds"],
        "variables": {},
        "safety": dict(SAFETY),
    }


def _recipe() -> dict[str, object]:
    return {
        "version": "0.1",
        "id": "demo_recipe",
        "name": "Demo",
        "steps": [{"action": "wait.seconds", "seconds": 0.1}],
    }


def _write_pack(
    tmp_path: Path,
    *,
    manifest: dict[str, object],
    recipe: dict[str, object],
    name: str = "demo.setpiecepack",
) -> Path:
    path = tmp_path / name
    with ZipFile(path, "w") as archive:
        archive.writestr("manifest.yaml", yaml.safe_dump(manifest, sort_keys=False))
        archive.writestr("recipe.yaml", yaml.safe_dump(recipe, sort_keys=False))
    return path
