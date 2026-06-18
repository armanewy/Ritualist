from __future__ import annotations

from pathlib import Path

import pytest

from ritualist.suggestions.models import Suggestion, SuggestionStatus
from ritualist.suggestions.review import (
    approve_suggestion,
    can_create_draft,
    cancel_suggestion,
    dismiss_suggestion,
    is_approval_current,
    proposed_artifact_summary,
    require_approval_for_draft,
    review_snapshot,
    review_token_for,
    SuggestionReviewRequiredError,
    SuggestionRuntimeExecutionBlockedError,
)
from ritualist.suggestions.storage import SuggestionStore


REVIEWED_AT = "2026-06-18T10:11:12Z"


def _suggestion(
    title: str = "Project setup",
    proposed_actions: tuple[dict[str, object], ...] = (
        {
            "action": "review_ritual_recipe",
            "kind": "ritual_recipe",
            "title": "Project setup",
            "recipe_id": "project_setup",
        },
    ),
) -> Suggestion:
    return Suggestion.create(
        kind="ritual_recipe",
        title=title,
        description="Review-only recipe draft suggestion",
        confidence=0.8,
        evidence_summary="Repeated project setup pattern",
        evidence_count=3,
        sources=("ritualist_journal", "recent_items"),
        proposed_actions=proposed_actions,
        missing_inputs=("project_root",),
    )


def test_review_snapshot_exposes_token_and_proposed_artifact_summary() -> None:
    suggestion = _suggestion()

    snapshot = review_snapshot(suggestion)

    assert snapshot.suggestion_id == suggestion.id
    assert snapshot.review_token == review_token_for(suggestion)
    assert snapshot.proposed_artifact_summary == proposed_artifact_summary(suggestion)
    assert snapshot.proposed_artifact_summary.startswith("Ritual recipe draft: Project setup")
    assert "project_root" in snapshot.proposed_artifact_summary
    assert snapshot.approval_current is False
    assert snapshot.can_create_draft is False


def test_draft_gate_requires_approval_before_creation() -> None:
    suggestion = _suggestion()

    assert can_create_draft(suggestion) is False
    with pytest.raises(SuggestionReviewRequiredError):
        require_approval_for_draft(suggestion)


def test_approve_records_timestamp_token_and_does_not_create_or_enable_draft(
    tmp_path: Path,
) -> None:
    store = SuggestionStore(path=tmp_path / "suggestions.jsonl")
    suggestion = store.save(_suggestion())

    approved = approve_suggestion(
        store,
        suggestion.id,
        reviewed_by="Operator One",
        reviewed_at=REVIEWED_AT,
    )

    assert approved.status is SuggestionStatus.APPROVED
    assert approved.drafted_artifact_ref == ""
    assert approved.approval is not None
    assert approved.approval.approved is True
    assert approved.approval.reviewed_by == "operator_one"
    assert approved.approval.reviewed_at == REVIEWED_AT
    assert approved.approval.review_token == review_token_for(approved)
    assert "Ritual recipe draft" in approved.approval.artifact_summary
    assert is_approval_current(approved) is True
    assert require_approval_for_draft(approved) is approved
    assert {child.name for child in tmp_path.iterdir()} == {"suggestions.jsonl"}


@pytest.mark.parametrize(
    "review_action",
    [
        "review_shortcut_component",
        "review_ritual_recipe",
        "review_room_canvas",
        "review_cleanup_hint",
    ],
)
def test_approval_allows_review_only_proposal_actions(
    tmp_path: Path,
    review_action: str,
) -> None:
    store = SuggestionStore(path=tmp_path / "suggestions.jsonl")
    suggestion = store.save(
        _suggestion(
            proposed_actions=(
                {
                    "action": review_action,
                    "label": "Review-only proposal",
                },
            )
        )
    )

    approved = approve_suggestion(
        store,
        suggestion.id,
        reviewed_by="operator",
        reviewed_at=REVIEWED_AT,
    )

    assert approved.status is SuggestionStatus.APPROVED
    assert approved.approval is not None
    assert approved.approval.approved is True


