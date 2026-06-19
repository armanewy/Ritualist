from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "setpiece_live_gaming_acceptance.ps1"
SPEC_PATH = REPO_ROOT / "tests" / "acceptance" / "live_gaming_v0_2_alpha_1.yaml"
DOC_PATH = REPO_ROOT / "docs" / "LIVE_GAMING_ACCEPTANCE.md"


EXPECTED_CASE_IDS = {
    "battlenet_absent",
    "login_required",
    "install_visible",
    "locate_game_visible",
    "update_visible",
    "play_visible_disabled",
    "play_enabled",
    "target_disappears_after_approval",
    "diablo_already_running",
    "approved_play_succeeds",
    "postcondition_fails",
    "native_browser_handoff",
    "managed_browser_selected",
    "managed_media_starts",
    "managed_media_stalls",
    "optional_ambience_failure",
    "no_premature_minimize",
}


def test_live_gaming_acceptance_spec_declares_live_cases_and_safety() -> None:
    spec = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))

    assert spec["schema"] == "setpiece.live_gaming_acceptance.v1"
    assert spec["release"] == "v0.2.0-alpha.1"
    assert spec["scope"] == "live_integration_only"
    assert set(spec["semantics"]) == {"PASS", "FAIL", "NEEDS_HUMAN_REVIEW", "NOT_RUN"}
    assert {case["id"] for case in spec["cases"]} == EXPECTED_CASE_IDS
    assert "Never enters credentials." in spec["safety_contract"]
    assert "Never installs, locates, or updates the game." in spec["safety_contract"]
    assert "Never automates gameplay." in spec["safety_contract"]

    for case in spec["cases"]:
        assert case["expected_evidence"]
        assert case["pass_when"]


def test_live_gaming_acceptance_script_requires_explicit_live_opt_in(tmp_path: Path) -> None:
    shell = shutil.which("powershell") or shutil.which("pwsh")
    if shell is None:
        pytest.skip("PowerShell is not available")

    evidence_dir = tmp_path / "live"
    result = subprocess.run(
        [
            shell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT_PATH),
            "-EvidenceDir",
            str(evidence_dir),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    output = re.sub(r"\x1b\[[0-9;]*m", "", f"{result.stdout}\n{result.stderr}")
    assert result.returncode == 2
    assert "requires explicit user initiation" in output
    assert "-Live -IUnderstandThisIsLive" in output
    assert "never enters credentials" in output
    assert not evidence_dir.exists()


def test_live_gaming_acceptance_script_declares_evidence_contract() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    for expected in (
        "live-gaming-summary.json",
        "live-gaming-summary.md",
        "setpiece.live_gaming_acceptance_summary.v1",
        "live_integration_only",
        "live_integration_pass",
        "Fixture acceptance is not live integration",
        "process-tree.json",
        "window-tree.json",
        "battlenet-uia-tree.json",
        "runs-no-repair",
        "UIAutomationClient",
        "ControlType.ProgrammaticName",
        "IsEnabled",
        "IsOffscreen",
        "selected_branch",
        "confirmation_suppressed",
        "confirmation_shown",
        "invocation_result",
        "process_window_postcondition",
        "screenshot_or_short_clip",
        "human_notes",
    ):
        assert expected in script


def test_live_gaming_acceptance_script_avoids_forbidden_mutating_primitives() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8").casefold()

    for forbidden in (
        "setcursorpos",
        "mouse_event",
        "sendkeys",
        "install game",
        "update game",
        "locate game",
        "enter password",
        "start gameplay",
        "ocr",
        "record watch me",
    ):
        assert forbidden not in script

    assert "start-process" in script
    assert "python" in script
    assert "--no-repair" in script


def test_live_gaming_acceptance_docs_state_fixture_is_not_live() -> None:
    docs = DOC_PATH.read_text(encoding="utf-8")

    assert "Fixture acceptance is not live integration" in docs
    assert "v0.2.0-alpha.1` is not taggable from fixture acceptance alone" in docs
    assert ".\\scripts\\setpiece_live_gaming_acceptance.ps1" in docs
    assert "-Live -IUnderstandThisIsLive" in docs
