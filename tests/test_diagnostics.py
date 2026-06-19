from __future__ import annotations

import sys

from setpiece import diagnostics


def test_collect_diagnostics_includes_packaged_app_fields(monkeypatch, tmp_path):
    monkeypatch.setattr(diagnostics, "app_data_path", lambda: tmp_path / "data")
    monkeypatch.setattr(diagnostics, "config_path", lambda: tmp_path / "data" / "config")
    monkeypatch.setattr(diagnostics, "logs_path", lambda: tmp_path / "logs")
    monkeypatch.setattr(diagnostics, "runs_path", lambda: tmp_path / "data" / "runs")
    monkeypatch.setattr(
        diagnostics,
        "browser_profiles_path",
        lambda: tmp_path / "data" / "browser-profiles",
    )
    monkeypatch.setattr(diagnostics.Path, "cwd", lambda: tmp_path)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "_internal"), raising=False)

    rows = {item.name: item.value for item in diagnostics.collect_diagnostics()}

    assert rows["App version"]
    assert rows["PyInstaller bundle"] == "yes"
    assert rows["App data directory"] == str(tmp_path / "data")
    assert rows["Config directory"] == str(tmp_path / "data" / "config")
    assert rows["Logs directory"] == str(tmp_path / "logs")
    assert rows["Runs directory"] == str(tmp_path / "data" / "runs")
    assert rows["Browser profiles directory"] == str(tmp_path / "data" / "browser-profiles")
    assert rows["Python executable"]
    assert rows["Current working directory"] == str(tmp_path)
    assert rows["Playwright import"] in {"available", "missing"}
    assert rows["PySide6 import"] in {"available", "missing"}
    assert rows["Windows UI Automation dependencies"]


def test_format_diagnostics_is_copyable_text():
    text = diagnostics.format_diagnostics(
        [diagnostics.DiagnosticItem("PyInstaller bundle", "no")]
    )

    assert text == "PyInstaller bundle: no"
