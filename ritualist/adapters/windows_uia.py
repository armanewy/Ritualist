from __future__ import annotations

import re
import sys
import time
from typing import Any

from ritualist.errors import DependencyMissingError, PlatformUnsupportedError, RitualistError


class WindowsUIAutomationAdapter:
    def click_text(
        self,
        *,
        text: str,
        window_title_contains: str | None,
        control_type: str | None,
        exact: bool,
        button: str,
        timeout_seconds: float,
    ) -> None:
        _ensure_windows()
        try:
            from pywinauto import Desktop
        except ImportError as exc:
            raise DependencyMissingError(
                "desktop.click_text requires pywinauto; install ritualist[windows]"
            ) from exc

        desktop = Desktop(backend="uia")
        deadline = time.monotonic() + timeout_seconds
        matcher = _text_matcher(text, exact)

        while time.monotonic() < deadline:
            roots = _candidate_roots(desktop, window_title_contains)
            for root in roots:
                for element in _descendants(root, control_type):
                    label = _element_text(element)
                    if matcher(label):
                        element.click_input(button=button)
                        return
            time.sleep(0.25)

        raise RitualistError(f"visible text not found within {timeout_seconds:g}s: {text}")


class WindowsInputAdapter:
    def hotkey(self, keys: list[str]) -> None:
        _ensure_windows()
        try:
            from pywinauto.keyboard import send_keys
        except ImportError as exc:
            raise DependencyMissingError(
                "input.hotkey requires pywinauto; install ritualist[windows]"
            ) from exc

        send_keys(_format_hotkey(keys))


def _ensure_windows() -> None:
    if sys.platform != "win32":
        raise PlatformUnsupportedError("Windows UI/input automation is only supported on Windows")


def _candidate_roots(desktop: Any, window_title_contains: str | None) -> list[Any]:
    if not window_title_contains:
        return [desktop]
    pattern = re.compile(re.escape(window_title_contains), re.IGNORECASE)
    return [window for window in desktop.windows() if pattern.search(_element_text(window))]


def _descendants(root: Any, control_type: str | None) -> list[Any]:
    try:
        if control_type:
            return root.descendants(control_type=control_type)
        return root.descendants()
    except Exception:  # noqa: BLE001
        return []


def _element_text(element: Any) -> str:
    for attr in ("window_text",):
        try:
            value = getattr(element, attr)()
            if value:
                return str(value)
        except Exception:  # noqa: BLE001
            pass
    try:
        return str(element.element_info.name or "")
    except Exception:  # noqa: BLE001
        return ""


def _text_matcher(text: str, exact: bool):
    normalized = text.casefold()
    if exact:
        return lambda value: value.casefold() == normalized
    return lambda value: normalized in value.casefold()


def _format_hotkey(keys: list[str]) -> str:
    special = {
        "ctrl": "^",
        "control": "^",
        "alt": "%",
        "shift": "+",
        "win": "{VK_LWIN}",
        "enter": "{ENTER}",
        "escape": "{ESC}",
        "esc": "{ESC}",
        "tab": "{TAB}",
        "space": "{SPACE}",
    }
    formatted = []
    for key in keys:
        lowered = key.casefold()
        formatted.append(special.get(lowered, key))
    return "".join(formatted)
