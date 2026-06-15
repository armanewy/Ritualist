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

    def missing_gui() -> None:
        raise DependencyMissingError("GUI requires PySide6; install ritualist[gui]")

    monkeypatch.setattr(desktop_entry, "_run_gui", missing_gui)
    monkeypatch.setattr(desktop_entry, "_show_error_dialog", messages.append)

    assert desktop_entry.main() == 1
    assert messages == ["GUI requires PySide6; install ritualist[gui]"]
    assert "ritualist[gui]" in capsys.readouterr().err
