from __future__ import annotations

import sys
import traceback
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

from setpiece.errors import SetpieceError
from setpiece.e2e import record_event


@dataclass(frozen=True)
class DesktopLaunch:
    mode: str
    canvas: str | None = None
    host: str = "windowed"
    taskbar_policy: str = "respect"
    startup: bool = False
    open_picker: bool = False


def main(argv: Sequence[str] | None = None) -> int:
    """Launch the desktop entry point used by Windows app bundles."""
    try:
        launch = _launch_mode(sys.argv[1:] if argv is None else argv)
        record_event(
            "desktop_entry.launch",
            mode=launch.mode,
            value=launch.canvas,
            host=launch.host,
            taskbar_policy=launch.taskbar_policy,
        )
        if launch.mode == "agent":
            return _run_agent(startup=launch.startup, open_picker=launch.open_picker)
        if launch.mode == "classic-gui":
            _run_gui()
        elif launch.mode == "canvas":
            _run_canvas(launch.canvas, host=launch.host, taskbar_policy=launch.taskbar_policy)
        else:
            _run_home()
    except SetpieceError as exc:
        _report_startup_error(str(exc), traceback.format_exc())
        return 1
    except Exception as exc:  # noqa: BLE001 - last-resort GUI startup reporting.
        _report_startup_error(f"Setpiece failed to start: {exc}", traceback.format_exc())
        return 1
    return 0


def _run_agent(*, startup: bool = False, open_picker: bool = False) -> int:
    from setpiece.agent.app import run_agent

    return run_agent(startup=startup, open_picker=open_picker)


def _run_gui() -> None:
    from setpiece.ui.app import run_gui

    run_gui()


def _run_home() -> None:
    from setpiece.home.app import run_home

    run_home(mock=False)


def _run_canvas(canvas: str | None, *, host: str = "windowed", taskbar_policy: str = "respect") -> None:
    from setpiece.canvas import default_canvas_for_host, resolve_canvas_host_config
    from setpiece.canvas.app import run_canvas_use

    host_config = resolve_canvas_host_config(host, taskbar_policy=taskbar_policy)
    run_canvas_use(default_canvas_for_host(canvas, host_config), mock=False, host_config=host_config)


def _launch_mode(argv: Sequence[str]) -> DesktopLaunch:
    args = tuple(argv)
    if not args or args == ("--home",):
        return DesktopLaunch("home")
    if args and args[0] == "--agent":
        return _agent_launch(args[1:])
    if args in (("--classic-gui",), ("--gui",)):
        return DesktopLaunch("classic-gui")
    if args and (args[0] == "--room" or args[0].startswith("--room=")):
        if args[0] == "--room":
            return _room_launch(args[1:])
        return _room_launch((args[0].split("=", 1)[1], *args[1:]))
    if args and args[0] in {"--canvas", "--canvas-use"}:
        return _canvas_launch(args[1:])
    raise SetpieceError(
        "Unsupported desktop option. Use Setpiece.exe for Home or "
        "Setpiece.exe --agent for the tray Agent, "
        "Setpiece.exe --classic-gui for the classic GUI, or "
        "Setpiece.exe --room gaming --host desktop-work-area for a Room, or "
        "Setpiece.exe --canvas gaming_desktop for Canvas Use Mode."
    )


def _agent_launch(argv: Sequence[str]) -> DesktopLaunch:
    startup = False
    open_picker = False
    for token in argv:
        if token == "--startup":
            startup = True
        elif token == "--open-picker":
            open_picker = True
        else:
            raise SetpieceError(f"Unsupported Agent option for packaged app: {token}")
    if startup and open_picker:
        raise SetpieceError("--agent accepts either --startup or --open-picker, not both.")
    return DesktopLaunch("agent", startup=startup, open_picker=open_picker)


def _room_launch(argv: Sequence[str]) -> DesktopLaunch:
    from setpiece.rooms import room_by_id

    room_id: str | None = None
    host = "windowed"
    taskbar_policy = "respect"
    args = list(argv)
    while args:
        token = args.pop(0)
        if token == "--host":
            host = _pop_option_value("--host", args)
        elif token.startswith("--host="):
            host = token.split("=", 1)[1]
        elif token == "--taskbar-policy":
            taskbar_policy = _pop_option_value("--taskbar-policy", args)
        elif token.startswith("--taskbar-policy="):
            taskbar_policy = token.split("=", 1)[1]
        elif token.startswith("-"):
            raise SetpieceError(f"Unsupported Room option for packaged app: {token}")
        elif room_id is None:
            room_id = token
        else:
            raise SetpieceError(f"Unexpected extra Room argument for packaged app: {token}")
    if room_id is None:
        raise SetpieceError("--room requires a Room id.")
    room = room_by_id(room_id)
    return DesktopLaunch("canvas", canvas=room.canvas_id, host=host, taskbar_policy=taskbar_policy)


def _canvas_launch(argv: Sequence[str]) -> DesktopLaunch:
    canvas: str | None = None
    host = "windowed"
    taskbar_policy = "respect"
    args = list(argv)
    while args:
        token = args.pop(0)
        if token == "--host":
            host = _pop_option_value("--host", args)
        elif token.startswith("--host="):
            host = token.split("=", 1)[1]
        elif token == "--taskbar-policy":
            taskbar_policy = _pop_option_value("--taskbar-policy", args)
        elif token.startswith("--taskbar-policy="):
            taskbar_policy = token.split("=", 1)[1]
        elif token.startswith("-"):
            raise SetpieceError(f"Unsupported Canvas option for packaged app: {token}")
        elif canvas is None:
            canvas = token
        else:
            raise SetpieceError(f"Unexpected extra Canvas argument for packaged app: {token}")
    if canvas is None and host == "windowed":
        canvas = "gaming_desktop"
    return DesktopLaunch("canvas", canvas=canvas, host=host, taskbar_policy=taskbar_policy)


def _pop_option_value(option: str, args: list[str]) -> str:
    if not args:
        raise SetpieceError(f"{option} requires a value.")
    return args.pop(0)


def _report_startup_error(message: str, details: str | None = None) -> None:
    record_event("desktop_entry.startup_error", message=message)
    print(message, file=sys.stderr)
    _write_startup_error_log(message, details)
    _show_error_dialog(message)


def _write_startup_error_log(message: str, details: str | None = None) -> None:
    try:
        from setpiece.paths import logs_dir

        path = logs_dir() / "startup-error.log"
        payload = [
            f"time: {datetime.now(timezone.utc).isoformat()}",
            f"executable: {getattr(sys, 'executable', '')}",
            f"message: {message}",
        ]
        if details:
            payload.extend(["details:", details.rstrip()])
        with path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(payload) + "\n\n")
    except Exception:  # noqa: BLE001 - startup reporting must never mask the original failure.
        return


def _show_error_dialog(message: str) -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, message, "Setpiece", 0x10)
    except Exception:  # noqa: BLE001 - stderr is enough if a dialog is unavailable.
        return


if __name__ == "__main__":
    raise SystemExit(main())