@pytest.mark.parametrize(
    "intent_key,intent_value",
    [
        ("kind", "shortcut.folder"),
        ("kind", "shortcut.app"),
        ("kind", "shortcut.url"),
        ("kind", "ritual_recipe"),
        ("kind", "room_canvas"),
        ("type", "shortcut.folder"),
        ("type", "shortcut_component"),
        ("type", "cleanup_hint"),
        ("component_type", "shortcut.folder"),
        ("component_type", "shortcut.app"),
        ("component_type", "shortcut.url"),
    ],
)
def test_approval_allows_review_only_taxonomy_values(
    tmp_path: Path,
    intent_key: str,
    intent_value: str,
) -> None:
    store = SuggestionStore(path=tmp_path / "suggestions.jsonl")
    suggestion = store.save(
        _suggestion(
            proposed_actions=(
                {
                    "action": "review_shortcut_component",
                    intent_key: intent_value,
                    "label": "Review-only taxonomy",
                },
            )
        )
    )

    approved = approve_suggestion(
        store,
        suggestion.id,
        reviewed_by="operator",
        reviewed_at=REVIEWED_AT,
    )

    assert approved.status is SuggestionStatus.APPROVED
    assert approved.approval is not None
    assert approved.approval.approved is True


def test_dismiss_and_cancel_store_negative_review_records(tmp_path: Path) -> None:
    store = SuggestionStore(path=tmp_path / "suggestions.jsonl")
    dismissed_source = store.save(_suggestion("Dismissed setup"))
    cancelled_source = store.save(_suggestion("Cancelled setup"))

    dismissed = dismiss_suggestion(
        store,
        dismissed_source.id,
        reviewed_by="operator",
        reviewed_at=REVIEWED_AT,
    )
    cancelled = cancel_suggestion(
        store,
        cancelled_source.id,
        reviewed_by="operator",
        reviewed_at=REVIEWED_AT,
    )

    assert dismissed.status is SuggestionStatus.DISMISSED
    assert cancelled.status is SuggestionStatus.CANCELLED
    assert dismissed.approval is not None
    assert cancelled.approval is not None
    assert dismissed.approval.approved is False
    assert cancelled.approval.approved is False
    assert dismissed.approval.reviewed_at == REVIEWED_AT
    assert cancelled.approval.reviewed_at == REVIEWED_AT
    assert can_create_draft(dismissed) is False
    assert can_create_draft(cancelled) is False


def test_changed_suggestion_requires_re_review(tmp_path: Path) -> None:
    store = SuggestionStore(path=tmp_path / "suggestions.jsonl")
    suggestion = store.save(_suggestion())
    approved = approve_suggestion(
        store,
        suggestion.id,
        reviewed_by="operator",
        reviewed_at=REVIEWED_AT,
    )
    changed_payload = approved.to_dict()
    changed_payload["title"] = "Changed project setup"
    changed = Suggestion.from_mapping(changed_payload)

    assert changed.approval == approved.approval
    assert review_token_for(changed) != approved.approval.review_token
    assert is_approval_current(changed) is False
    with pytest.raises(SuggestionReviewRequiredError):
        require_approval_for_draft(changed)

    store.save(changed)
    reapproved = approve_suggestion(
        store,
        changed.id,
        reviewed_by="operator",
        reviewed_at="2026-06-18T10:11:13Z",
    )
    assert reapproved.approval is not None
    assert reapproved.approval.review_token == review_token_for(reapproved)
    assert reapproved.approval.review_token != approved.approval.review_token
    assert is_approval_current(reapproved) is True


