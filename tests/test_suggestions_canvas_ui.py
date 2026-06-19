from __future__ import annotations

from pathlib import Path

from setpiece.canvas import CanvasSuggestionsReviewBridge
from setpiece.learning_service import enable_learning
from setpiece.suggestions.drafts_room import PROMOTED_HERO_ROOM_IDS
from setpiece.suggestions.models import Suggestion
from setpiece.suggestions.storage import SuggestionStore


def _shortcut_suggestion() -> Suggestion:
    return Suggestion.create(
        kind="shortcut_component",
        title="Project shortcut",
        description="Review a local shortcut component draft.",
        confidence=0.82,
        evidence_summary="Repeated local shortcut use",
        evidence_count=4,
        sources=("setpiece_journal",),
        proposed_actions=(
            {
                "action": "review_shortcut_component",
                "kind": "shortcut.folder",
                "component_type": "shortcut.folder",
                "label": "Project Folder",
            },
        ),
        missing_inputs=("folder_path",),
    )


def _ritual_suggestion() -> Suggestion:
    return Suggestion.create(
        kind="ritual_recipe",
        title="Project kickoff",
        description="Review a disabled recipe draft.",
        confidence=0.74,
        evidence_summary="Repeated recipe pattern",
        evidence_count=3,
        sources=("setpiece_journal",),
        proposed_actions=(
            {
                "action": "review_ritual_recipe",
                "kind": "ritual_recipe",
                "title": "Project kickoff",
                "recipe_id": "project_kickoff",
            },
        ),
        missing_inputs=("project_root",),
    )


def _room_suggestion() -> Suggestion:
    return Suggestion.create(
        kind="room_canvas",
        title="Review Support Desk canvas",
        description="Review a Room draft.",
        confidence=0.7,
        evidence_summary="Repeated support workflow",
        evidence_count=2,
        sources=("setpiece_journal",),
        proposed_actions=(
            {
                "action": "review_room_canvas",
                "kind": "room_canvas",
                "room_id": "support_desk",
                "label": "Support Desk",
            },
        ),
        missing_inputs=("room_review",),
    )


def _bridge(tmp_path: Path) -> CanvasSuggestionsReviewBridge:
    config_path = tmp_path / "config.yaml"
    enable_learning(("setpiece_journal",), config_path=config_path)
    store = SuggestionStore(path=tmp_path / "suggestions.jsonl")
    store.save_many((_shortcut_suggestion(), _ritual_suggestion(), _room_suggestion()))
    return CanvasSuggestionsReviewBridge(store=store, config_path=config_path)


def test_canvas_suggestions_bridge_filters_badges_and_review_gates_drafts(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path)

    model = bridge.model()

    assert model["schema_version"] == "setpiece.canvas.suggestions_review_ui.v1"
    assert [item["id"] for item in model["filters"]] == ["all", "shortcut", "ritual", "room"]
    assert model["count"] == 3
    assert {row["kind_label"] for row in model["suggestions"]} == {"Shortcut", "Ritual", "Room"}
    assert all("Confidence " in row["confidence_badge"] for row in model["suggestions"])
    assert all("Evidence " in row["evidence_badge"] for row in model["suggestions"])
    assert all("Privacy " in row["privacy_badge"] for row in model["suggestions"])
    assert all(row["can_create_draft"] is False for row in model["suggestions"])
    assert model["auto_create"] is False
    assert model["auto_run"] is False

    shortcut_model = bridge.set_filter("shortcut")

    assert shortcut_model["count"] == 1
    shortcut = shortcut_model["suggestions"][0]
    assert shortcut["kind"] == "shortcut_component"

    reviewed = bridge.review_suggestion(shortcut["id"])

    reviewed_shortcut = reviewed["suggestions"][0]
    assert reviewed_shortcut["status"] == "approved"
    assert reviewed_shortcut["can_create_draft"] is True
    assert reviewed["last_draft"] == {}

    drafted = bridge.create_draft(shortcut["id"])

    assert drafted["last_draft"]["created_artifact"] is False
    assert drafted["last_draft"]["wrote_files"] is False
    assert drafted["last_draft"]["ran"] is False
    assert drafted["last_draft"]["draft"]["schema_version"] == "setpiece.shortcut_draft.v1"
    assert drafted["last_draft"]["draft"]["status"] == "needs_setup"
    assert {child.name for child in tmp_path.iterdir()} == {"config.yaml", "suggestions.jsonl"}


def test_canvas_suggestions_bridge_edit_before_create_and_delete_all(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path)
    room = next(row for row in bridge.model()["suggestions"] if row["kind"] == "room_canvas")

    editing = bridge.edit_before_creating(room["id"])

    assert editing["editing_before_create"] is True
    assert editing["selected_suggestion_id"] == room["id"]
    assert editing["last_draft"] == {}

    deleted = bridge.delete_all()

    assert deleted["count"] == 0
    assert deleted["selected_suggestion_id"] == ""
    assert deleted["last_draft"] == {}


def test_canvas_suggestions_review_qml_is_edit_mode_only_and_review_gated() -> None:
    qml = Path("setpiece/canvas/qml/CanvasUse.qml").read_text(encoding="utf-8")
    app = Path("setpiece/canvas/app.py").read_text(encoding="utf-8")

    assert "Suggestions" in qml
    assert "Find Suggestions" in qml
    assert "Review" in qml
    assert "Create Draft" in qml
    assert "Edit Before Creating" in qml
    assert "Dismiss" in qml
    assert "Delete All" in qml
    assert "Delete all stored Suggestions?" in qml
    assert "confidence_badge" in qml
    assert "evidence_badge" in qml
    assert "privacy_badge" in qml
    assert "visible: root.editMode" in qml
    assert "root.canvasController.findSuggestions()" in qml
    assert "root.canvasController.createSuggestionDraft(modelData.id)" in qml
    assert "dispatch(componentId, actionId)" in qml
    assert "suggestionsOperationCompleted" in app
    assert "findSuggestions" in app
    assert "createSuggestionDraft" in app
    assert "deleteAllSuggestions" in app
    assert "def _suggestions_available" in app
    assert app.count("if not self._suggestions_available():") == 7
    assert "Switch to Edit Mode to review Suggestions" in app

    forbidden = (
        "watch me",
        "teach-by-watching",
        "browser_history",
        "keylogging",
        "screenshot",
        "ocr",
        "coordinate capture",
    )
    lowered = qml.casefold()
    assert all(marker not in lowered for marker in forbidden)
    assert PROMOTED_HERO_ROOM_IDS == ("gaming", "project", "support_desk")
