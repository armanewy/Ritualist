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
        window_title_contains: str,
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
        last_roots: list[Any] = []

        while time.monotonic() < deadline:
            roots = _candidate_roots(desktop, window_title_contains)
            last_roots = roots
            for root in roots:
                for element in _preferred_descendants(root, control_type):
                    label = _element_text(element)
                    if matcher(label):
                        _activate(element, button=button)
                        return
            time.sleep(0.25)

        if not last_roots:
            raise RitualistError(
                f"target window not found within {timeout_seconds:g}s: {window_title_contains}"
            )
        candidates = _candidate_labels(last_roots, control_type)
        suffix = f" Candidate labels: {', '.join(candidates)}" if candidates else " No visible labels found."
        raise RitualistError(
            f"visible text not found within {timeout_seconds:g}s in window "
            f"'{window_title_contains}': {text}.{suffix}"
        )


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


def _preferred_descendants(root: Any, control_type: str | None) -> list[Any]:
    descendants = _descendants(root, control_type)
    return sorted(
        descendants,
        key=lambda element: (not _is_visible_enabled(element), _element_text(element).casefold()),
    )


def _is_visible_enabled(element: Any) -> bool:
    try:
        visible = bool(element.is_visible())
    except Exception:  # noqa: BLE001
        visible = True
    try:
        enabled = bool(element.is_enabled())
    except Exception:  # noqa: BLE001
        enabled = True
    return visible and enabled


def _activate(element: Any, *, button: str) -> None:
    if button == "left":
        try:
            element.invoke()
            return
        except Exception:  # noqa: BLE001
            pass
        try:
            element.iface_invoke.Invoke()
            return
        except Exception:  # noqa: BLE001
            pass
    element.click_input(button=button)


def _candidate_labels(roots: list[Any], control_type: str | None, *, limit: int = 30) -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()
    for root in roots:
        for element in _preferred_descendants(root, control_type):
            if not _is_visible_enabled(element):
                continue
            label = _element_text(element).strip()
            if not label or label in seen:
                continue
            labels.append(label)
            seen.add(label)
            if len(labels) >= limit:
                return labels
    return labels


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
