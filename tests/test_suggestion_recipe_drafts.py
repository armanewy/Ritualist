from __future__ import annotations

from pathlib import Path

import pytest

from setpiece.recipe_loader import load_recipe_document
from setpiece.suggestions.drafts_recipe import (
    DRAFT_RECIPE_SCHEMA_VERSION,
    RecipeDraftBuildError,
    build_draft_recipe,
)
from setpiece.suggestions.models import Suggestion
from setpiece.suggestions.review import (
    SuggestionReviewRequiredError,
    approve_suggestion,
)
from setpiece.suggestions.storage import SuggestionStore


REVIEWED_AT = "2026-06-18T12:00:00Z"


def _suggestion(
    *,
    missing_inputs: tuple[str, ...] = ("project_url", "operator_prompt"),
) -> Suggestion:
    return Suggestion.create(
        kind="ritual_recipe",
        title="Project handoff",
        description="Review-only recipe draft suggestion",
        confidence=0.8,
        evidence_summary="Repeated local project handoff pattern",
        evidence_count=3,
        sources=("setpiece_journal", "recent_items"),
        proposed_actions=(
            {
                "action": "review_ritual_recipe",
                "kind": "ritual_recipe",
                "title": "Project handoff",
                "recipe_id": "project_handoff",
            },
        ),
        missing_inputs=missing_inputs,
    )


def _approved(tmp_path: Path, suggestion: Suggestion | None = None) -> Suggestion:
    store = SuggestionStore(path=tmp_path / "suggestions.jsonl")
    saved = store.save(suggestion or _suggestion())
    return approve_suggestion(
        store,
        saved.id,
        reviewed_by="operator",
        reviewed_at=REVIEWED_AT,
    )


def test_draft_builder_requires_current_approval() -> None:
    with pytest.raises(SuggestionReviewRequiredError):
        build_draft_recipe(_suggestion())


def test_draft_builder_returns_disabled_data_and_missing_values_as_variables(
    tmp_path: Path,
) -> None:
    approved = _approved(tmp_path)

    draft = build_draft_recipe(approved)

    assert draft["schema_version"] == DRAFT_RECIPE_SCHEMA_VERSION
    assert draft["status"] == "disabled"
    assert draft["requires_doctor_before_enable"] is True
    assert draft["creation_side_effects"] == {
        "installed": False,
        "enabled": False,
        "ran": False,
        "wrote_files": False,
    }
    assert draft["missing_variables"] == ["operator_prompt"]
    recipe = draft["recipe"]
    assert recipe["id"] == "project-handoff-draft"
    assert recipe["name"] == "Project handoff draft"
    assert recipe["variables"] == {}
    assert recipe["environment"]["variable_hints"]["operator_prompt"]
    assert recipe["steps"] == [
        {
            "action": "human.checklist",
            "prompt": "Review approved suggestion before editing this disabled draft.",
            "items": ["Project handoff"],
        },
        {
            "action": "human.prompt",
            "prompt": "Provide {{ operator_prompt }} before enabling this draft.",
        },
        {
            "action": "wait.for_user",
            "prompt": "Run Doctor after filling draft variables.",
        },
    ]


def test_draft_builder_ignores_post_review_recipe_payload_mutation(
    tmp_path: Path,
) -> None:
    approved = _approved(tmp_path, _suggestion(missing_inputs=()))
    source = approved.to_dict()
    source["proposed_recipe"] = {
        "id": "post_review_added",
        "name": "Post review added",
        "steps": [
            {"action": "recipe.run", "recipe_id": "other"},
            {"action": "app.launch", "command": "powershell -Command Get-Process"},
            {"action": "browser.open", "url": "javascript:alert(1)"},
            {"action": "note.add", "text": "<script>alert(1)</script>"},
            {"action": "wait.seconds", "seconds": 1.0},
        ],
    }
    source["proposed_actions"][0]["steps"] = [
        {"action": "browser.open", "url": "javascript:alert(1)"}
    ]

    draft = build_draft_recipe(source)

    assert draft["recipe"]["id"] != "post_review_added"
    assert draft["recipe"]["steps"] == [
        {
            "action": "human.checklist",
            "prompt": "Review approved suggestion before editing this disabled draft.",
            "items": ["Project handoff"],
        },
        {
            "action": "wait.for_user",
            "prompt": "Run Doctor after filling draft variables.",
        },
    ]
    draft_text = str(draft).casefold()
    assert "powershell" not in draft_text
    assert "javascript:" not in draft_text
    assert "wait.seconds" not in draft_text
    assert draft["omitted_steps"] == []


def test_post_review_desktop_click_text_payload_is_ignored(
    tmp_path: Path,
) -> None:
    approved = _approved(tmp_path, _suggestion(missing_inputs=()))
    source = approved.to_dict()
    source["proposed_recipe"] = {
        "steps": [
            {
                "action": "desktop.click_text",
                "text": "Play",
                "requires_confirmation": True,
            },
            {
                "action": "desktop.click_text",
                "text": "Play",
                "window_title_contains": "Launcher",
            },
            {
                "action": "desktop.click_text",
                "text": "Play",
                "window_title_contains": "Launcher",
                "requires_confirmation": True,
            },
        ],
    }

    draft = build_draft_recipe(source)

    assert draft["recipe"]["steps"] == [
        {
            "action": "human.checklist",
            "prompt": "Review approved suggestion before editing this disabled draft.",
            "items": ["Project handoff"],
        },
        {
            "action": "wait.for_user",
            "prompt": "Run Doctor after filling draft variables.",
        }
    ]
    assert "desktop.click_text" not in str(draft)
    assert draft["omitted_steps"] == []


def test_draft_recipe_loads_after_operator_supplies_variables(tmp_path: Path) -> None:
    approved = _approved(tmp_path)

    draft = build_draft_recipe(approved)
    recipe_data = dict(draft["recipe"])

    recipe = load_recipe_document(
        recipe_data,
        overrides={
            "operator_prompt": "Continue?",
        },
    )

    assert recipe.id.endswith("draft")
    assert recipe.steps[0].action == "human.checklist"
