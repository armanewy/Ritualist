from __future__ import annotations

from dataclasses import dataclass
import sys
from typing import Any, Literal

from setpiece.errors import PlatformUnsupportedError, SetpieceError
from setpiece.overlay import ScreenRect

TaskbarEdge = Literal["left", "top", "right", "bottom"]


@dataclass(frozen=True)
class Point:
    x: int
    y: int


@dataclass(frozen=True)
class MonitorGeometry:
    handle: object
    monitor_rect: ScreenRect
    work_area: ScreenRect
    primary: bool = False

    @property
    def taskbar_edge(self) -> TaskbarEdge | None:
        return taskbar_edge(self.monitor_rect, self.work_area)


@dataclass(frozen=True)
class MonitorSelection:
    monitor: MonitorGeometry
    requested_point: Point
    fallback_used: bool = False
    reason: str | None = None


class WindowsMonitorGeometryAdapter:
    def __init__(self, *, winapi: Any | None = None, platform: str | None = None) -> None:
        self._winapi = winapi
        self._platform = platform

    def list_monitors(self) -> list[MonitorGeometry]:
        self._ensure_windows()
        monitors = self._api().list_monitors()
        if not monitors:
            raise SetpieceError("no monitors found")
        return monitors

    def cursor_point(self) -> Point:
        self._ensure_windows()
        x, y = self._api().get_cursor_pos()
        return Point(int(x), int(y))

    def target_monitor(
        self,
        *,
        point: Point | tuple[int, int] | None = None,
        preferred_handle: object | None = None,
    ) -> MonitorSelection:
        requested = _coerce_point(point) if point is not None else self.cursor_point()
        monitors = self.list_monitors()
        if preferred_handle is not None:
            for monitor in monitors:
                if monitor.handle == preferred_handle:
                    return MonitorSelection(monitor=monitor, requested_point=requested)

        selected = _monitor_containing_point(monitors, requested)
        if selected is not None:
            reason = "preferred monitor was not available" if preferred_handle is not None else None
            return MonitorSelection(
                monitor=selected,
                requested_point=requested,
                fallback_used=preferred_handle is not None,
                reason=reason,
            )

        primary = _primary_or_first(monitors)
        return MonitorSelection(
            monitor=primary,
            requested_point=requested,
            fallback_used=True,
            reason="point was outside current monitors",
        )

    def target_work_area(
        self,
        *,
        point: Point | tuple[int, int] | None = None,
        preferred_handle: object | None = None,
    ) -> ScreenRect:
        return self.target_monitor(point=point, preferred_handle=preferred_handle).monitor.work_area

    def _api(self) -> Any:
        return self._winapi if self._winapi is not None else _Win32MonitorApi()

    def _ensure_windows(self) -> None:
        if (self._platform or sys.platform) != "win32":
            raise PlatformUnsupportedError("Windows monitor geometry is only supported on Windows")


class FakeMonitorGeometryAdapter:
    def __init__(
        self,
        monitors: list[MonitorGeometry] | None = None,
        *,
        cursor: Point | tuple[int, int] = Point(0, 0),
    ) -> None:
        self.monitors = monitors or [
            MonitorGeometry(
                handle="primary",
                monitor_rect=ScreenRect(0, 0, 1920, 1080),
                work_area=ScreenRect(0, 0, 1920, 1040),
                primary=True,
            )
        ]
        self.cursor = _coerce_point(cursor)

    def list_monitors(self) -> list[MonitorGeometry]:
        return list(self.monitors)

    def cursor_point(self) -> Point:
        return self.cursor

    def target_monitor(
        self,
        *,
        point: Point | tuple[int, int] | None = None,
        preferred_handle: object | None = None,
    ) -> MonitorSelection:
        adapter = WindowsMonitorGeometryAdapter(winapi=self, platform="win32")
        return adapter.target_monitor(point=point, preferred_handle=preferred_handle)

    def target_work_area(
        self,
        *,
        point: Point | tuple[int, int] | None = None,
        preferred_handle: object | None = None,
    ) -> ScreenRect:
        return self.target_monitor(point=point, preferred_handle=preferred_handle).monitor.work_area

    def get_cursor_pos(self) -> tuple[int, int]:
        return self.cursor.x, self.cursor.y


class _Win32MonitorApi:
    def list_monitors(self) -> list[MonitorGeometry]:
        import ctypes
        from ctypes import wintypes

        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long),
            ]

        class MONITORINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("rcMonitor", RECT),
                ("rcWork", RECT),
                ("dwFlags", wintypes.DWORD),
            ]

        monitors: list[MonitorGeometry] = []

        monitor_enum_proc = ctypes.WINFUNCTYPE(
            ctypes.c_int,
            wintypes.HMONITOR,
            wintypes.HDC,
            ctypes.POINTER(RECT),
            wintypes.LPARAM,
        )

        def callback(handle: object, _hdc: object, _rect: object, _data: object) -> int:
            info = MONITORINFO()
            info.cbSize = ctypes.sizeof(MONITORINFO)
            if ctypes.windll.user32.GetMonitorInfoW(handle, ctypes.byref(info)):
                monitors.append(
                    MonitorGeometry(
                        handle=int(handle),
                        monitor_rect=_rect_to_screen_rect(info.rcMonitor),
                        work_area=_rect_to_screen_rect(info.rcWork),
                        primary=bool(info.dwFlags & 1),
                    )
                )
            return 1

        ctypes.windll.user32.EnumDisplayMonitors(None, None, monitor_enum_proc(callback), 0)
        return monitors

    def get_cursor_pos(self) -> tuple[int, int]:
        import ctypes
        from ctypes import wintypes

        point = wintypes.POINT()
        if not ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
            raise SetpieceError("cursor position unavailable")
        return int(point.x), int(point.y)


def taskbar_edge(monitor_rect: ScreenRect, work_area: ScreenRect) -> TaskbarEdge | None:
    insets = {
        "left": max(0, work_area.x - monitor_rect.x),
        "top": max(0, work_area.y - monitor_rect.y),
        "right": max(
            0,
            monitor_rect.x + monitor_rect.width - (work_area.x + work_area.width),
        ),
        "bottom": max(
            0,
            monitor_rect.y + monitor_rect.height - (work_area.y + work_area.height),
        ),
    }
    edge, size = max(insets.items(), key=lambda item: item[1])
    return edge if size > 0 else None


def _coerce_point(value: Point | tuple[int, int]) -> Point:
    if isinstance(value, Point):
        return value
    x, y = value
    return Point(int(x), int(y))


def _monitor_containing_point(
    monitors: list[MonitorGeometry],
    point: Point,
) -> MonitorGeometry | None:
    for monitor in monitors:
        rect = monitor.monitor_rect
        if rect.x <= point.x < rect.x + rect.width and rect.y <= point.y < rect.y + rect.height:
            return monitor
    return None


def _primary_or_first(monitors: list[MonitorGeometry]) -> MonitorGeometry:
    for monitor in monitors:
        if monitor.primary:
            return monitor
    return monitors[0]


def _rect_to_screen_rect(rect: Any) -> ScreenRect:
    return ScreenRect(
        x=int(rect.left),
        y=int(rect.top),
        width=max(0, int(rect.right) - int(rect.left)),
        height=max(0, int(rect.bottom) - int(rect.top)),
    )
