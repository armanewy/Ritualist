from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from ritualist.cli import app
from ritualist.policy import build_policy_report_for_plan
from ritualist.primitive_runtime import FORBIDDEN_DIAGNOSTIC_CLASSES, run_read_only_primitive
from ritualist.primitives import PrimitivePlan, PrimitivePlanStep, PrimitiveRisk


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "primitive_contracts"


def test_primitives_json_matches_semantic_contract() -> None:
    contract = _load_contract("primitives_json_contract.json")
    payload = _cli_json(["primitives", "--json"])

    assert isinstance(payload, list)
    assert [entry["primitive_id"] for entry in payload] == sorted(
        entry["primitive_id"] for entry in payload
    )
    observed_risks = {risk for entry in payload for risk in [entry["risk"]]}
    assert observed_risks <= set(contract["known_risk_values"])
    assert observed_risks >= set(contract["required_present_risk_values"])
    by_id = {entry["primitive_id"]: entry for entry in payload}
    assert set(contract["required_read_only_primitive_ids"]) <= set(by_id)

    for entry in payload:
        assert set(contract["required_top_level_fields"]) <= set(entry)
        assert set(contract["adapter_binding_fields"]) <= set(entry["adapter_binding"])
        for parameter in entry["parameters"]:
            assert set(contract["parameter_fields"]) <= set(parameter)

    for primitive_id, expected in contract["representative_primitives"].items():
        entry = by_id[primitive_id]
        assert entry["risk"] == expected["risk"]
        assert entry["adapter_binding"]["adapter_id"] == expected["adapter_id"]
        if "confirmation_policy" in expected:
            assert entry["confirmation_policy"] == expected["confirmation_policy"]
        if "allowed_in_imported_packs" in expected:
            assert entry["allowed_in_imported_packs"] is expected["allowed_in_imported_packs"]
        if "required_capabilities" in expected:
            assert entry["required_capabilities"] == expected["required_capabilities"]
        if "supported_platforms" in expected:
            assert entry["supported_platforms"] == expected["supported_platforms"]


def test_policy_show_json_matches_semantic_contract() -> None:
    contract = _load_contract("policy_show_json_contract.json")
    payload = _cli_json(["policy", "show", "--json"])

    assert set(contract["required_top_level_fields"]) <= set(payload)
    assert payload["schema_version"] == contract["schema_version"]
    assert payload["default_profile"] == contract["default_profile"]
    assert payload["categories"] == contract["categories"]
    assert payload["decisions"] == contract["decisions"]
    assert set(contract["profiles"]) <= set(payload["profiles"])
    assert payload["risk_defaults"] == contract["risk_defaults"]
    assert set(contract["never_importable_classes"]) <= set(payload["never_importable_classes"])


def test_actions_json_matches_semantic_contract() -> None:
    contract = _load_contract("actions_json_contract.json")
    payload = _cli_json(["actions", "--json"])

    assert isinstance(payload, list)
    assert [entry["action_name"] for entry in payload] == sorted(
        entry["action_name"] for entry in payload
    )
    by_name = {entry["action_name"]: entry for entry in payload}
    observed_side_effects = {entry["side_effect_level"] for entry in payload}
    assert observed_side_effects <= set(contract["known_side_effect_values"])
    assert observed_side_effects >= set(contract["required_present_side_effect_values"])
    for entry in payload:
        assert set(contract["required_top_level_fields"]) <= set(entry)
        assert entry["action"] == entry["action_name"]
        assert entry["platform_support"] == entry["supported_platforms"]

    for action_name, expected in contract["representative_actions"].items():
        entry = by_name[action_name]
        assert entry["side_effect_level"] == expected["side_effect_level"]
        assert entry["allowed_in_imported_packs"] is expected["allowed_in_imported_packs"]
        if "confirmation_policy" in expected:
            assert entry["confirmation_policy"] == expected["confirmation_policy"]
        assert entry["required_capabilities"] == expected["required_capabilities"]


