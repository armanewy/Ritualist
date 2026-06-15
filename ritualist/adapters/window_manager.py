from __future__ import annotations

import re
import sys
import time
from typing import Any

from ritualist.errors import DependencyMissingError, PlatformUnsupportedError, RitualistError


class WindowsWindowManager:
    def focus(
        self,
        *,
        title_contains: str | None,
        process_name: str | None,
        timeout_seconds: float,
    ) -> None:
        window = self._find_window(title_contains, process_name, timeout_seconds)
        window.set_focus()

    def minimize(
        self,
        *,
        title_contains: str | None,
        process_name: str | None,
        timeout_seconds: float,
    ) -> None:
        window = self._find_window(title_contains, process_name, timeout_seconds)
        window.minimize()

    def maximize(
        self,
        *,
        title_contains: str | None,
        process_name: str | None,
        timeout_seconds: float,
    ) -> None:
        window = self._find_window(title_contains, process_name, timeout_seconds)
        window.maximize()

    def wait(
        self,
        *,
        title_contains: str | None,
        process_name: str | None,
        timeout_seconds: float,
    ) -> None:
        self._find_window(title_contains, process_name, timeout_seconds)

    def _find_window(
        self,
        title_contains: str | None,
        process_name: str | None,
        timeout_seconds: float,
    ) -> Any:
        _ensure_windows()
        try:
            from pywinauto import Desktop
        except ImportError as exc:
            raise DependencyMissingError(
                "window actions require pywinauto; install ritualist[windows]"
            ) from exc

        process_ids = _matching_process_ids(process_name)
        title_pattern = re.compile(re.escape(title_contains), re.IGNORECASE) if title_contains else None
        deadline = time.monotonic() + timeout_seconds
        desktop = Desktop(backend="uia")

        while time.monotonic() < deadline:
            for window in desktop.windows():
                title = _safe_window_text(window)
                if title_pattern and not title_pattern.search(title):
                    continue
                if process_ids is not None and _safe_process_id(window) not in process_ids:
                    continue
                return window
            time.sleep(0.25)

        matcher = title_contains or process_name or "window"
        raise RitualistError(f"window not found within {timeout_seconds:g}s: {matcher}")


def _ensure_windows() -> None:
    if sys.platform != "win32":
        raise PlatformUnsupportedError("Windows UI/window automation is only supported on Windows")


def _matching_process_ids(process_name: str | None) -> set[int] | None:
    if process_name is None:
        return None
    try:
        import psutil
    except ImportError as exc:
        raise DependencyMissingError(
            "process-based window matching requires psutil; install ritualist[windows]"
        ) from exc

    normalized = process_name.casefold()
    ids: set[int] = set()
    for process in psutil.process_iter(["pid", "name"]):
        try:
            name = process.info.get("name") or ""
            if name.casefold() == normalized:
                ids.add(int(process.info["pid"]))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return ids


def _safe_window_text(window: Any) -> str:
    try:
        return window.window_text()
    except Exception:  # noqa: BLE001 - third-party wrapper can raise several COM errors.
        return ""


def _safe_process_id(window: Any) -> int | None:
    try:
        return int(window.process_id())
    except Exception:  # noqa: BLE001
        return None