@pytest.mark.parametrize(
    "runtime_action",
    [
        "open_app",
        "openUrl",
        "launchApp",
        "runRecipe",
        "executeRecipe",
        "pressKey",
        "desktopClick",
        "browserOpen",
        "startRitual",
        "openurl",
        "openapp",
        "openfile",
        "openfolder",
        "launchapp",
        "runrecipe",
        "executerecipe",
        "presskey",
        "desktopclick",
        "browseropen",
        "startritual",
        "runritual",
        "execCommand",
        "navigateUrl",
        "visitUrl",
        "gotoUrl",
        "browseUrl",
        "startApp",
        "startApplication",
        "openProgram",
        "startProgram",
        "startProcess",
        "sendKeys",
        "keyboardShortcut",
        "spawnProcess",
        "createProcess",
        "invokeCommand",
        "systemCommand",
        "powershellCommand",
        "pythonCommand",
        "openWebsite",
        "openLink",
        "keyPress",
        "keyboardInput",
        "inputText",
        "sendText",
    ],
)
def test_approval_rejects_runtime_execution_actions(
    tmp_path: Path,
    runtime_action: str,
) -> None:
    store = SuggestionStore(path=tmp_path / "suggestions.jsonl")
    suggestion = store.save(
        _suggestion(
            proposed_actions=(
                {
                    "action": runtime_action,
                    "label": "Calculator",
                },
            )
        )
    )

    with pytest.raises(SuggestionRuntimeExecutionBlockedError):
        approve_suggestion(
            store,
            suggestion.id,
            reviewed_by="operator",
            reviewed_at=REVIEWED_AT,
        )

    restored = store.get(suggestion.id)
    assert restored is not None
    assert restored.status is SuggestionStatus.NEW
    assert restored.approval is None


@pytest.mark.parametrize("intent_key", ["kind", "type"])
@pytest.mark.parametrize(
    "runtime_value",
    [
        "spawnProcess",
        "openWebsite",
        "keyPress",
        "systemCommand",
    ],
)
def test_approval_rejects_runtime_taxonomy_values(
    tmp_path: Path,
    intent_key: str,
    runtime_value: str,
) -> None:
    store = SuggestionStore(path=tmp_path / "suggestions.jsonl")
    suggestion = store.save(
        _suggestion(
            proposed_actions=(
                {
                    "action": "review_shortcut_component",
                    intent_key: runtime_value,
                    "label": "Unsafe taxonomy",
                },
            )
        )
    )

    with pytest.raises(SuggestionRuntimeExecutionBlockedError):
        approve_suggestion(
            store,
            suggestion.id,
            reviewed_by="operator",
            reviewed_at=REVIEWED_AT,
        )

    restored = store.get(suggestion.id)
    assert restored is not None
    assert restored.status is SuggestionStatus.NEW
    assert restored.approval is None


@pytest.mark.parametrize(
    "proposed_action",
    [
        {"action": ["spawnProcess"], "label": "Unsafe action"},
        {"action": 123, "label": "Unsafe action"},
        {"action": None, "label": "Unsafe action"},
        {
            "action": "review_shortcut_component",
            "type": ["spawnProcess"],
            "label": "Unsafe type",
        },
        {
            "action": "review_shortcut_component",
            "kind": 123,
            "label": "Unsafe kind",
        },
        {
            "action": "review_shortcut_component",
            "kind": {"value": "shortcut.folder"},
            "label": "Unsafe kind",
        },
        {
            "action": "review_shortcut_component",
            "component_type": ["spawnProcess"],
            "label": "Unsafe component type",
        },
    ],
)
def test_approval_rejects_non_string_intent_values(
    tmp_path: Path,
    proposed_action: dict[str, object],
) -> None:
    store = SuggestionStore(path=tmp_path / "suggestions.jsonl")
    suggestion = store.save(_suggestion(proposed_actions=(proposed_action,)))

    with pytest.raises(SuggestionRuntimeExecutionBlockedError):
        approve_suggestion(
            store,
            suggestion.id,
            reviewed_by="operator",
            reviewed_at=REVIEWED_AT,
        )

    restored = store.get(suggestion.id)
    assert restored is not None
    assert restored.status is SuggestionStatus.NEW
    assert restored.approval is None


