from __future__ import annotations

from importlib.resources import files
from pathlib import Path


def test_windows_build_script_targets_home_onedir_bundle():
    script = Path("scripts/build_windows_app.ps1").read_text(encoding="utf-8")

    assert "--onedir" in script
    assert "--windowed" in script
    assert '"Ritualist"' in script
    assert "ritualist\\desktop_entry.py" in script
    assert "--collect-submodules" in script
    assert "ritualist.actions" in script
    assert "ritualist.adapters" in script
    assert "ritualist.home" in script
    assert "ritualist.ui" in script
    assert "--collect-data" in script
    assert "ritualist.home.qml" in script
    assert "ritualist.sample_recipes" in script
    assert "dist\\Ritualist\\Ritualist.exe" in script


def test_package_data_includes_home_qml_and_sample_templates():
    qml = files("ritualist.home.qml").joinpath("Home.qml")
    sample_names = {
        child.name
        for child in files("ritualist.sample_recipes").iterdir()
        if child.name.endswith(".yaml")
    }

    assert qml.is_file()
    assert "ritualistHomeController" in qml.read_text(encoding="utf-8")
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
