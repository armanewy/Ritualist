from __future__ import annotations

from importlib.resources import files
from pathlib import Path

import yaml


def test_windows_build_script_targets_home_onedir_bundle():
    script = Path("scripts/build_windows_app.ps1").read_text(encoding="utf-8")

    assert "--onedir" in script
    assert "--windowed" in script
    assert '"Ritualist"' in script
    assert "ritualist\\desktop_entry.py" in script
    assert "--collect-submodules" in script
    assert "ritualist.actions" in script
    assert "ritualist.adapters" in script
    assert "ritualist.canvas" in script
    assert "ritualist.home" in script
    assert "ritualist.ui" in script
    assert "--hidden-import" in script
    assert "ritualist.home.confirmation" in script
    assert "--collect-data" in script
    assert "ritualist.canvas.qml" in script
    assert "ritualist.sample_canvases" in script
    assert "ritualist.home.qml" in script
    assert "ritualist.sample_recipes" in script
    assert "--add-data" in script
    assert "themes;themes" in script
    assert "dist\\Ritualist\\Ritualist.exe" in script


def test_package_data_includes_home_canvas_qml_and_sample_templates():
    qml = files("ritualist.home.qml").joinpath("Home.qml")
    canvas_qml = files("ritualist.canvas.qml").joinpath("CanvasUse.qml")
    sample_names = {
        child.name
        for child in files("ritualist.sample_recipes").iterdir()
        if child.name.endswith(".yaml")
    }
    canvas_names = {
        child.name
        for child in files("ritualist.sample_canvases").iterdir()
        if child.name.endswith(".yaml")
    }
    paper_theme = Path("themes/ritualist-paper/theme.yaml")

    assert qml.is_file()
    assert "ritualistHomeController" in qml.read_text(encoding="utf-8")
    assert canvas_qml.is_file()
    assert "ritualistCanvasUseController" in canvas_qml.read_text(encoding="utf-8")
    assert {
        "gaming_mode.yaml",
        "coding_mode.yaml",
        "meeting_mode.yaml",
        "research_mode.yaml",
        "streaming_mode.yaml",
        "support_triage_workspace.yaml",
        "collect_basic_diagnostics.yaml",
        "browser_admin_console_workspace.yaml",
    }.issubset(sample_names)
    assert {
        "focus_room.yaml",
        "gaming_desktop.yaml",
        "helpdesk_desktop.yaml",
        "minimal_desktop.yaml",
        "project_room.yaml",
    }.issubset(canvas_names)
    assert paper_theme.is_file()
    assert "ritualist.paper" in paper_theme.read_text(encoding="utf-8")


def test_ci_optional_deps_cover_home_and_perf_smokes():
    workflow = yaml.safe_load(Path(".github/workflows/test.yml").read_text(encoding="utf-8"))

    jobs = workflow["jobs"]
    assert {"test", "windows-optional-deps-smoke", "optional-deps-gui-home"}.issubset(jobs)

    optional_job = jobs["optional-deps-gui-home"]
    assert optional_job["env"]["QT_QPA_PLATFORM"] == "offscreen"
    optional_steps = "\n".join(str(step.get("run", "")) for step in optional_job["steps"])
    assert 'python -m pip install -e ".[all,dev]"' in optional_steps
    assert "python -m pytest -q" in optional_steps
    assert "python -m compileall -q ritualist tests" in optional_steps
    assert "python -m ritualist home --help" in optional_steps
    assert "python -m ritualist pack --help" in optional_steps
    assert "python -m ritualist perf home-model --mock-cards 100 --json" in optional_steps
    assert "python -m ritualist perf home-model --mock-cards 300 --json" in optional_steps

    windows_steps = "\n".join(
        str(step.get("run", "")) for step in jobs["windows-optional-deps-smoke"]["steps"]
    )
    assert "python -m ritualist home --help" in windows_steps
    assert "python -m ritualist pack --help" in windows_steps


def test_release_checklist_documents_home_dogfood_commands():
    checklist = Path("RELEASE_CHECKLIST.md").read_text(encoding="utf-8")

    assert 'python -m pip install -e ".[all,dev]"' in checklist
    assert "python -m playwright install chromium" in checklist
    assert "python -m ritualist doctor gaming_mode --json --no-strict" in checklist
    assert "python -m ritualist dry-run gaming_mode" in checklist
    assert "python -m ritualist home --help" in checklist
    assert "python -m ritualist perf home-model --mock-cards 100 --json" in checklist
    assert "python -m ritualist perf home-model --mock-cards 300 --json" in checklist
    assert "python -m ritualist pack export gaming_mode --out $packPath" in checklist
    assert "python -m ritualist pack import $packPath" in checklist
