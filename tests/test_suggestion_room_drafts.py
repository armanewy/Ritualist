from __future__ import annotations

import pytest

from setpiece.canvas import (
    CanvasBackground,
    CanvasBackgroundType,
    CanvasBindingKind,
    CanvasDocument,
    validate_canvas_structure,
)
from setpiece.shortcuts import ShortcutService
from setpiece.suggestions.drafts_room import (
    PROMOTED_HERO_ROOM_IDS,
    SAFE_ROOM_DRAFT_COMPONENT_TYPES,
    RoomDraftError,
    build_room_draft,
    build_room_draft_result,
    promoted_hero_room_snapshot,
)
from setpiece.suggestions.models import Suggestion, SuggestionStatus
from setpiece.suggestions.review import (
    SuggestionReviewRequiredError,
    build_approval_record,
)


REVIEWED_AT = "2026-06-18T12:34:56Z"


def _room_suggestion(
    proposed_actions: tuple[dict[str, object], ...] = (
        {
            "action": "review_room_canvas",
            "kind": "room_canvas",
            "room_id": "support_desk",
            "label": "Support Desk",
        },
    ),
) -> Suggestion:
    return Suggestion.create(
        kind="room_canvas",
        title="Review Support Desk canvas",
        description="Review-only Room draft suggestion",
        confidence=0.72,
        evidence_summary="Repeated Room usage with local activity",
        evidence_count=3,
        sources=("setpiece_journal", "recent_items"),
        proposed_actions=proposed_actions,
        missing_inputs=("room_review",),
    )


def _approved(suggestion: Suggestion) -> Suggestion:
    approval = build_approval_record(
        suggestion,
        reviewed_by="operator",
        reviewed_at=REVIEWED_AT,
        approved=True,
    )
    return suggestion.with_status(SuggestionStatus.APPROVED, approval=approval)


def test_room_draft_builder_requires_current_approval() -> None:
    suggestion = _room_suggestion()

    with pytest.raises(SuggestionReviewRequiredError):
        build_room_draft(suggestion)


def test_room_draft_builder_returns_valid_system_wallpaper_canvas() -> None:
    suggestion = _approved(
        _room_suggestion(
            proposed_actions=(
                {
                    "action": "review_room_canvas",
                    "kind": "room_canvas",
                    "room_id": "support_desk",
                    "label": "Support Desk",
                },
                {
                    "action": "review_room_canvas",
                    "component_type": "shortcut.folder",
                    "label": "Ticket Folder",
                },
                {
                    "action": "review_room_canvas",
                    "component_type": "shortcut.app",
                    "label": "Support Console",
                },
                {
                    "action": "review_room_canvas",
                    "kind": "ritual_recipe",
                    "label": "Support Shift",
                    "recipe_id": "support_shift",
                },
            )
        )
    )

    result = build_room_draft_result(suggestion)
    document = result.document
    components = {component.id: component for component in document.components}
    types = {component.type for component in document.components}

    assert isinstance(document, CanvasDocument)
    assert result.validation.valid is True
    assert validate_canvas_structure(document).valid is True
    assert document.background.type is CanvasBackgroundType.SYSTEM_WALLPAPER
    assert document.background.value == ""
    assert document.name == "Support Desk Draft"
    assert types <= SAFE_ROOM_DRAFT_COMPONENT_TYPES
    assert {"shortcut.folder", "shortcut.app", "ritual.card", "ritual.status", "ritual.controller"} <= types
    assert components["ritual_1"].binding is not None
    assert components["ritual_1"].binding.kind is CanvasBindingKind.RECIPE
    assert components["ritual_1"].binding.reference == "support_shift"
    assert components["ritual_status_1"].binding is not None
    assert components["ritual_status_1"].binding.reference == "support_shift"
    assert components["ritual_controller_1"].binding is not None
    assert components["ritual_controller_1"].binding.reference == "support_shift"


def test_room_draft_status_and_controller_require_recipe_binding() -> None:
    document = build_room_draft(_approved(_room_suggestion()))
    types = [component.type for component in document.components]

    assert "ritual.card" in types
    assert "shortcut.folder" in types
    assert "shortcut.app" in types
    assert "ritual.status" not in types
    assert "ritual.controller" not in types


def test_room_draft_accepts_only_passthrough_backgrounds() -> None:
    approved = _approved(_room_suggestion())

    system = build_room_draft(approved, background="system-background")
    transparent = build_room_draft(
        approved,
        background=CanvasBackground(type="transparent", value="passthrough"),
    )

    assert system.background.type is CanvasBackgroundType.SYSTEM_WALLPAPER
    assert transparent.background.type is CanvasBackgroundType.TRANSPARENT
    with pytest.raises(RoomDraftError, match="wallpaper passthrough"):
        build_room_draft(approved, background={"type": "solid", "value": "#10141c"})


def test_room_draft_rejects_internal_minimal_desktop_target() -> None:
    suggestion = _approved(
        _room_suggestion(
            proposed_actions=(
                {
                    "action": "review_room_canvas",
                    "kind": "room_canvas",
                    "room_id": "minimal_desktop",
                    "label": "Minimal Desktop",
                },
            )
        )
    )

    with pytest.raises(RoomDraftError, match="internal Room"):
        build_room_draft(suggestion)


def test_room_draft_does_not_mutate_promoted_rooms_or_execute_shortcuts(monkeypatch) -> None:
    before = promoted_hero_room_snapshot()

    def fail_open(self: ShortcutService, request: object) -> object:
        raise AssertionError(f"draft creation must not execute shortcut {request!r}")

    monkeypatch.setattr(ShortcutService, "open", fail_open)
    document = build_room_draft(_approved(_room_suggestion()))

    assert document.id.startswith("support_desk_")
    assert promoted_hero_room_snapshot() == before
    assert tuple(room_id for room_id, _name, _canvas_id in before) == PROMOTED_HERO_ROOM_IDS
    assert len(before) == 3
