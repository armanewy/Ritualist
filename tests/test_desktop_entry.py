from __future__ import annotations

from ritualist import desktop_entry
from ritualist.errors import DependencyMissingError


def test_desktop_entry_launches_home_by_default(monkeypatch):
    called = []
    monkeypatch.setattr(desktop_entry, "_run_home", lambda: called.append("home"))
    monkeypatch.setattr(desktop_entry, "_run_gui", lambda: called.append("gui"))

    assert desktop_entry.main([]) == 0
    assert called == ["home"]


def test_desktop_entry_launches_home_with_option(monkeypatch):
    called = []
    monkeypatch.setattr(desktop_entry, "_run_home", lambda: called.append("home"))
    monkeypatch.setattr(desktop_entry, "_run_gui", lambda: called.append("gui"))

    assert desktop_entry.main(["--home"]) == 0
    assert called == ["home"]


def test_desktop_entry_launches_classic_gui_with_option(monkeypatch):
    called = []
    monkeypatch.setattr(desktop_entry, "_run_home", lambda: called.append("home"))
    monkeypatch.setattr(desktop_entry, "_run_gui", lambda: called.append("gui"))

    assert desktop_entry.main(["--classic-gui"]) == 0
    assert called == ["gui"]


def test_desktop_entry_launches_canvas_with_option(monkeypatch):
    called = []
    monkeypatch.setattr(desktop_entry, "_run_home", lambda: called.append(("home", "")))
    monkeypatch.setattr(desktop_entry, "_run_gui", lambda: called.append(("gui", "")))
    monkeypatch.setattr(desktop_entry, "_run_canvas", lambda canvas: called.append(("canvas", canvas)))

    assert desktop_entry.main(["--canvas"]) == 0
    assert called == [("canvas", "gaming_desktop")]


def test_desktop_entry_launches_named_canvas_with_option(monkeypatch):
    called = []
    monkeypatch.setattr(desktop_entry, "_run_home", lambda: called.append(("home", "")))
    monkeypatch.setattr(desktop_entry, "_run_gui", lambda: called.append(("gui", "")))
    monkeypatch.setattr(desktop_entry, "_run_canvas", lambda canvas: called.append(("canvas", canvas)))

    assert desktop_entry.main(["--canvas-use", "media_desktop"]) == 0
    assert called == [("canvas", "media_desktop")]


def test_desktop_entry_reports_home_dependency_error(monkeypatch, capsys):
    messages = []
    logs = []

    def missing_home() -> None:
        raise DependencyMissingError("Home UI requires PySide6; install ritualist[gui]")

    monkeypatch.setattr(desktop_entry, "_run_home", missing_home)
    monkeypatch.setattr(desktop_entry, "_show_error_dialog", messages.append)
    monkeypatch.setattr(desktop_entry, "_write_startup_error_log", lambda *args: logs.append(args))

    assert desktop_entry.main([]) == 1
    assert messages == ["Home UI requires PySide6; install ritualist[gui]"]
    assert logs[0][0] == "Home UI requires PySide6; install ritualist[gui]"
    assert "ritualist[gui]" in capsys.readouterr().err


def test_desktop_entry_rejects_unknown_options(monkeypatch, capsys):
    messages = []
    logs = []
    monkeypatch.setattr(desktop_entry, "_show_error_dialog", messages.append)
    monkeypatch.setattr(desktop_entry, "_write_startup_error_log", lambda *args: logs.append(args))

    assert desktop_entry.main(["--unknown"]) == 1
    assert "Unsupported desktop option" in messages[0]
    assert "Ritualist.exe --classic-gui" in logs[0][0]
    assert "Ritualist.exe --canvas gaming_desktop" in logs[0][0]
    assert "Unsupported desktop option" in capsys.readouterr().err


def test_desktop_entry_writes_startup_error_log(tmp_path, monkeypatch):
    monkeypatch.setattr("ritualist.paths.logs_dir", lambda: tmp_path)

    desktop_entry._write_startup_error_log("failed to start", "traceback details")

    text = (tmp_path / "startup-error.log").read_text(encoding="utf-8")
    assert "failed to start" in text
    assert "traceback details" in text