def test_gaming_mode_doctor_json_matches_semantic_contract(monkeypatch, tmp_path: Path) -> None:
    contract = _load_contract("doctor_gaming_mode_json_contract.json")

    monkeypatch.setattr("ritualist.doctor.sys.platform", "linux")
    monkeypatch.setattr("ritualist.doctor.browser_profiles_dir", lambda: tmp_path / "profiles")

    payload = _cli_json(["doctor", str(_gaming_mode_sample_path()), "--json", "--no-strict"])

    assert set(contract["required_top_level_fields"]) <= set(payload)
    assert payload["schema_version"] == contract["schema_version"]
    assert payload["recipe_id"] == contract["recipe_id"]
    assert payload["recipe_name"] == contract["recipe_name"]
    assert set(contract["compatibility_fields"]) <= set(payload["compatibility"])
    assert payload["compatibility"]["status"] in {
        "compatible",
        "compatible_with_warnings",
        "incompatible",
    }
    assert payload["checks"]
    for check in payload["checks"]:
        assert set(contract["required_check_fields"]) <= set(check)
    assert set(contract["required_action_names"]) <= {
        action["action_name"] for action in payload["actions"]
    }
    assert set(contract["required_primitive_ids"]) <= {
        primitive["primitive_id"] for primitive in payload["primitives"]
    }
    assert set(contract["required_capabilities"]) <= {
        capability["id"] for capability in payload["capabilities"]
    }
    assert set(contract["required_environment_fields"]) <= set(payload["environment"])
    assert payload["environment"]["expected_os"] == ["windows"]


def test_primitive_plan_policy_report_matches_semantic_contract() -> None:
    contract = _load_contract("primitive_plan_policy_report_contract.json")
    plan = PrimitivePlan(
        plan_id="contract_plan",
        steps=(
            PrimitivePlanStep("diagnostics.bundle.collect_minimal"),
            PrimitivePlanStep(
                "uia.element.click_text",
                action_name="desktop.click_text",
                step_name="Click Play",
                parameters={"text": "Play"},
                risk=PrimitiveRisk.RISKY,
            ),
        ),
    )

    payload = build_policy_report_for_plan(
        plan,
        imported=True,
        private_or_local=False,
    ).to_dict()

    assert set(contract["required_top_level_fields"]) <= set(payload)
    assert payload["schema_version"] == contract["schema_version"]
    assert payload["profile"] == contract["profile"]
    assert payload["allowed"] is False
    assert payload["blocked_count"] == 1
    by_id = {finding["primitive_id"]: finding for finding in payload["findings"]}
    for finding in payload["findings"]:
        assert set(contract["required_finding_fields"]) <= set(finding)
    for primitive_id, expected in contract["representative_findings"].items():
        finding = by_id[primitive_id]
        assert finding["category"] == expected["category"]
        assert finding["decision"] == expected["decision"]
        assert finding["risk"] == expected["risk"]
        assert finding["blocked"] is expected["blocked"]


def test_read_only_primitive_reports_match_semantic_contract(tmp_path: Path) -> None:
    contract = _load_contract("read_only_primitive_report_contract.json")

    dry_run = run_read_only_primitive(
        "hardware.inventory.snapshot",
        dry_run=True,
        parameters={"secret_token": "value"},
    ).to_dict()
    _assert_result_contract(dry_run, contract)
    assert dry_run["status"] == contract["dry_run"]["status"]
    assert dry_run["verification"]["status"] == contract["dry_run"]["verification_status"]
    assert set(contract["dry_run"]["details_fields"]) <= set(dry_run["details"])
    assert dry_run["details"]["parameters"]["secret_token"] == "[redacted]"

    execution = run_read_only_primitive(
        "diagnostics.bundle.collect_minimal",
        parameters={"output_dir": str(tmp_path)},
    ).to_dict()
    _assert_result_contract(execution, contract)
    assert execution["status"] in contract["execution"]["allowed_statuses"]
    assert execution["verification"]["status"] in contract["execution"]["verification_statuses"]
    for artifact in execution["artifacts"]:
        assert set(contract["diagnostics_artifact_fields"]) <= set(artifact)
        assert artifact["redacted"] is True
    assert set(contract["forbidden_secret_classes"]) == set(FORBIDDEN_DIAGNOSTIC_CLASSES)
    assert set(contract["forbidden_secret_classes"]) <= set(
        execution["details"]["redaction_summary"]["forbidden_classes_excluded"]
    )


def _assert_result_contract(payload: dict[str, object], contract: dict[str, object]) -> None:
    assert set(contract["required_result_fields"]) <= set(payload)
    assert payload["verification"] is not None
    assert set(contract["required_verification_fields"]) <= set(payload["verification"])
    assert isinstance(payload["artifacts"], list)
    assert isinstance(payload["details"], dict)


def _cli_json(args: list[str]) -> object:
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def _load_contract(name: str) -> dict[str, object]:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _gaming_mode_sample_path() -> Path:
    return Path(__file__).resolve().parents[1] / "ritualist" / "sample_recipes" / "gaming_mode.yaml"
