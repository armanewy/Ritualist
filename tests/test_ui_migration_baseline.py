from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "setpiece_ui_baseline.ps1"
SPEC_PATH = REPO_ROOT / "tests" / "acceptance" / "ui_migration_baseline.yaml"

EXPECTED_SURFACES = {
    "home",
    "gaming_room",
    "active_running",
    "waiting",
    "confirmation",
    "blocked",
    "failed",
    "interrupted_history",
    "settings_privacy_disclosure",
}


def _powershell() -> str | None:
    return shutil.which("powershell") or shutil.which("pwsh")


def _external_or_repo_artifacts_tmp_dir(tmp_path: Path, name: str) -> Path:
    candidate = tmp_path / name
    try:
        candidate.relative_to(REPO_ROOT)
    except ValueError:
        return candidate
    return Path(tempfile.mkdtemp(prefix=f"setpiece-{name}-")) / name


def test_ui_migration_baseline_spec_declares_before_state_contract() -> None:
    spec = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))

    assert spec["schema"] == "setpiece.ui_migration_baseline.v1"
    assert spec["baseline_head"] == "4789b4c1b1795b89d91d109050c9153b9e41f13a"
    assert spec["scope"] == "current_before_state_only"
    assert "before-state only" in spec["product_goal_note"]
    assert set(spec["semantics"]) == {"CAPTURED", "NOT_CAPTURED", "NEEDS_HUMAN_REVIEW", "FAIL"}
    assert "PASS" not in spec["semantics"]
    assert spec["truth_model"]["human_usability_pass"] == "NOT_RUN"
    assert spec["truth_model"]["release_pass"] is False
    assert spec["truth_model"]["ux_pass_assigned"] is False
    assert spec["requested_scales"] == [100, 125, 150]
    assert spec["dpi_policy"]["switching_allowed"] is False
    assert spec["dpi_policy"]["missing_scale_capture_status"] == "NOT_CAPTURED"
    assert {surface["id"] for surface in spec["surfaces"]} == EXPECTED_SURFACES

    for key in (
        "baseline_summary_json",
        "baseline_summary_md",
        "screenshots_dir",
        "process_tree_json",
        "window_tree_json",
    ):
        assert key in spec["artifact_contract"]

    for observation in (
        "process_tree_after_launch",
        "window_tree",
        "visible_window_count",
        "taskbar_entries_where_observable",
        "alt_tab_entries_where_observable",
        "home_remains_open_after_room_launch",
        "spawned_process_count",
        "clipped_or_overlapping_controls",
        "leaked_internal_ids",
        "selected_theme",
        "minimum_window_sizes",
        "actual_window_sizes",
    ):
        assert observation in spec["required_observations"]


def test_ui_migration_baseline_script_declares_artifact_and_state_contracts() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    for expected in (
        "baseline-summary.json",
        "baseline-summary.md",
        "screenshots",
        "window-tree.json",
        "process-tree.json",
        "setpiece.ui_migration_baseline_summary.v1",
        "current_before_state_only",
        "Legacy surfaces are recorded factually as before-state only",
        "CAPTURED",
        "NOT_CAPTURED",
        "NEEDS_HUMAN_REVIEW",
        "no_ux_pass_assigned",
        "human_usability_pass",
        "release_pass",
        "home_remains_open_after_room_launch",
        "spawned_process_count",
        "clipped_or_overlapping_controls",
        "leaked_internal_ids",
        "selected_theme",
        "minimum_window_sizes",
        "actual_window_sizes",
        "Open in Window",
        "--room",
        "gaming",
        "SETPIECE_E2E",
        "SETPIECE_E2E_ARTIFACT_DIR",
    ):
        assert expected in script

    for surface in EXPECTED_SURFACES:
        assert f'id = "{surface}"' in script


def test_ui_migration_baseline_requires_explicit_packaged_screenshot_opt_in(tmp_path: Path) -> None:
    shell = _powershell()
    if shell is None:
        pytest.skip("PowerShell is not available")

    evidence_dir = _external_or_repo_artifacts_tmp_dir(tmp_path, "ui-baseline")
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
    assert "requires explicit packaged desktop evidence opt-in" in output
    assert "-Packaged -IUnderstandThisCapturesDesktop" in output
    assert "does not use coordinate clicks" in output
    assert not evidence_dir.exists()


def test_ui_migration_baseline_missing_packaged_app_marks_not_captured(tmp_path: Path) -> None:
    shell = _powershell()
    if shell is None:
        pytest.skip("PowerShell is not available")

    evidence_dir = _external_or_repo_artifacts_tmp_dir(tmp_path, "ui-baseline")
    missing_exe = tmp_path / "missing" / "Setpiece.exe"
    result = subprocess.run(
        [
            shell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT_PATH),
            "-Packaged",
            "-IUnderstandThisCapturesDesktop",
            "-EvidenceDir",
            str(evidence_dir),
            "-ExecutablePath",
            str(missing_exe),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads((evidence_dir / "baseline-summary.json").read_text(encoding="utf-8"))
    assert summary["schema_version"] == "setpiece.ui_migration_baseline_summary.v1"
    assert summary["packaged"]["executable_exists"] is False
    assert summary["safety"]["no_ux_pass_assigned"] is True
    assert summary["truth_model"]["human_usability_pass"] == "NOT_RUN"
    assert summary["truth_model"]["release_pass"] is False
    assert {surface["id"] for surface in summary["surfaces"]} == EXPECTED_SURFACES
    assert {surface["status"] for surface in summary["surfaces"]} == {"NOT_CAPTURED"}
    assert "PASS" not in {surface["status"] for surface in summary["surfaces"]}
    assert summary["dpi"]["requested_scale_percents"] == [100, 125, 150]
    assert summary["dpi"]["switching_attempted"] is False
    assert (evidence_dir / "process-tree.json").exists()
    assert (evidence_dir / "window-tree.json").exists()
    assert (evidence_dir / "baseline-summary.md").exists()


def test_ui_migration_baseline_script_avoids_forbidden_desktop_automation_primitives() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8").casefold()

    for forbidden in (
        "setcursorpos",
        "mouse_event",
        "keybd_event",
        "sendkeys",
        "sendinput",
        "start-process powershell",
        "invoke-expression",
    ):
        assert forbidden not in script

    assert "invoke_pattern" not in script
    assert "coordinate clicks" in script
    assert "screenshot_capture_scope" in script
