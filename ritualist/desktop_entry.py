from __future__ import annotations

import sys
import traceback
from collections.abc import Sequence
from datetime import datetime, timezone

from ritualist.errors import RitualistError
from ritualist.e2e import record_event


def main(argv: Sequence[str] | None = None) -> int:
    """Launch the desktop entry point used by Windows app bundles."""
    try:
        launch_mode, launch_value = _launch_mode(sys.argv[1:] if argv is None else argv)
        record_event("desktop_entry.launch", mode=launch_mode, value=launch_value)
        if launch_mode == "classic-gui":
            _run_gui()
        elif launch_mode == "canvas":
            _run_canvas(launch_value or "gaming_desktop")
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


def _run_canvas(canvas: str) -> None:
    from ritualist.canvas.app import run_canvas_use

    run_canvas_use(canvas, mock=False)


def _launch_mode(argv: Sequence[str]) -> tuple[str, str | None]:
    args = tuple(argv)
    if not args or args == ("--home",):
        return ("home", None)
    if args in (("--classic-gui",), ("--gui",)):
        return ("classic-gui", None)
    if args in (("--canvas",), ("--canvas-use",)):
        return ("canvas", "gaming_desktop")
    if len(args) == 2 and args[0] in {"--canvas", "--canvas-use"}:
        return ("canvas", args[1])
    raise RitualistError(
        "Unsupported desktop option. Use Ritualist.exe for Home or "
        "Ritualist.exe --classic-gui for the classic GUI, or "
        "Ritualist.exe --canvas gaming_desktop for Canvas Use Mode."
    )


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
