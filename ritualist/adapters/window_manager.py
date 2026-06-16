from __future__ import annotations

import re
import sys
import time
from typing import Any

from ritualist.errors import DependencyMissingError, PlatformUnsupportedError, RitualistError
from ritualist.overlay import ScreenRect, TargetRegion


class WindowsWindowManager:
    def foreground_window_title(self) -> str:
        _ensure_windows()
        try:
            import win32gui
        except ImportError as exc:
            raise DependencyMissingError(
                "foreground window capture requires pywin32; install ritualist[windows]"
            ) from exc

        handle = win32gui.GetForegroundWindow()
        title = str(win32gui.GetWindowText(handle) or "").strip()
        if not title:
            raise RitualistError("foreground window title unavailable")
        return title

    def window_exists(
        self,
        *,
        title_contains: str | None,
        process_name: str | None,
        timeout_seconds: float,
    ) -> bool:
        try:
            self._find_window(title_contains, process_name, timeout_seconds)
            return True
        except (DependencyMissingError, PlatformUnsupportedError):
            raise
        except RitualistError:
            return False

    def find_window_region(
        self,
        *,
        title_contains: str | None,
        process_name: str | None,
        timeout_seconds: float,
    ) -> TargetRegion:
        window = self._find_window(title_contains, process_name, timeout_seconds)
        return TargetRegion(rect=_window_rect(window), window_title=_safe_window_text(window))

    def focus(
        self,
        *,
        title_contains: str | None,
        process_name: str | None,
        timeout_seconds: float,
    ) -> TargetRegion:
        window = self._find_window(title_contains, process_name, timeout_seconds)
        window.set_focus()
        return _target_region(window)

    def move_window(
        self,
        *,
        title_contains: str | None,
        process_name: str | None,
        timeout_seconds: float,
        x: int,
        y: int,
        width: int | None = None,
        height: int | None = None,
    ) -> TargetRegion:
        window = self._find_window(title_contains, process_name, timeout_seconds)
        current_rect = _window_rect(window)
        if (width is None or height is None) and current_rect is None:
            raise RitualistError(
                "window bounds unavailable; cannot move window without width and height"
            )
        rect = _validated_rect(
            x=x,
            y=y,
            width=width if width is not None else current_rect.width,
            height=height if height is not None else current_rect.height,
        )
        return _move_window_to_rect(window, rect)

    def resize_window(
        self,
        *,
        title_contains: str | None,
        process_name: str | None,
        timeout_seconds: float,
        width: int,
        height: int,
    ) -> TargetRegion:
        window = self._find_window(title_contains, process_name, timeout_seconds)
        current_rect = _window_rect(window)
        if current_rect is None:
            raise RitualistError("window bounds unavailable; cannot resize window")
        rect = _validated_rect(
            x=current_rect.x,
            y=current_rect.y,
            width=width,
            height=height,
        )
        return _move_window_to_rect(window, rect)

    def minimize(
        self,
        *,
        title_contains: str | None,
        process_name: str | None,
        timeout_seconds: float,
    ) -> TargetRegion:
        window = self._find_window(title_contains, process_name, timeout_seconds)
        window.minimize()
        return _target_region(window)

    def maximize(
        self,
        *,
        title_contains: str | None,
        process_name: str | None,
        timeout_seconds: float,
    ) -> TargetRegion:
        return self.maximize_window(
            title_contains=title_contains,
            process_name=process_name,
            timeout_seconds=timeout_seconds,
        )

    def maximize_window(
        self,
        *,
        title_contains: str | None,
        process_name: str | None,
        timeout_seconds: float,
    ) -> TargetRegion:
        window = self._find_window(title_contains, process_name, timeout_seconds)
        window.maximize()
        return _target_region(window)

    def restore_window(
        self,
        *,
        title_contains: str | None,
        process_name: str | None,
        timeout_seconds: float,
    ) -> TargetRegion:
        window = self._find_window(title_contains, process_name, timeout_seconds)
        window.restore()
        return _target_region(window)

    def snap_left(
        self,
        *,
        title_contains: str | None,
        process_name: str | None,
        timeout_seconds: float,
    ) -> TargetRegion:
        return self._snap_window(
            title_contains=title_contains,
            process_name=process_name,
            timeout_seconds=timeout_seconds,
            edge="left",
        )

    def snap_right(
        self,
        *,
        title_contains: str | None,
        process_name: str | None,
        timeout_seconds: float,
    ) -> TargetRegion:
        return self._snap_window(
            title_contains=title_contains,
            process_name=process_name,
            timeout_seconds=timeout_seconds,
            edge="right",
        )

    def snap_top(
        self,
        *,
        title_contains: str | None,
        process_name: str | None,
        timeout_seconds: float,
    ) -> TargetRegion:
        return self._snap_window(
            title_contains=title_contains,
            process_name=process_name,
            timeout_seconds=timeout_seconds,
            edge="top",
        )

    def snap_bottom(
        self,
        *,
        title_contains: str | None,
        process_name: str | None,
        timeout_seconds: float,
    ) -> TargetRegion:
        return self._snap_window(
            title_contains=title_contains,
            process_name=process_name,
            timeout_seconds=timeout_seconds,
            edge="bottom",
        )

    def list_monitors(self) -> list[ScreenRect]:
        return _monitor_rects()

    def wait(
        self,
        *,
        title_contains: str | None,
        process_name: str | None,
        timeout_seconds: float,
    ) -> TargetRegion:
        window = self._find_window(title_contains, process_name, timeout_seconds)
        return _target_region(window)

    def _snap_window(
        self,
        *,
        title_contains: str | None,
        process_name: str | None,
        timeout_seconds: float,
        edge: str,
    ) -> TargetRegion:
        window = self._find_window(title_contains, process_name, timeout_seconds)
        monitor = _monitor_for_window(_window_rect(window), _monitor_rects())
        rect = _snap_rect(monitor, edge)
        return _move_window_to_rect(window, rect)

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

        while True:
            for window in desktop.windows():
                title = _safe_window_text(window)
                if title_pattern and not title_pattern.search(title):
                    continue
                if process_ids is not None and _safe_process_id(window) not in process_ids:
                    continue
                return window
            if time.monotonic() >= deadline:
                break
            time.sleep(min(0.25, max(0.0, deadline - time.monotonic())))

        matcher = title_contains or process_name or "window"
        raise RitualistError(f"window not found within {timeout_seconds:g}s: {matcher}")


