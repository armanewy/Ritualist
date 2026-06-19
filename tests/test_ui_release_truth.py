from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = REPO_ROOT / "tests" / "acceptance" / "ui_release_truth.yaml"

EXPECTED_UI_GATES = {
    "shell_architecture_pass",
    "visual_contract_pass",
    "dpi_pass",
    "keyboard_accessibility_pass",
    "narrator_pass",
    "focus_lifecycle_pass",
    "human_usability_pass",
}


def _load_spec() -> dict:
    return yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))


def test_ui_release_truth_declares_all_explicit_gates() -> None:
    spec = _load_spec()

    assert spec["schema"] == "setpiece.ui_release_truth.v1"
    assert spec["baseline"]["head"] == "4789b4c1b1795b89d91d109050c9153b9e41f13a"
    assert spec["baseline"]["product_goal"]["retain_unused_legacy_behavior"] is False
    assert set(spec["status_values"]) == {"PASS", "FAIL", "NOT_RUN", "NEEDS_HUMAN_REVIEW"}
    assert set(spec["ui_gates"]) == EXPECTED_UI_GATES

    for gate in spec["ui_gates"].values():
        assert gate["status"] in spec["status_values"]
        assert gate["pass_requires"]
        assert gate["grant_policy"]["required_evidence"]


def test_human_usability_starts_not_run_and_cannot_be_machine_granted() -> None:
    spec = _load_spec()
    human_gate = spec["ui_gates"]["human_usability_pass"]
    policy = human_gate["grant_policy"]

    assert human_gate["status"] == "NOT_RUN"
    assert policy["initial_status"] == "NOT_RUN"
    assert policy["machine_structure_tests_may_grant"] is False
    assert policy["automated_tests_may_grant"] is False
    assert policy["screenshots_alone_may_grant"] is False
    assert policy["required_evidence"] == [
        "explicit_human_usability_decision",
        "usability_findings",
    ]


def test_visual_contract_requires_explicit_review_not_screenshots_alone() -> None:
    spec = _load_spec()
    visual_gate = spec["ui_gates"]["visual_contract_pass"]
    policy = visual_gate["grant_policy"]

    assert visual_gate["status"] != "PASS"
    assert policy["screenshots_alone_may_grant"] is False
    assert policy["screenshots_are_supporting_evidence"] is True
    assert policy["requires_explicit_review"] is True
    assert "explicit_visual_review_decision" in policy["required_evidence"]
    assert "reviewed_visual_artifacts" in policy["required_evidence"]


def test_release_pass_remains_false_while_human_usability_is_not_run_or_fail() -> None:
    spec = _load_spec()
    release = spec["release_decision"]
    human_status = spec["ui_gates"]["human_usability_pass"]["status"]

    assert {"NOT_RUN", "FAIL"}.issubset(set(release["human_usability_blocking_statuses"]))
    assert human_status in release["human_usability_blocking_statuses"]
    assert release["release_pass"]["passed"] is False
    assert release["release_pass"]["status"] == "NOT_RUN"
    assert release["taggable"] is False
    assert release["taggable"] == release["release_pass"]["passed"]
    assert release["taggable_is_alias_of_release_pass_passed"] is True


def test_current_f2_engine_and_simulated_acceptance_evidence_stays_valid() -> None:
    spec = _load_spec()
    baseline = spec["functionality_baseline"]

    assert baseline["source"] == "2026-06-18 Set 2 Wave F2 functionality recovery evidence"
    assert baseline["engine_tests_pass"]["status"] == "PASS"
    assert baseline["simulated_acceptance_pass"]["status"] == "PASS"
    assert baseline["live_integration_pass"]["status"] == "NOT_RUN"
    assert any(
        "artifacts/release-acceptance-set2-f2/acceptance-summary.json" == item
        for item in baseline["simulated_acceptance_pass"]["evidence"]
    )


def test_historical_taggable_claims_cannot_override_current_truth_model() -> None:
    spec = _load_spec()
    policy = spec["historical_claim_policy"]

    assert policy["taggable_claims_may_override_current_truth_model"] is False
    assert spec["release_decision"]["taggable"] is False
    for summary in policy["acceptance_summaries"]:
        assert summary["may_override_current_truth_model"] is False
