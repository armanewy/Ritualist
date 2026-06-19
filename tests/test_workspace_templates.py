from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from setpiece.adapters.fake import FakeAdapters
from setpiece.executor import WorkflowExecutor
from setpiece.recipe_loader import load_recipe, read_recipe_document

SAMPLE_DIR = Path(__file__).resolve().parents[1] / "setpiece" / "sample_recipes"
WORKSPACE_TEMPLATE_IDS = {
    "coding_mode",
    "meeting_mode",
    "research_mode",
    "streaming_mode",
}
HELPDESK_TEMPLATE_IDS = {
    "browser_admin_console_workspace",
    "collect_basic_diagnostics",
    "lab_classroom_setup",
    "meeting_audio_troubleshooting",
    "support_triage_workspace",
    "vendor_app_configuration_placeholder",
}
TEMPLATE_IDS = WORKSPACE_TEMPLATE_IDS | HELPDESK_TEMPLATE_IDS
TEMPLATE_PATHS = [SAMPLE_DIR / f"{template_id}.yaml" for template_id in sorted(TEMPLATE_IDS)]
SAMPLE_RECIPE_PATHS = sorted(SAMPLE_DIR.glob("*.yaml"))
TEMPLATE_REF_RE = re.compile(r"^\{\{\s*([A-Za-z_][A-Za-z0-9_.-]*)\s*\}\}$")
ALLOWED_TEMPLATE_ACTIONS = {
    "app.launch",
    "assert.file_exists",
    "assert.path_exists",
    "assert.window_exists",
    "browser.open",
    "confirm.ask",
    "wait.for_user",
}
FORBIDDEN_EVIDENCE_CAPTURE_ACTIONS = {
    "browser.capture_page",
    "browser.capture_page_contents",
    "browser.cookies",
    "browser.export_cookies",
    "browser.page_contents",
    "browser.page_source",
    "browser.screenshot",
    "clipboard.read",
    "desktop.capture_screenshot",
    "desktop.screenshot",
    "input.read_clipboard",
    "ocr.read",
    "password.capture",
    "system.read_clipboard",
}
FORBIDDEN_EVIDENCE_CAPTURE_MARKERS = (
    "capture_page",
    "clipboard",
    "cookie",
    "ocr",
    "page_contents",
    "page_content",
    "page_html",
    "page_source",
    "page_text",
    "password",
    "screenshot",
)
FORBIDDEN_DEFAULT_EVIDENCE_TERMS = (
    "clipboard contents",
    "cookie",
    "cookies",
    "page contents",
    "page_content",
    "password",
    "screenshot",
)


def test_workspace_templates_are_bundled() -> None:
    assert {path.stem for path in TEMPLATE_PATHS} == TEMPLATE_IDS
    for path in TEMPLATE_PATHS:
        assert path.exists()


def test_helpdesk_template_set_is_complete() -> None:
    assert HELPDESK_TEMPLATE_IDS == {
        "browser_admin_console_workspace",
        "collect_basic_diagnostics",
        "lab_classroom_setup",
        "meeting_audio_troubleshooting",
        "support_triage_workspace",
        "vendor_app_configuration_placeholder",
    }


def test_workspace_templates_validate_and_dry_run_without_side_effects() -> None:
    for path in TEMPLATE_PATHS:
        recipe = load_recipe(path)
        fakes = FakeAdapters()
        confirmations: list[str] = []

        summary = WorkflowExecutor(
            adapters=fakes.bundle(),
            dry_run=True,
            confirmer=lambda prompt: confirmations.append(str(prompt)) or False,
        ).run(recipe)

        assert recipe.id == path.stem
        assert summary.success
        assert len(summary.results) == len(recipe.execution_steps)
        assert [result.status for result in summary.results] == ["dry-run"] * len(
            recipe.execution_steps
        )
        assert fakes.shell.calls == []
        assert fakes.browser.calls == []
        assert fakes.window.calls == []
        assert fakes.desktop.calls == []
        assert fakes.input.calls == []
        assert confirmations == []


def test_workspace_templates_use_variables_for_paths_and_urls() -> None:
    for path in TEMPLATE_PATHS:
        raw = read_recipe_document(path)
        variables = raw["variables"]

        for step in _all_steps(raw):
            action = step["action"]
            if action == "app.launch":
                variable_name = _template_reference(step["command"])
                assert variable_name in variables
                assert variable_name.endswith("_path")
                for arg in step.get("args", []):
                    assert _template_reference(arg) in variables
            if action == "browser.open":
                variable_name = _template_reference(step["url"])
                assert variable_name in variables
                assert variable_name.endswith("_url")
            if action in {"assert.file_exists", "assert.path_exists"}:
                assert _template_reference(step["path"]) in variables


def test_templates_provide_doctor_friendly_variable_hints() -> None:
    for path in TEMPLATE_PATHS:
        raw = read_recipe_document(path)
        variables = raw["variables"]
        environment = raw.get("environment") or {}
        hints = environment.get("variable_hints") or {}

        assert environment.get("required_capabilities")
        assert set(variables) <= set(hints)


def test_workspace_templates_keep_risky_actions_behind_confirmation() -> None:
    for path in TEMPLATE_PATHS:
        recipe = load_recipe(path)

        assert recipe.steps[0].action == "confirm.ask"
        for step in recipe.steps[1:]:
            if step.requires_confirmation:
                assert step.action in {"app.launch", "browser.open"}


def test_workspace_templates_avoid_disallowed_content() -> None:
    for path in TEMPLATE_PATHS:
        raw = read_recipe_document(path)
        text = path.read_text(encoding="utf-8").casefold()
        actions = {step["action"] for step in _all_steps(raw)}

        assert actions <= ALLOWED_TEMPLATE_ACTIONS
        assert "secret" not in text
        assert "token" not in text
        for term in FORBIDDEN_DEFAULT_EVIDENCE_TERMS:
            assert term not in text
        assert "desktop.click_text" not in text
        assert "desktop.click_text" not in actions


def test_sample_recipes_do_not_use_forbidden_evidence_capture_actions() -> None:
    for path in SAMPLE_RECIPE_PATHS:
        raw = read_recipe_document(path)
        for step in _all_steps(raw):
            action = step["action"]
            normalized_action = _normalized_action_name(action)

            assert action not in FORBIDDEN_EVIDENCE_CAPTURE_ACTIONS
            assert not any(
                marker in normalized_action
                for marker in FORBIDDEN_EVIDENCE_CAPTURE_MARKERS
            )


def _all_steps(raw: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        step
        for section in ("preflight", "steps", "verify")
        for step in raw.get(section, [])
    ]


def _template_reference(value: str) -> str:
    match = TEMPLATE_REF_RE.fullmatch(value)
    assert match is not None
    return match.group(1)


def _normalized_action_name(action: str) -> str:
    return action.casefold().replace(".", "_").replace("-", "_")