def _ensure_windows() -> None:
    if sys.platform != "win32":
        raise PlatformUnsupportedError("Windows UI/window automation is only supported on Windows")


def _monitor_rects() -> list[ScreenRect]:
    _ensure_windows()
    try:
        import win32api
    except ImportError as exc:
        raise DependencyMissingError(
            "window monitor listing requires pywin32; install ritualist[windows]"
        ) from exc

    rects: list[ScreenRect] = []
    for monitor, _device_context, _monitor_rect in win32api.EnumDisplayMonitors():
        info = win32api.GetMonitorInfo(monitor)
        rect = _screen_rect_from_sequence(info.get("Work") or info.get("Monitor"))
        if rect is not None:
            rects.append(rect)
    if not rects:
        raise RitualistError("no monitors found")
    return rects


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


def _window_rect(window: Any) -> ScreenRect | None:
    try:
        rect = window.rectangle()
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


def _screen_rect_from_sequence(rect: Any) -> ScreenRect | None:
    if rect is None:
        return None
    try:
        left, top, right, bottom = rect
    except (TypeError, ValueError):
        return _screen_rect_from_object(rect)
    width = max(0, int(right) - int(left))
    height = max(0, int(bottom) - int(top))
    if width <= 0 or height <= 0:
        return None
    return ScreenRect(x=int(left), y=int(top), width=width, height=height)


def _validated_rect(*, x: int, y: int, width: int, height: int) -> ScreenRect:
    rect = ScreenRect(x=int(x), y=int(y), width=int(width), height=int(height))
    if not rect.is_valid:
        raise RitualistError("window layout bounds must have positive width and height")
    return rect


def _move_window_to_rect(window: Any, rect: ScreenRect) -> TargetRegion:
    mover = getattr(window, "move_window", None)
    if callable(mover):
        mover(
            rect.x,
            rect.y,
            rect.width,
            rect.height,
            repaint=True,
        )
    else:
        _move_window_by_handle(window, rect)
    return TargetRegion(
        rect=_window_rect(window) or rect,
        window_title=_safe_window_text(window),
    )


def _move_window_by_handle(window: Any, rect: ScreenRect) -> None:
    handle = _window_handle(window)
    if handle is None:
        raise RitualistError("window handle unavailable; cannot move window")
    try:
        from pywinauto.controls.hwndwrapper import HwndWrapper
    except ImportError as exc:
        raise DependencyMissingError(
            "window layout actions require pywinauto/pywin32; install ritualist[windows]"
        ) from exc

    HwndWrapper(handle).move_window(
        rect.x,
        rect.y,
        rect.width,
        rect.height,
        repaint=True,
    )


def _window_handle(window: Any) -> int | None:
    candidates = (
        getattr(window, "handle", None),
        getattr(getattr(window, "element_info", None), "handle", None),
    )
    for candidate in candidates:
        try:
            value = candidate() if callable(candidate) else candidate
            if value:
                return int(value)
        except Exception:  # noqa: BLE001 - third-party wrappers vary here.
            continue
    return None


def _monitor_for_window(window_rect: ScreenRect | None, monitors: list[ScreenRect]) -> ScreenRect:
    if not monitors:
        raise RitualistError("no monitors found")
    if window_rect is None:
        return monitors[0]

    center_x = window_rect.x + window_rect.width // 2
    center_y = window_rect.y + window_rect.height // 2
    for monitor in monitors:
        if (
            monitor.x <= center_x < monitor.x + monitor.width
            and monitor.y <= center_y < monitor.y + monitor.height
        ):
            return monitor
    return monitors[0]


def _snap_rect(monitor: ScreenRect, edge: str) -> ScreenRect:
    half_width = max(1, monitor.width // 2)
    half_height = max(1, monitor.height // 2)
    if edge == "left":
        return ScreenRect(monitor.x, monitor.y, half_width, monitor.height)
    if edge == "right":
        return ScreenRect(
            monitor.x + monitor.width - half_width,
            monitor.y,
            half_width,
            monitor.height,
        )
    if edge == "top":
        return ScreenRect(monitor.x, monitor.y, monitor.width, half_height)
    if edge == "bottom":
        return ScreenRect(
            monitor.x,
            monitor.y + monitor.height - half_height,
            monitor.width,
            half_height,
        )
    raise RitualistError(f"unsupported window snap edge: {edge}")


def _target_region(window: Any) -> TargetRegion:
    return TargetRegion(rect=_window_rect(window), window_title=_safe_window_text(window))
