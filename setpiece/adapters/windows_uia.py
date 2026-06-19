from __future__ import annotations

from dataclasses import dataclass
import re
import sys
import time
from typing import Any

from setpiece.errors import DependencyMissingError, PlatformUnsupportedError, SetpieceError
from setpiece.overlay import ScreenRect, TargetRegion


@dataclass(frozen=True)
class WindowInspection:
    title: str
    labels: list[str]


@dataclass(frozen=True)
class UIAControlInspection:
    name: str
    control_type: str
    enabled: bool
    visible: bool


@dataclass(frozen=True)
class WindowControlInspection:
    title: str
    controls: list[UIAControlInspection]


class WindowsUIAutomationAdapter:
    def text_visible(
        self,
        *,
        text: str,
        window_title_contains: str,
        control_type: str | None,
        exact: bool,
        timeout_seconds: float,
    ) -> bool:
        _ensure_windows()
        desktop = _desktop()
        deadline = time.monotonic() + timeout_seconds
        matcher = _text_matcher(text, exact)

        while True:
            roots = _candidate_roots(desktop, window_title_contains)
            for root in roots:
                for element in _preferred_descendants(root, control_type):
                    if matcher(_element_text(element)):
                        return True
            if timeout_seconds <= 0 or time.monotonic() >= deadline:
                return False
            time.sleep(0.25)

    def find_text_region(
        self,
        *,
        text: str,
        window_title_contains: str,
        control_type: str | None,
        exact: bool,
        timeout_seconds: float,
    ) -> TargetRegion | None:
        _ensure_windows()
        desktop = _desktop()
        deadline = time.monotonic() + timeout_seconds
        matcher = _text_matcher(text, exact)

        while True:
            roots = _candidate_roots(desktop, window_title_contains)
            for root in roots:
                for element in _preferred_descendants(root, control_type):
                    label = _element_text(element)
                    if matcher(label) and _is_visible_enabled(element):
                        return _target_region(root, element, label or text, control_type)
            if timeout_seconds <= 0 or time.monotonic() >= deadline:
                return None
            time.sleep(0.25)

    def inspect_windows(
        self,
        *,
        title_contains: str,
        limit: int,
        control_type: str | None,
    ) -> list[WindowInspection]:
        _ensure_windows()
        desktop = _desktop()
        roots = _candidate_roots(desktop, title_contains)
        return [
            WindowInspection(
                title=_element_text(root),
                labels=_candidate_labels([root], control_type, limit=limit),
            )
            for root in roots
        ]

    def inspect_control_tree(
        self,
        *,
        title_contains: str,
        limit: int = 200,
    ) -> list[WindowControlInspection]:
        _ensure_windows()
        desktop = _desktop()
        roots = _candidate_roots(desktop, title_contains)
        windows: list[WindowControlInspection] = []
        for root in roots:
            controls: list[UIAControlInspection] = []
            for element in _descendants(root, None):
                name = _element_text(element).strip()
                control_type = _element_control_type(element)
                if not name and not control_type:
                    continue
                controls.append(
                    UIAControlInspection(
                        name=name,
                        control_type=control_type,
                        enabled=_is_enabled(element),
                        visible=_is_visible(element),
                    )
                )
                if len(controls) >= limit:
                    break
            windows.append(WindowControlInspection(title=_element_text(root), controls=controls))
        return windows

    def click_text(
        self,
        *,
        text: str,
        window_title_contains: str,
        control_type: str | None,
        exact: bool,
        button: str,
        timeout_seconds: float,
    ) -> TargetRegion:
        _ensure_windows()
        desktop = _desktop()
        deadline = time.monotonic() + timeout_seconds
        matcher = _text_matcher(text, exact)
        last_roots: list[Any] = []

        while True:
            roots = _candidate_roots(desktop, window_title_contains)
            last_roots = roots
            for root in roots:
                for element in _preferred_descendants(root, control_type):
                    label = _element_text(element)
                    if matcher(label) and _is_visible_enabled(element):
                        region = _target_region(root, element, label or text, control_type)
                        _activate(element, button=button)
                        return region
            if timeout_seconds <= 0 or time.monotonic() >= deadline:
                break
            time.sleep(0.25)

        if not last_roots:
            raise SetpieceError(
                f"target window not found within {timeout_seconds:g}s: {window_title_contains}"
            )
        candidates = _candidate_labels(last_roots, control_type)
        suffix = f" Candidate labels: {', '.join(candidates)}" if candidates else " No visible labels found."
        raise SetpieceError(
            f"visible text not found within {timeout_seconds:g}s in window "
            f"'{window_title_contains}': {text}.{suffix}"
        )

    def invoke_resolved_text_region(
        self,
        *,
        target: TargetRegion,
        text: str,
        window_title_contains: str,
        control_type: str | None,
        exact: bool,
        button: str,
        timeout_seconds: float,
    ) -> TargetRegion:
        _ensure_windows()
        if button != "left":
            raise SetpieceError("confirmed desktop clicks can only invoke left-button targets")
        if not target.target_identity:
            raise SetpieceError("confirmed desktop click target is missing resolved identity")
        desktop = _desktop()
        deadline = time.monotonic() + timeout_seconds
        matcher = _text_matcher(text, exact)

        while True:
            roots = _candidate_roots(desktop, window_title_contains)
            for root in roots:
                for element in _preferred_descendants(root, control_type):
                    label = _element_text(element)
                    if not matcher(label) or not _is_visible_enabled(element):
                        continue
                    if _element_identity(element) != target.target_identity:
                        continue
                    _invoke(element)
                    return _target_region(root, element, label or text, control_type)
            if timeout_seconds <= 0 or time.monotonic() >= deadline:
                raise SetpieceError(
                    "resolved target changed or disappeared before invocation: "
                    f"{text} in '{window_title_contains}'"
                )
            time.sleep(0.25)


