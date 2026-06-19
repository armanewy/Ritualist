from __future__ import annotations

from setpiece import desktop_entry
from setpiece.errors import DependencyMissingError


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


def test_desktop_entry_launches_agent_with_startup_option(monkeypatch):
    called = []
    monkeypatch.setattr(
        desktop_entry,
        "_run_agent",
        lambda *, startup=False, open_picker=False: called.append((startup, open_picker)) or 0,
    )

    assert desktop_entry.main(["--agent", "--startup"]) == 0
    assert called == [(True, False)]


def test_desktop_entry_launches_agent_with_open_picker_option(monkeypatch):
    called = []
    monkeypatch.setattr(
        desktop_entry,
        "_run_agent",
        lambda *, startup=False, open_picker=False: called.append((startup, open_picker)) or 0,
    )

    assert desktop_entry.main(["--agent", "--open-picker"]) == 0
    assert called == [(False, True)]


def test_desktop_entry_agent_defaults_to_picker_activation(monkeypatch):
    called = []
    monkeypatch.setattr(
        desktop_entry,
        "_run_agent",
        lambda *, startup=False, open_picker=False: called.append((startup, open_picker)) or 0,
    )

    assert desktop_entry.main(["--agent"]) == 0
    assert called == [(False, False)]


def test_desktop_entry_launches_canvas_with_option(monkeypatch):
    called = []
    monkeypatch.setattr(desktop_entry, "_run_home", lambda: called.append(("home", "")))
    monkeypatch.setattr(desktop_entry, "_run_gui", lambda: called.append(("gui", "")))
    monkeypatch.setattr(
        desktop_entry,
        "_run_canvas",
        lambda canvas, *, host, taskbar_policy: called.append((canvas, host, taskbar_policy)),
    )

    assert desktop_entry.main(["--canvas"]) == 0
    assert called == [("gaming_desktop", "windowed", "respect")]


def test_desktop_entry_launches_named_canvas_with_option(monkeypatch):
    called = []
    monkeypatch.setattr(desktop_entry, "_run_home", lambda: called.append(("home", "")))
    monkeypatch.setattr(desktop_entry, "_run_gui", lambda: called.append(("gui", "")))
    monkeypatch.setattr(
        desktop_entry,
        "_run_canvas",
        lambda canvas, *, host, taskbar_policy: called.append((canvas, host, taskbar_policy)),
    )

    assert desktop_entry.main(["--canvas-use", "media_desktop"]) == 0
    assert called == [("media_desktop", "windowed", "respect")]


def test_desktop_entry_launches_desktop_work_area_canvas_with_option(monkeypatch):
    called = []
    monkeypatch.setattr(desktop_entry, "_run_home", lambda: called.append(("home", "")))
    monkeypatch.setattr(desktop_entry, "_run_gui", lambda: called.append(("gui", "")))
    monkeypatch.setattr(
        desktop_entry,
        "_run_canvas",
        lambda canvas, *, host, taskbar_policy: called.append((canvas, host, taskbar_policy)),
    )

    assert desktop_entry.main(["--canvas", "--host", "desktop-work-area"]) == 0
    assert called == [(None, "desktop-work-area", "respect")]


def test_desktop_entry_launches_room_by_alias_without_running_ritual(monkeypatch):
    called = []
    monkeypatch.setattr(desktop_entry, "_run_home", lambda: called.append(("home", "")))
    monkeypatch.setattr(desktop_entry, "_run_gui", lambda: called.append(("gui", "")))
    monkeypatch.setattr(
        desktop_entry,
        "_run_canvas",
        lambda canvas, *, host, taskbar_policy: called.append((canvas, host, taskbar_policy)),
    )

    assert desktop_entry.main(["--room", "gaming", "--host", "desktop-work-area"]) == 0
    assert called == [("gaming_desktop", "desktop-work-area", "respect")]


