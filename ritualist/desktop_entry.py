from __future__ import annotations

import sys
import traceback
from datetime import datetime, timezone

from ritualist.errors import RitualistError
from ritualist.ui.app import run_gui


def main() -> int:
    """Launch the desktop GUI entry point used by Windows app bundles."""
    try:
        _run_gui()
    except RitualistError as exc:
        _report_startup_error(str(exc), traceback.format_exc())
        return 1
    except Exception as exc:  # noqa: BLE001 - last-resort GUI startup reporting.
        _report_startup_error(f"Ritualist failed to start: {exc}", traceback.format_exc())
        return 1
    return 0


def _run_gui() -> None:
    run_gui()


def _report_startup_error(message: str, details: str | None = None) -> None:
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
