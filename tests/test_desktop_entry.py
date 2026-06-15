from __future__ import annotations

from ritualist import desktop_entry
from ritualist.errors import DependencyMissingError


def test_desktop_entry_launches_gui(monkeypatch):
    called = []
    monkeypatch.setattr(desktop_entry, "_run_gui", lambda: called.append(True))

    assert desktop_entry.main() == 0
    assert called == [True]


def test_desktop_entry_reports_gui_dependency_error(monkeypatch, capsys):
    messages = []
    logs = []

    def missing_gui() -> None:
        raise DependencyMissingError("GUI requires PySide6; install ritualist[gui]")

    monkeypatch.setattr(desktop_entry, "_run_gui", missing_gui)
    monkeypatch.setattr(desktop_entry, "_show_error_dialog", messages.append)
    monkeypatch.setattr(desktop_entry, "_write_startup_error_log", lambda *args: logs.append(args))

    assert desktop_entry.main() == 1
    assert messages == ["GUI requires PySide6; install ritualist[gui]"]
    assert logs[0][0] == "GUI requires PySide6; install ritualist[gui]"
    assert "ritualist[gui]" in capsys.readouterr().err


def test_desktop_entry_writes_startup_error_log(tmp_path, monkeypatch):
    monkeypatch.setattr("ritualist.paths.logs_dir", lambda: tmp_path)

    desktop_entry._write_startup_error_log("failed to start", "traceback details")

    text = (tmp_path / "startup-error.log").read_text(encoding="utf-8")
    assert "failed to start" in text
    assert "traceback details" in text