class WindowsInputAdapter:
    def hotkey(self, keys: list[str]) -> None:
        _ensure_windows()
        try:
            from pywinauto.keyboard import send_keys
        except ImportError as exc:
            raise DependencyMissingError(
                "input.hotkey requires pywinauto; install setpiece[windows]"
            ) from exc

        send_keys(_format_hotkey(keys))


def _ensure_windows() -> None:
    if sys.platform != "win32":
        raise PlatformUnsupportedError("Windows UI/input automation is only supported on Windows")


def _desktop() -> Any:
    try:
        from pywinauto import Desktop
    except ImportError as exc:
        raise DependencyMissingError(
            "Windows UI Automation requires pywinauto; install setpiece[windows]"
        ) from exc
    return Desktop(backend="uia")


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
    return _is_visible(element) and _is_enabled(element)


def _is_visible(element: Any) -> bool:
    try:
        return bool(element.is_visible())
    except Exception:  # noqa: BLE001
        return True


def _is_enabled(element: Any) -> bool:
    try:
        return bool(element.is_enabled())
    except Exception:  # noqa: BLE001
        return True


def _activate(element: Any, *, button: str) -> None:
    if button != "left":
        raise SetpieceError("desktop.click_text does not support coordinate fallback clicks")
    _invoke(element)


def _invoke(element: Any) -> None:
    try:
        element.invoke()
        return
    except Exception:  # noqa: BLE001
        pass
    try:
        element.iface_invoke.Invoke()
        return
    except Exception as exc:  # noqa: BLE001
        raise SetpieceError("target does not support UI Automation invoke") from exc


def _target_region(
    root: Any,
    element: Any,
    label: str,
    control_type: str | None,
) -> TargetRegion:
    return TargetRegion(
        rect=_element_rect(element),
        window_title=_element_text(root),
        target_text=label,
        control_type=control_type,
        target_identity=_element_identity(element),
        visible=_is_visible(element),
        enabled=_is_enabled(element),
    )


def _element_identity(element: Any) -> str:
    parts: list[str] = []
    info = getattr(element, "element_info", None)
    for attr in ("runtime_id", "automation_id", "control_type", "class_name", "handle", "process_id"):
        try:
            value = getattr(info, attr)
        except Exception:  # noqa: BLE001
            value = None
        if callable(value):
            try:
                value = value()
            except Exception:  # noqa: BLE001
                value = None
        if value not in (None, "", []):
            parts.append(f"{attr}={value!r}")
    rect = _element_rect(element)
    if rect is not None:
        parts.append(f"rect={rect.x},{rect.y},{rect.width},{rect.height}")
    text = _element_text(element)
    if text:
        parts.append(f"text={text!r}")
    return "|".join(parts)


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


def _element_control_type(element: Any) -> str:
    try:
        value = getattr(element.element_info, "control_type", "")
        return str(value or "")
    except Exception:  # noqa: BLE001
        return ""


def _element_rect(element: Any) -> ScreenRect | None:
    try:
        rect = element.rectangle()
    except Exception:  # noqa: BLE001
        return None
    return _screen_rect_from_object(rect)


def _screen_rect_from_object(rect: Any) -> ScreenRect | None:
    try:
        left = int(rect.left)
        top = int(rect.top)
        right = int(rect.right)
        bottom = int(rect.bottom)
    except Exception:  # noqa: BLE001
        try:
            left = int(rect.left())
            top = int(rect.top())
            right = int(rect.right())
            bottom = int(rect.bottom())
        except Exception:  # noqa: BLE001
            return None
    width = max(0, right - left)
    height = max(0, bottom - top)
    if width <= 0 or height <= 0:
        return None
    return ScreenRect(x=left, y=top, width=width, height=height)


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
