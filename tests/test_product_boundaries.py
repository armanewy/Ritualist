from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_product_boundaries_document_contains_containment_doctrine() -> None:
    text = (REPO_ROOT / "docs" / "PRODUCT_BOUNDARIES.md").read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    assert "local ritual/runbook engine with a desktop-native body" in normalized
    assert "Recipes and rituals are the center of gravity" in normalized
    assert "If a feature does not improve one of those, it does not ship." in normalized
    assert "Setpiece has six product nouns" in text
    for noun in ("Room", "Ritual", "Component", "Shortcut", "Suggestion", "Pack"):
        assert f"**{noun}**" in text
    assert "Setpiece is not allowed to become" in text


def test_product_boundaries_document_contains_active_freeze_rules() -> None:
    text = (REPO_ROOT / "docs" / "PRODUCT_BOUNDARIES.md").read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    required = (
        "The v0.2 release line is in feature freeze.",
        "desktop-host expansion is frozen",
        "Browser history and Recall-like sources are frozen.",
        "New primitive families are frozen unless a hero Room or runbook requires them",
        "Marketplace behavior is frozen.",
        "Recording remains frozen permanently",
    )
    for phrase in required:
        assert phrase in normalized


def test_roadmap_keeps_feature_freeze_as_current_focus() -> None:
    text = (REPO_ROOT / "docs" / "roadmap.md").read_text(encoding="utf-8")

    assert "Stabilize the v0.2 release line and cut feature creep." in text
    assert "## Active Feature Freeze" in text
    assert "Do not add new primitive families during the active feature freeze." in text
    assert "browser history collection" in text
    assert "Watch Me, record mode, macro recording" in text


def test_canvas_docs_do_not_reopen_frozen_desktop_host_expansion() -> None:
    text = (REPO_ROOT / "docs" / "canvas.md").read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    assert "Desktop Work-Area mode on top of the normal desktop" in normalized
    assert "Desktop-host expansion is frozen" in normalized
    assert "immersive/fullscreen canvas mode" not in text
    assert "true shell replacement research" not in text


def test_room_builder_roadmap_keeps_three_hero_rooms() -> None:
    text = (REPO_ROOT / "docs" / "ROOM_BUILDER_ROADMAP.md").read_text(encoding="utf-8")

    assert "- Gaming Room" in text
    assert "- Project Room" in text
    assert "- Support Desk" in text
    assert "- Focus/Study" not in text
    assert "- Helpdesk" not in text
    assert "not a promoted starter Room" in text


def test_readme_leads_with_ritual_first_product_definition() -> None:
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert "safe local rituals that can be previewed, checked, run, paused, logged, and recovered" in text
    assert "Recipes and rituals remain the center of gravity" in text
    assert "Canvas exists to express rituals" in text