def test_desktop_entry_launches_room_in_window_by_default(monkeypatch):
    called = []
    monkeypatch.setattr(desktop_entry, "_run_home", lambda: called.append(("home", "")))
    monkeypatch.setattr(desktop_entry, "_run_gui", lambda: called.append(("gui", "")))
    monkeypatch.setattr(
        desktop_entry,
        "_run_canvas",
        lambda canvas, *, host, taskbar_policy: called.append((canvas, host, taskbar_policy)),
    )

    assert desktop_entry.main(["--room=project"]) == 0
    assert called == [("project_room", "windowed", "respect")]


def test_desktop_entry_rejects_unknown_room(monkeypatch, capsys):
    messages = []
    logs = []
    monkeypatch.setattr(desktop_entry, "_show_error_dialog", messages.append)
    monkeypatch.setattr(desktop_entry, "_write_startup_error_log", lambda *args: logs.append(args))

    assert desktop_entry.main(["--room", "minimal"]) == 1
    assert "room not found" in messages[0]
    assert "room not found" in capsys.readouterr().err


def test_desktop_entry_rejects_unknown_canvas_option(monkeypatch, capsys):
    messages = []
    logs = []
    monkeypatch.setattr(desktop_entry, "_show_error_dialog", messages.append)
    monkeypatch.setattr(desktop_entry, "_write_startup_error_log", lambda *args: logs.append(args))

    assert desktop_entry.main(["--canvas", "--fullscreen"]) == 1
    assert "Unsupported Canvas option" in messages[0]
    assert "--fullscreen" in capsys.readouterr().err


def test_desktop_entry_rejects_unknown_agent_option(monkeypatch, capsys):
    messages = []
    logs = []
    monkeypatch.setattr(desktop_entry, "_show_error_dialog", messages.append)
    monkeypatch.setattr(desktop_entry, "_write_startup_error_log", lambda *args: logs.append(args))

    assert desktop_entry.main(["--agent", "--legacy-home"]) == 1
    assert "Unsupported Agent option" in messages[0]
    assert "--legacy-home" in capsys.readouterr().err


def test_desktop_entry_reports_home_dependency_error(monkeypatch, capsys):
    messages = []
    logs = []

    def missing_home() -> None:
        raise DependencyMissingError("Home UI requires PySide6; install setpiece[gui]")

    monkeypatch.setattr(desktop_entry, "_run_home", missing_home)
    monkeypatch.setattr(desktop_entry, "_show_error_dialog", messages.append)
    monkeypatch.setattr(desktop_entry, "_write_startup_error_log", lambda *args: logs.append(args))

    assert desktop_entry.main([]) == 1
    assert messages == ["Home UI requires PySide6; install setpiece[gui]"]
    assert logs[0][0] == "Home UI requires PySide6; install setpiece[gui]"
    assert "setpiece[gui]" in capsys.readouterr().err


def test_desktop_entry_rejects_unknown_options(monkeypatch, capsys):
    messages = []
    logs = []
    monkeypatch.setattr(desktop_entry, "_show_error_dialog", messages.append)
    monkeypatch.setattr(desktop_entry, "_write_startup_error_log", lambda *args: logs.append(args))

    assert desktop_entry.main(["--unknown"]) == 1
    assert "Unsupported desktop option" in messages[0]
    assert "Setpiece.exe --agent" in logs[0][0]
    assert "Setpiece.exe --classic-gui" in logs[0][0]
    assert "Setpiece.exe --room gaming --host desktop-work-area" in logs[0][0]
    assert "Setpiece.exe --canvas gaming_desktop" in logs[0][0]
    assert "Unsupported desktop option" in capsys.readouterr().err


def test_desktop_entry_writes_startup_error_log(tmp_path, monkeypatch):
    monkeypatch.setattr("setpiece.paths.logs_dir", lambda: tmp_path)

    desktop_entry._write_startup_error_log("failed to start", "traceback details")

    text = (tmp_path / "startup-error.log").read_text(encoding="utf-8")
    assert "failed to start" in text
    assert "traceback details" in text