@pytest.mark.parametrize(
    "component_type",
    [
        "spawnProcess",
        "openUrl",
        "shell",
    ],
)
def test_approval_rejects_runtime_component_type_values(
    tmp_path: Path,
    component_type: str,
) -> None:
    store = SuggestionStore(path=tmp_path / "suggestions.jsonl")
    suggestion = store.save(
        _suggestion(
            proposed_actions=(
                {
                    "action": "review_shortcut_component",
                    "component_type": component_type,
                    "label": "Unsafe component type",
                },
            )
        )
    )

    with pytest.raises(SuggestionRuntimeExecutionBlockedError):
        approve_suggestion(
            store,
            suggestion.id,
            reviewed_by="operator",
            reviewed_at=REVIEWED_AT,
        )

    restored = store.get(suggestion.id)
    assert restored is not None
    assert restored.status is SuggestionStatus.NEW
    assert restored.approval is None


@pytest.mark.parametrize(
    "proposed_action",
    [
        {"kind": "ritual_recipe", "label": "Missing action"},
        {"label": "Missing action"},
        {"component_type": "shortcut.app", "label": "Missing action"},
    ],
)
def test_approval_rejects_missing_review_action(
    tmp_path: Path,
    proposed_action: dict[str, object],
) -> None:
    store = SuggestionStore(path=tmp_path / "suggestions.jsonl")
    suggestion = store.save(_suggestion(proposed_actions=(proposed_action,)))

    with pytest.raises(SuggestionRuntimeExecutionBlockedError):
        approve_suggestion(
            store,
            suggestion.id,
            reviewed_by="operator",
            reviewed_at=REVIEWED_AT,
        )

    restored = store.get(suggestion.id)
    assert restored is not None
    assert restored.status is SuggestionStatus.NEW
    assert restored.approval is None


def test_approval_rejects_empty_proposed_actions(tmp_path: Path) -> None:
    store = SuggestionStore(path=tmp_path / "suggestions.jsonl")
    suggestion = store.save(_suggestion(proposed_actions=()))

    with pytest.raises(SuggestionRuntimeExecutionBlockedError):
        approve_suggestion(
            store,
            suggestion.id,
            reviewed_by="operator",
            reviewed_at=REVIEWED_AT,
        )

    restored = store.get(suggestion.id)
    assert restored is not None
    assert restored.status is SuggestionStatus.NEW
    assert restored.approval is None
    assert can_create_draft(restored) is False


@pytest.mark.parametrize(
    "proposed_action",
    [
        {
            "action": "review_ritual_recipe",
            "kind": "ritual_recipe",
            "notes": [{"action": "spawnProcess", "label": "bad"}],
        },
        {
            "action": "review_ritual_recipe",
            "kind": "ritual_recipe",
            "notes": [[{"action": "spawnProcess", "label": "bad"}]],
        },
        {
            "action": "review_shortcut_component",
            "kind": "shortcut_component",
            "label": [{"component_type": "openUrl"}],
        },
        {
            "action": "review_shortcut_component",
            "kind": "shortcut_component",
            "label": [[{"component_type": "openUrl"}]],
        },
    ],
)
def test_approval_rejects_runtime_intent_inside_sequence_values(
    tmp_path: Path,
    proposed_action: dict[str, object],
) -> None:
    store = SuggestionStore(path=tmp_path / "suggestions.jsonl")
    suggestion = store.save(_suggestion(proposed_actions=(proposed_action,)))

    with pytest.raises(SuggestionRuntimeExecutionBlockedError):
        approve_suggestion(
            store,
            suggestion.id,
            reviewed_by="operator",
            reviewed_at=REVIEWED_AT,
        )

    restored = store.get(suggestion.id)
    assert restored is not None
    assert restored.status is SuggestionStatus.NEW
    assert restored.approval is None
    assert can_create_draft(restored) is False
