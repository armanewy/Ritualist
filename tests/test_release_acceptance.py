from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = REPO_ROOT / "tests" / "acceptance" / "release_v0_2_alpha_1.yaml"
SCRIPT_PATH = REPO_ROOT / "scripts" / "ritualist_release_acceptance.ps1"

EXPECTED_CHECK_IDS = {
    "packaged_home_visible",
    "packaged_canvas_visible",
    "packaged_classic_gui_visible",
    "gaming_desktop_renders",
    "expected_canvas_components_appear",
    "ritual_card_doctor",
    "ritual_card_dry_run",
    "safe_ritual_card_run",
    "ritual_status_updates",
    "ritual_controller_pause_resume_stop",
    "target_card_preview",
    "recent_activity_updates",
    "native_confirmation_z_order",
    "declining_play_stopped",
    "show_run_declined_confirmation",
    "hard_kill_repairs_interrupted",
    "no_recording_or_preview_capture",
    "canvas_theme_pack_import_export_no_autorun",
    "arbitrary_component_code_rejected",
    "component_perf_100_300_recorded",
    "ui_heartbeat_no_obvious_freeze",
}


def test_release_acceptance_spec_lists_current_manual_blockers() -> None:
    spec = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))

    assert spec["schema"] == "ritualist.release_acceptance.v1"
    assert spec["release"] == "v0.2.0-alpha.1"
    assert set(spec["semantics"]) == {"PASS", "FAIL", "NEEDS_HUMAN_REVIEW"}
    assert spec["artifact_contract"]["summary_json"] == (
        "artifacts/release-acceptance/acceptance-summary.json"
    )

    checks = spec["checks"]
    assert {check["id"] for check in checks} == EXPECTED_CHECK_IDS
    assert len(checks) == len(EXPECTED_CHECK_IDS)
    for check in checks:
        assert check["blocker"]
        assert check["expected_evidence"]
        assert check["pass_when"]


def test_release_acceptance_harness_declares_artifact_and_e2e_contracts() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    for expected in (
        "acceptance-summary.json",
        "acceptance-summary.md",
        "RITUALIST_E2E",
        "RITUALIST_E2E_ARTIFACT_DIR",
        "RITUALIST_E2E_APP_DATA_DIR",
        "release_v0_2_alpha_1.yaml",
        "NEEDS_HUMAN_REVIEW",
        "EvidenceDir",
        "theme_evidence",
        "theme_id",
        "theme_valid",
        "theme_accessibility_warning_count",
        "accessibility_warning_count",
        "visual_artifacts",
        "Capture-CanvasVisualArtifact",
        "Capture-CanvasEditModeVisualArtifact",
        "Find-NamedElement",
        "edit_mode_builder_visible",
        "edit-unverified",
        "review_status",
        "expected_controls",
        "missing_controls",
        "control_basis",
        "recent-activity-after-decline",
        "recent_activity_component_ids",
        "recent_activity_model",
        "Get-RecentActivityModelEvidence",
        "Get-UiHeartbeatTimingEvidence",
        "canvas.ui_heartbeat",
        "app_heartbeat_timing",
        "max_app_heartbeat_gap_ms",
        "run_history_contains_run",
        "Get-FrameTimingEvidence",
        "max_frame_gap_ms",
        "max_allowed_gap_ms",
        'ArtifactId "minimal-room"',
        'ArtifactId "gaming-room"',
        'ArtifactId "helpdesk-room"',
        "Capture-DesktopWorkAreaCanvasArtifact",
        "desktop-work-area-canvas",
        "desktop-work-area-windowed-fallback",
        "RITUALIST_CANVAS_FORCE_WINDOWED",
        "--host",
        "desktop-work-area",
        "bounds_match_work_area",
        "exit_clean",
        "forced_windowed",
        "input_policy",
        "click_through_implemented",
        "blank_area_click_through_status",
        "blank_area_click_through_machine_verified",
        "blank_area_click_through_review",
        "component_click_evidence",
        "interactive_wallpaper_fixture_input",
        "edit_mode_input_capture",
        "no_coordinate_click_automation",
        "background_passthrough",
        "background_mode",
        "Ritualist Wallpaper Fixture",
        "Start-FakeWallpaperFixture",
        "Stop-FakeWallpaperFixture",
        "fake_wallpaper_fixture",
        "wallpaper_app_processes",
        "observed_only",
        "controlled_by_ritualist",
        "dpi",
        "monitor",
        "Exit Desktop Canvas",
        '"edit-mode-builder"',
        "no_recording_or_preview_capture",
    ):
        assert expected in script

    assert "watch_me_preview_privacy" not in script


def test_release_acceptance_harness_rejects_repo_root_evidence_dir() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "artifactsRootWithSeparator" in script
    assert "repository artifacts directory" in script
    assert "$resolvedAcceptanceRoot -ne $resolvedRepoRoot" not in script


def test_release_acceptance_harness_rejects_non_artifact_repo_subdirs() -> None:
    shell = shutil.which("powershell") or shutil.which("pwsh")
    if shell is None:
        pytest.skip("PowerShell is not available")

    result = subprocess.run(
        [
            shell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT_PATH),
            "-EvidenceDir",
            "tests",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode != 0
    output = re.sub(r"\x1b\[[0-9;]*m", "", f"{result.stdout}\n{result.stderr}")
    assert "artifacts" in output
    assert "directory" in output
    assert (REPO_ROOT / "tests").is_dir()


def test_release_acceptance_harness_avoids_forbidden_input_primitives() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8").casefold()

    for forbidden in (
        "setcursorpos",
        "mouse_event",
        "sendkeys",
        "action: app.launch",
        "taskbar hiding",
        "kiosk mode",
        "stop-wallpaperengine",
        "wallpaper_engine.profile",
    ):
        assert forbidden not in script


def test_release_acceptance_harness_keeps_click_through_unverified() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert '"NEEDS_HUMAN_REVIEW"' in script
    assert "blank_area_click_through_machine_verified" in script
    assert "native per-component hit testing is not implemented" in script
    assert "does not synthesize blank-area mouse input" in script
    assert 'status = if ($exitInvoked) { "PASS" } else { "NEEDS_HUMAN_REVIEW" }' in script
