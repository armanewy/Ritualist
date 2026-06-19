from __future__ import annotations

from pathlib import Path
from typing import Any

from setpiece.adapters.fake import FakeAdapters
from setpiece.canvas import load_bundled_canvas, validate_canvas_document
from setpiece.canvas.runtime import CanvasRuntimeContext, build_canvas_runtime_model
from setpiece.executor import WorkflowExecutor
from setpiece.recipe_loader import load_recipe, read_recipe_document


REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_RECIPE_DIR = REPO_ROOT / "setpiece" / "sample_recipes"
SUPPORT_RECIPE_IDS = (
    "support_triage_workspace",
    "collect_basic_diagnostics",
    "meeting_audio_troubleshooting",
    "vpn_repair_placeholder",
    "new_hire_setup_draft",
)
SUPPORT_CARD_TITLES = {
    "Support Triage",
    "Collect Basic Diagnostics",
    "Meeting Audio Troubleshooting",
    "VPN Repair",
    "New Hire Setup",
}
ALLOWED_SUPPORT_ACTIONS = {
    "app.launch",
    "assert.path_exists",
    "browser.open",
    "confirm.ask",
    "human.checklist",
    "note.add",
    "wait.for_user",
}
FORBIDDEN_SUPPORT_ACTIONS = {
    "browser.click_role",
    "browser.click_test_id",
    "browser.click_text",
    "desktop.click_text",
    "input.hotkey",
    "notify.sound",
    "window.move",
    "window.resize",
}
FORBIDDEN_RECIPE_MARKERS = (
    "powershell",
    "javascript",
    "python",
    "desktop.click_text",
    "watch me",
    "recording",
    "screenshot",
    "ocr",
)


def test_support_desk_canvas_exposes_five_cards_and_main_run_surface() -> None:
    document = load_bundled_canvas("helpdesk_desktop")
    validation = validate_canvas_document(document)

    assert document.name == "Support Desk"
    assert validation.valid, validation.errors

    components = {component.id: component for component in document.components}
    ritual_cards = [component for component in document.components if component.type == "ritual.card"]

    assert {component.props_dict()["title"] for component in ritual_cards} == SUPPORT_CARD_TITLES
    assert {component.binding.reference for component in ritual_cards if component.binding} == set(
        SUPPORT_RECIPE_IDS
    )
    assert components["doctor_badge"].type == "doctor.badge"
    assert components["run_status"].type == "ritual.status"
    assert components["run_controller"].type == "ritual.controller"
    assert components["recent_runs"].type == "recent.activity"
    assert "Runbook Ledger" in components["recent_runs"].props_dict()["title"]
    assert "Open Logs" in components["recent_runs"].props_dict()["title"]
    assert "Open Logs / Evidence" in components["evidence_note"].props_dict()["text"]

    model = build_canvas_runtime_model(
        document,
        context=CanvasRuntimeContext(recipe_ids=set(SUPPORT_RECIPE_IDS), recent_runs=()),
    )

    for card in ritual_cards:
        assert "open_logs" in model.component_state(card.id).enabled_actions
    assert model.component_state("doctor_badge").enabled_actions == ("doctor",)
    assert model.component_state("recent_runs").enabled_actions == ("open_logs",)


def test_support_desk_recipes_validate_and_fake_adapter_dry_run() -> None:
    for recipe_id in SUPPORT_RECIPE_IDS:
        recipe = load_recipe(SAMPLE_RECIPE_DIR / f"{recipe_id}.yaml")
        fakes = FakeAdapters()
        confirmations: list[str] = []

        summary = WorkflowExecutor(
            adapters=fakes.bundle(),
            dry_run=True,
            confirmer=lambda prompt: confirmations.append(str(prompt)) or False,
        ).run(recipe)

        assert recipe.id == recipe_id
        assert summary.success
        assert [result.status for result in summary.results] == ["dry-run"] * len(
            recipe.execution_steps
        )
        assert fakes.browser.calls == []
        assert fakes.shell.calls == []
        assert fakes.window.calls == []
        assert fakes.desktop.calls == []
        assert fakes.input.calls == []
        assert confirmations == []


def test_support_desk_recipes_stay_inside_safe_support_actions() -> None:
    for recipe_id in SUPPORT_RECIPE_IDS:
        path = SAMPLE_RECIPE_DIR / f"{recipe_id}.yaml"
        raw = read_recipe_document(path)
        text = path.read_text(encoding="utf-8").casefold()
        actions = {step["action"] for step in _all_steps(raw)}

        assert raw["home"]["category"] == "Support Desk"
        assert raw["steps"][0]["action"] == "confirm.ask"
        assert actions <= ALLOWED_SUPPORT_ACTIONS
        assert actions.isdisjoint(FORBIDDEN_SUPPORT_ACTIONS)
        assert not any(marker in text for marker in FORBIDDEN_RECIPE_MARKERS)
        for step in _all_steps(raw):
            if step["action"] == "app.launch":
                assert step.get("requires_confirmation") is True


def test_vpn_repair_placeholder_is_manual_and_non_mutating() -> None:
    path = SAMPLE_RECIPE_DIR / "vpn_repair_placeholder.yaml"
    raw = read_recipe_document(path)
    text = path.read_text(encoding="utf-8").casefold()
    actions = [step["action"] for step in _all_steps(raw)]

    assert "placeholder" in raw["name"].casefold()
    assert "placeholder" in raw["home"]["card"]["subtitle"].casefold()
    assert "human.checklist" in actions
    assert "wait.for_user" in actions
    assert "note.add" in actions
    for marker in (
        "netsh",
        "ipconfig",
        "rasdial",
        "remove-vpnconnection",
        "set-vpnconnection",
        "password",
        "credential",
    ):
        assert marker not in text


def test_new_hire_setup_is_clearly_draft_review_only() -> None:
    path = SAMPLE_RECIPE_DIR / "new_hire_setup_draft.yaml"
    raw = read_recipe_document(path)
    text = path.read_text(encoding="utf-8").casefold()
    actions = [step["action"] for step in _all_steps(raw)]

    assert "draft" in raw["name"].casefold()
    assert "draft" in raw["description"].casefold()
    assert "review" in raw["description"].casefold()
    assert "human.checklist" in actions
    assert "note.add" in actions
    assert "app.launch" not in actions
    for marker in (
        "password",
        "credential",
        "winget",
        "msiexec",
        "choco",
        "install-package",
        "new-aduser",
        "dsadd",
    ):
        assert marker not in text


def _all_steps(raw: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        step
        for section in ("preflight", "steps", "verify")
        for step in raw.get(section, [])
    ]
