from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from ritualist.cli import app
from ritualist.intent_planner import (
    IntentSpec,
    build_plan_doctor_report,
    compile_intent_to_plan,
    compile_plan_reference,
    compile_recipe_to_plan,
)
from ritualist.models import Recipe


def test_diagnostics_intent_compiles_to_read_only_diagnostics_plan() -> None:
    intent = IntentSpec(
        intent_id="collect_minimal",
        kind="diagnostics.collect",
        display_name="Collect diagnostics",
        requested_outcome="Collect minimal diagnostics.",
        constraints={"preset": "minimal"},
    )

    plan = compile_intent_to_plan(intent)

    assert plan.required_primitives == ("diagnostics.bundle.collect_minimal",)
    assert plan.required_capabilities == ("diagnostics_collect",)
    assert plan.risk_summary == {"read_only": 1}
    assert plan.artifacts_expected == (
        "JSON report",
        "text summary",
        "zip bundle",
        "checksums",
        "redaction summary",
    )


def test_workspace_intent_compiles_to_launch_and_window_primitives() -> None:
    intent = IntentSpec(
        intent_id="workspace",
        kind="workspace.prepare",
        display_name="Prepare workspace",
        requested_outcome="Launch app and focus window.",
        risk_budget="controls_ui",
        target={
            "apps": [{"name": "Open vendor app", "command": "vendor.exe"}],
            "windows": [{"title_contains": "Vendor", "focus": True}],
        },
    )

    plan = compile_intent_to_plan(intent)

    assert [step.primitive_id for step in plan.steps] == [
        "app.process.launch",
        "window.topology.wait",
        "window.topology.focus",
    ]
    assert plan.unresolved_questions == ()
    assert plan.risk_summary == {"controls_ui": 1, "launches_app": 1, "read_only": 1}


def test_unknown_intent_reports_unresolved_questions() -> None:
    intent = IntentSpec(
        intent_id="unknown",
        kind="vendor.magic",
        requested_outcome="Do a thing.",
    )

    plan = compile_intent_to_plan(intent)

    assert plan.steps == ()
    assert plan.unresolved_questions == ("no deterministic compiler rule for intent kind 'vendor.magic'",)


def test_plan_doctor_reports_blocked_primitive_policy() -> None:
    recipe = Recipe.model_validate(
        {
            "id": "risky",
            "name": "Risky",
            "steps": [
                {
                    "action": "desktop.click_text",
                    "window_title_contains": "Battle.net",
                    "text": "Play",
                    "requires_confirmation": True,
                }
            ],
        }
    )
    plan = compile_recipe_to_plan(recipe)

    report = build_plan_doctor_report(plan)
    data = report.to_dict()

    assert any(
        finding["primitive_id"] == "uia.element.click_text" and finding["blocked"] is True
        for finding in data["policy"]["findings"]
    )
    assert any(check["category"] == "Policy" and check["status"] == "error" for check in data["checks"])


def test_plan_preview_json_has_stable_shape() -> None:
    result = CliRunner().invoke(app, ["plan", "preview", "diagnostics.collect", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert set(data) == {"schema_version", "plan", "doctor"}
    assert data["schema_version"] == "intent.plan_preview.v1"
    assert data["plan"]["intent"]["kind"] == "diagnostics.collect"
    assert data["plan"]["required_primitives"] == ["diagnostics.bundle.collect_minimal"]
    assert data["doctor"]["schema_version"] == "intent.plan_doctor.v1"


def test_plan_preview_path_supports_intent_yaml(tmp_path: Path) -> None:
    intent_path = tmp_path / "intent.yaml"
    intent_path.write_text(
        """
intent_id: support_bundle
kind: diagnostics.collect
display_name: Support bundle
requested_outcome: Collect support diagnostics.
constraints:
  preset: support
""".lstrip(),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["plan", "preview", str(intent_path), "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["plan"]["required_primitives"] == ["diagnostics.bundle.collect_support"]


def test_plan_preview_recipe_lookup_does_not_create_user_recipe_dir(
    tmp_path: Path,
    monkeypatch,
) -> None:
    recipe_root = tmp_path / "recipes"
    monkeypatch.setattr("ritualist.intent_planner.recipes_path", lambda: recipe_root)

    plan = compile_plan_reference("diagnostics.collect")

    assert plan.intent["kind"] == "diagnostics.collect"
    assert not recipe_root.exists()


def test_plan_preview_does_not_call_runtime_or_adapters(monkeypatch) -> None:
    def fail_adapter_creation():
        raise AssertionError("plan preview must not create runtime adapters")

    def fail_executor(*_args, **_kwargs):
        raise AssertionError("plan preview must not create workflow executor")

    monkeypatch.setattr("ritualist.cli.create_default_adapters", fail_adapter_creation)
    monkeypatch.setattr("ritualist.cli.WorkflowExecutor", fail_executor)

    result = CliRunner().invoke(app, ["plan", "preview", "diagnostics.collect", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["plan"]["plan_steps"][0]["primitive_id"] == "diagnostics.bundle.collect_minimal"


def test_recipe_preview_compiles_existing_recipe_steps_without_execution() -> None:
    recipe = Recipe.model_validate(
        {
            "id": "runbook",
            "name": "Runbook",
            "steps": [
                {"action": "browser.open", "url": "https://example.test"},
                {"action": "wait.seconds", "seconds": 1},
            ],
        }
    )

    plan = compile_recipe_to_plan(recipe)

    assert [step.primitive_id for step in plan.steps] == [
        "browser.session.open",
        "runtime.wait.seconds",
    ]
    assert "playwright" in plan.required_capabilities
    assert plan.rollback_or_cleanup_notes == (
        "Preview does not launch apps, click UI, mutate files, or run shell commands.",
    )


def test_plan_doctor_reports_missing_recipe_variables(tmp_path: Path) -> None:
    recipe_path = tmp_path / "missing_var.yaml"
    recipe_path.write_text(
        """
version: "0.1"
id: missing_var
name: Missing Var
steps:
  - action: app.launch
    command: "${app_path}"
""".lstrip(),
        encoding="utf-8",
    )

    plan = compile_plan_reference(recipe_path)
    report = build_plan_doctor_report(plan)
    data = report.to_dict()

    assert "missing variable 'app_path'" in plan.unresolved_questions
    assert data["compatibility"]["status"] == "incompatible"
    assert any(
        check["category"] == "Variables" and "missing variable 'app_path'" in check["message"]
        for check in data["checks"]
    )
