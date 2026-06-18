from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
NORTH_STAR = REPO_ROOT / "docs" / "NORTH_STAR.md"
HERO_ROOMS = ("Gaming Room", "Project Room", "Support Desk")


def _north_star_text() -> str:
    return NORTH_STAR.read_text(encoding="utf-8")


def _normalized_text() -> str:
    return " ".join(_north_star_text().split())


def test_north_star_states_ritual_first_product_contract() -> None:
    normalized = _normalized_text()

    assert "Ritualist is a local ritual/runbook engine with a desktop-native body." in normalized
    assert "Recipes and rituals are the center of gravity." in normalized
    assert "Rooms, Canvas, shortcuts, Suggestions, packs, logs, and recovery surfaces" in normalized
    assert "shell replacement" in normalized
    assert "marketplace" in normalized
    assert "cloud automation service" in normalized


def test_north_star_locks_exactly_three_promoted_hero_rooms() -> None:
    text = _north_star_text()
    normalized = " ".join(text.split())
    hero_section = text.split("## Hero Rooms", 1)[1].split("### Gaming Room", 1)[0]
    promoted_bullets = re.findall(r"^- ([^\n]+)$", hero_section, flags=re.MULTILINE)

    assert tuple(promoted_bullets) == HERO_ROOMS
    assert "Ritualist has exactly three promoted hero Rooms:" in normalized
    assert "Do not promote a fourth Room." in normalized
    assert "`minimal_desktop` Canvas must not be deleted" in text
    assert "not a promoted Room" in normalized


def test_north_star_locks_hero_room_requirements_without_styling_dependency() -> None:
    normalized = _normalized_text()

    gaming_requirements = (
        "Gaming Room centers the `gaming_mode` ritual.",
        "Doctor, Dry Run, and Run",
        "runtime status and controller state",
        "preview the Diablo target",
        "recent activity",
        "confirmation and recovery surfaces",
    )
    project_requirements = (
        "Project Room centers a coding/project setup ritual.",
        "folder, editor, terminal, and documentation shortcuts",
        "ritual status and controller state",
        "recent activity",
    )
    support_requirements = (
        "Support Desk centers support triage runbooks.",
        "collect diagnostics",
        "meeting audio troubleshooting",
        "VPN Repair placeholder",
        "New Hire Setup draft",
        "Doctor, status, and controller state",
        "recent runs",
        "local evidence and logs",
    )

    for phrase in gaming_requirements + project_requirements + support_requirements:
        assert phrase in normalized


def test_north_star_locks_ritual_state_contract() -> None:
    normalized = _normalized_text()

    required_states = (
        "Doctor status",
        "dry-run status",
        "current step",
        "waiting state",
        "confirmation required state",
        "paused state",
        "failed state",
        "interrupted recovery",
        "last run summary",
        "logs and artifacts access",
    )
    for state in required_states:
        assert state in normalized

    assert "Risky desktop actions require explicit confirmation gates." in normalized
    assert "Recovery must be visible after an interrupted run." in normalized


def test_north_star_locks_suggestions_and_entry_safety_contracts() -> None:
    normalized = _normalized_text()

    assert "Suggestions are local and opt-in." in normalized
    assert "review-before-create" in normalized
    assert "must never auto-create or auto-run a ritual" in normalized
    assert "taskbar-preserving Room picker" in normalized
    assert "never fullscreen by default" in normalized
    assert "The entry surface promotes exactly three Rooms: Gaming Room, Project Room, and Support Desk." in normalized
    assert "The recipe library is secondary" in normalized
    assert "must never run automatically and must never create local rituals automatically" in normalized


def test_north_star_keeps_frozen_capabilities_out_of_product_contract() -> None:
    normalized = _normalized_text()

    forbidden_capability_phrases = (
        "Watch Me",
        "recording",
        "OCR",
        "screenshots",
        "keylogging",
        "coordinate capture",
        "browser history ingestion",
        "cloud sync",
        "remote execution",
        "marketplace behavior",
        "password automation",
        "gameplay automation",
        "taskbar hiding",
        "kiosk mode",
        "click-through automation",
        "arbitrary recipe-supplied Python",
        "arbitrary recipe-supplied JavaScript",
        "arbitrary recipe-supplied PowerShell",
        "arbitrary shell snippets",
        "arbitrary QML",
        "arbitrary HTML",
    )
    for phrase in forbidden_capability_phrases:
        assert phrase in normalized

    assert "Do not add Watch Me, recording, OCR, screenshots, keylogging, coordinate capture" in normalized
    assert "Windows UI Automation imports must remain lazy and inside adapter methods." in normalized
    assert "Tests must use fake adapters" in normalized
