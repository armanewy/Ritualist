from __future__ import annotations

import sys
import traceback
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

from ritualist.errors import RitualistError
from ritualist.e2e import record_event


@dataclass(frozen=True)
class DesktopLaunch:
    mode: str
    canvas: str | None = None
    host: str = "windowed"
    taskbar_policy: str = "respect"


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
        if launch.mode == "classic-gui":
            _run_gui()
        elif launch.mode == "canvas":
            _run_canvas(launch.canvas, host=launch.host, taskbar_policy=launch.taskbar_policy)
        else:
            _run_home()
    except RitualistError as exc:
        _report_startup_error(str(exc), traceback.format_exc())
        return 1
    except Exception as exc:  # noqa: BLE001 - last-resort GUI startup reporting.
        _report_startup_error(f"Ritualist failed to start: {exc}", traceback.format_exc())
        return 1
    return 0


def _run_gui() -> None:
    from ritualist.ui.app import run_gui

    run_gui()


def _run_home() -> None:
    from ritualist.home.app import run_home

    run_home(mock=False)


def _run_canvas(canvas: str | None, *, host: str = "windowed", taskbar_policy: str = "respect") -> None:
    from ritualist.canvas import default_canvas_for_host, resolve_canvas_host_config
    from ritualist.canvas.app import run_canvas_use

    host_config = resolve_canvas_host_config(host, taskbar_policy=taskbar_policy)
    run_canvas_use(default_canvas_for_host(canvas, host_config), mock=False, host_config=host_config)


def _launch_mode(argv: Sequence[str]) -> DesktopLaunch:
    args = tuple(argv)
    if not args or args == ("--home",):
        return DesktopLaunch("home")
    if args in (("--classic-gui",), ("--gui",)):
        return DesktopLaunch("classic-gui")
    if args and args[0] in {"--canvas", "--canvas-use"}:
        return _canvas_launch(args[1:])
    raise RitualistError(
        "Unsupported desktop option. Use Ritualist.exe for Home or "
        "Ritualist.exe --classic-gui for the classic GUI, or "
        "Ritualist.exe --canvas gaming_desktop for Canvas Use Mode."
    )


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
            raise RitualistError(f"Unsupported Canvas option for packaged app: {token}")
        elif canvas is None:
            canvas = token
        else:
            raise RitualistError(f"Unexpected extra Canvas argument for packaged app: {token}")
    if canvas is None and host == "windowed":
        canvas = "gaming_desktop"
    return DesktopLaunch("canvas", canvas=canvas, host=host, taskbar_policy=taskbar_policy)


def _pop_option_value(option: str, args: list[str]) -> str:
    if not args:
        raise RitualistError(f"{option} requires a value.")
    return args.pop(0)


def _report_startup_error(message: str, details: str | None = None) -> None:
    record_event("desktop_entry.startup_error", message=message)
    print(message, file=sys.stderr)
    _write_startup_error_log(message, details)
    _show_error_dialog(message)


def _write_startup_error_log(message: str, details: str | None = None) -> None:
    try:
        from ritualist.paths import logs_dir

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

        ctypes.windll.user32.MessageBoxW(None, message, "Ritualist", 0x10)
    except Exception:  # noqa: BLE001 - stderr is enough if a dialog is unavailable.
        return


if __name__ == "__main__":
    raise SystemExit(main())
