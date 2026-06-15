from __future__ import annotations

from pathlib import Path


def test_windows_build_script_targets_gui_onedir_bundle():
    script = Path("scripts/build_windows_app.ps1").read_text(encoding="utf-8")

    assert "--onedir" in script
    assert "--windowed" in script
    assert '"Ritualist"' in script
    assert "ritualist\\desktop_entry.py" in script
    assert "--collect-submodules" in script
    assert "ritualist.actions" in script
    assert "ritualist.adapters" in script
    assert "ritualist.ui" in script
    assert "--collect-data" in script
    assert "ritualist.sample_recipes" in script
    assert "dist\\Ritualist\\Ritualist.exe" in script
