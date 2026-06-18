from __future__ import annotations

from pathlib import Path

import pytest

from ritualist.suggestions.drafts_shortcut import (
    SHORTCUT_DRAFT_SCHEMA_VERSION,
    ShortcutDraftUnsupportedError,
    ShortcutDraftValidationError,
    build_shortcut_draft,
)
from ritualist.suggestions.models import Suggestion, SuggestionStatus
from ritualist.suggestions.review import (
    SuggestionReviewRequiredError,
    build_approval_record,
)


REVIEWED_AT = "2026-06-18T11:12:13Z"


def _shortcut_suggestion(component_type: str, *, title: str = "Project shortcut") -> Suggestion:
    return Suggestion.create(
        kind="shortcut_component",
        title=title,
        description="Review-only shortcut component suggestion",
        confidence=0.8,
        evidence_summary="Repeated shortcut target use",
        evidence_count=3,
        sources=("ritualist_journal",),
        proposed_actions=(
            {
                "action": "review_shortcut_component",
                "kind": component_type,
                "component_type": component_type,
                "label": title,
                "missing_input": _missing_input_for(component_type),
            },
        ),
        missing_inputs=(_missing_input_for(component_type),),
    )


def _approved(suggestion: Suggestion) -> Suggestion:
    return suggestion.with_status(
        SuggestionStatus.APPROVED,
        approval=build_approval_record(
            suggestion,
            reviewed_by="operator",
            approved=True,
            reviewed_at=REVIEWED_AT,
        ),
    )


def _missing_input_for(component_type: str) -> str:
    return {
        "shortcut.folder": "folder_path",
        "shortcut.app": "app_target",
        "shortcut.url": "url",
    }[component_type]


def test_shortcut_draft_requires_current_approval() -> None:
    suggestion = _shortcut_suggestion("shortcut.folder")

    with pytest.raises(SuggestionReviewRequiredError):
        build_shortcut_draft(suggestion)


def test_folder_shortcut_draft_without_path_is_unplaced_needs_setup() -> None:
    suggestion = _approved(_shortcut_suggestion("shortcut.folder", title="Workspace"))

    draft = build_shortcut_draft(suggestion)

    assert draft["schema_version"] == SHORTCUT_DRAFT_SCHEMA_VERSION
    assert draft["status"] == "needs_setup"
    assert draft["component_type"] == "shortcut.folder"
    assert draft["missing_inputs"] == ["folder_path"]
    assert draft["shortcut"] == {
        "kind": "folder",
        "action": "open",
        "target_configured": False,
        "target_label": "Workspace",
    }
    assert draft["review"]["required"] is True
    assert draft["review"]["approved"] is True
    assert draft["review"]["reviewed_at"] == REVIEWED_AT

    component = draft["component"]
    assert component["type"] == "shortcut.folder"
    assert component["props"] == {"title": "Workspace"}
    assert "path" not in component["props"]
    assert "x" not in component and "y" not in component
    assert draft["validation"]["valid"] is True
    assert any("target is not configured" in item for item in draft["validation"]["warnings"])
    assert "run_log" not in str(draft)
    assert "recipe_id" not in str(draft)


def test_missing_local_folder_path_remains_needs_setup(tmp_path: Path) -> None:
    missing = tmp_path / "missing-project"
    suggestion = _approved(_shortcut_suggestion("shortcut.folder", title="Missing Project"))

    draft = build_shortcut_draft(
        suggestion,
        reviewed_inputs={"folder_path": str(missing)},
    )

    assert draft["status"] == "needs_setup"
    assert draft["setup_issue"].startswith("folder shortcut target needs setup")
    assert draft["component"]["props"]["path"] == str(missing)
    assert draft["component"]["binding"]["kind"] == "shortcut.folder"
    assert draft["component"]["binding"]["path"] == str(missing)
    assert draft["validation"]["valid"] is True
    assert any("needs setup" in item for item in draft["validation"]["warnings"])
    assert not (tmp_path / "runs").exists()


def test_app_shortcut_draft_accepts_reviewed_local_app_path(tmp_path: Path) -> None:
    app = tmp_path / "editor.exe"
    app.write_text("fake executable placeholder", encoding="utf-8")
    suggestion = _approved(_shortcut_suggestion("shortcut.app", title="Editor"))

    draft = build_shortcut_draft(suggestion, reviewed_inputs={"app_target": str(app)})

    assert draft["status"] == "ready"
    assert draft["shortcut"] == {
        "kind": "app",
        "action": "launch",
        "target_configured": True,
        "target_label": "editor.exe",
    }
    assert draft["component"]["props"] == {"title": "Editor", "path": str(app)}
    assert draft["component"]["binding"] == {
        "kind": "shortcut.app",
        "path": str(app),
    }
    assert draft["validation"]["valid"] is True
    assert draft["validation"]["errors"] == []
    assert not (tmp_path / "runs").exists()


def test_url_shortcut_draft_accepts_reviewed_http_url() -> None:
    suggestion = _approved(_shortcut_suggestion("shortcut.url", title="Docs"))

    draft = build_shortcut_draft(
        suggestion,
        reviewed_inputs={"url": "https://example.com/docs"},
    )

    assert draft["status"] == "ready"
    assert draft["shortcut"] == {
        "kind": "url",
        "action": "open",
        "target_configured": True,
        "target_label": "example.com",
    }
    assert draft["component"]["props"] == {
        "title": "Docs",
        "url": "https://example.com/docs",
    }
    assert draft["component"]["binding"] == {
        "kind": "shortcut.url",
        "url": "https://example.com/docs",
    }
    assert draft["validation"]["valid"] is True


@pytest.mark.parametrize(
    "reviewed_inputs",
    [
        {"command": "cmd /c calc.exe"},
        {"rawCommand": "powershell Start-Process calc"},
        {"app_target": "cmd /c calc.exe"},
    ],
)
def test_shortcut_draft_rejects_raw_commands(reviewed_inputs: dict[str, str]) -> None:
    suggestion = _approved(_shortcut_suggestion("shortcut.app", title="Unsafe App"))

    with pytest.raises(ShortcutDraftValidationError):
        build_shortcut_draft(suggestion, reviewed_inputs=reviewed_inputs)


@pytest.mark.parametrize(
    "component_type,reviewed_inputs",
    [
        ("shortcut.folder", {"folder_path": r"\\server\share"}),
        ("shortcut.url", {"url": "javascript:alert(1)"}),
    ],
)
def test_shortcut_draft_rejects_imported_or_non_http_targets(
    component_type: str,
    reviewed_inputs: dict[str, str],
) -> None:
    suggestion = _approved(_shortcut_suggestion(component_type, title="Unsafe Shortcut"))

    with pytest.raises(ShortcutDraftValidationError):
        build_shortcut_draft(suggestion, reviewed_inputs=reviewed_inputs)


def test_shortcut_draft_rejects_non_shortcut_suggestions() -> None:
    suggestion = Suggestion.create(
        kind="ritual_recipe",
        title="Recipe",
        description="Review-only recipe suggestion",
        confidence=0.7,
        evidence_summary="Repeated pattern",
        evidence_count=2,
        proposed_actions=(
            {
                "action": "review_ritual_recipe",
                "kind": "ritual_recipe",
                "title": "Recipe",
            },
        ),
    )

    with pytest.raises(ShortcutDraftUnsupportedError):
        build_shortcut_draft(_approved(suggestion))
