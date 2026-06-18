from __future__ import annotations

from dataclasses import dataclass
import sys
from typing import Any, Literal

from ritualist.errors import PlatformUnsupportedError
from ritualist.overlay import ScreenRect

from .monitor_geometry import MonitorGeometry, Point, WindowsMonitorGeometryAdapter

TrayGeometrySource = Literal["shell_notify_icon", "cursor", "unsupported", "unavailable"]


@dataclass(frozen=True)
class TrayIconIdentity:
    hwnd: int
    uid: int = 0


@dataclass(frozen=True)
class TrayGeometryResult:
    rect: ScreenRect | None
    source: TrayGeometrySource
    monitor: MonitorGeometry | None = None
    message: str | None = None


class WindowsTrayGeometryAdapter:
    def __init__(
        self,
        *,
        shellapi: Any | None = None,
        monitor_adapter: Any | None = None,
        platform: str | None = None,
    ) -> None:
        self._shellapi = shellapi
        self._monitor_adapter = monitor_adapter
        self._platform = platform

    def icon_geometry(
        self,
        identity: TrayIconIdentity | None = None,
        *,
        fallback_to_cursor: bool = True,
    ) -> TrayGeometryResult:
        if not self._is_windows():
            return TrayGeometryResult(
                rect=None,
                source="unsupported",
                message="tray icon geometry is only supported on Windows",
            )

        if identity is not None:
            rect = self._api().notify_icon_rect(identity)
            if rect is not None:
                monitor = self._monitor_adapter_or_default().target_monitor(
                    point=(rect.x + rect.width // 2, rect.y + rect.height // 2)
                ).monitor
                return TrayGeometryResult(rect=rect, source="shell_notify_icon", monitor=monitor)

        if fallback_to_cursor:
            return self.cursor_fallback()

        return TrayGeometryResult(
            rect=None,
            source="unavailable",
            message="tray icon geometry unavailable",
        )

    def cursor_fallback(self) -> TrayGeometryResult:
        if not self._is_windows():
            return TrayGeometryResult(
                rect=None,
                source="unsupported",
                message="tray icon geometry is only supported on Windows",
            )
        monitor_adapter = self._monitor_adapter_or_default()
        point = monitor_adapter.cursor_point()
        selection = monitor_adapter.target_monitor(point=point)
        return TrayGeometryResult(
            rect=ScreenRect(point.x, point.y, 1, 1),
            source="cursor",
            monitor=selection.monitor,
            message="using cursor position because tray icon geometry was unavailable",
        )

    def _api(self) -> Any:
        return self._shellapi if self._shellapi is not None else _Win32ShellNotifyApi()

    def _monitor_adapter_or_default(self) -> Any:
        if self._monitor_adapter is not None:
            return self._monitor_adapter
        return WindowsMonitorGeometryAdapter(platform=self._platform)

    def _is_windows(self) -> bool:
        return (self._platform or sys.platform) == "win32"


class FakeTrayGeometryAdapter:
    def __init__(
        self,
        *,
        rect: ScreenRect | None = None,
        monitor: MonitorGeometry | None = None,
        cursor: Point | tuple[int, int] = Point(0, 0),
    ) -> None:
        self.rect = rect
        self.monitor = monitor
        self.cursor = cursor if isinstance(cursor, Point) else Point(int(cursor[0]), int(cursor[1]))

    def icon_geometry(
        self,
        identity: TrayIconIdentity | None = None,
        *,
        fallback_to_cursor: bool = True,
    ) -> TrayGeometryResult:
        if self.rect is not None:
            return TrayGeometryResult(
                rect=self.rect,
                source="shell_notify_icon",
                monitor=self.monitor,
            )
        if not fallback_to_cursor:
            return TrayGeometryResult(rect=None, source="unavailable")
        return TrayGeometryResult(
            rect=ScreenRect(self.cursor.x, self.cursor.y, 1, 1),
            source="cursor",
            monitor=self.monitor,
        )


class _Win32ShellNotifyApi:
    def notify_icon_rect(self, identity: TrayIconIdentity) -> ScreenRect | None:
        import ctypes
        from ctypes import wintypes

        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long),
            ]

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        class NOTIFYICONIDENTIFIER(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("hWnd", wintypes.HWND),
                ("uID", wintypes.UINT),
                ("guidItem", GUID),
            ]

        rect = RECT()
        notify_id = NOTIFYICONIDENTIFIER()
        notify_id.cbSize = ctypes.sizeof(NOTIFYICONIDENTIFIER)
        notify_id.hWnd = wintypes.HWND(identity.hwnd)
        notify_id.uID = identity.uid
        result = ctypes.windll.shell32.Shell_NotifyIconGetRect(
            ctypes.byref(notify_id),
            ctypes.byref(rect),
        )
        if result != 0:
            return None
        return ScreenRect(
            x=int(rect.left),
            y=int(rect.top),
            width=max(0, int(rect.right) - int(rect.left)),
            height=max(0, int(rect.bottom) - int(rect.top)),
        )


def unsupported_tray_geometry() -> TrayGeometryResult:
    raise PlatformUnsupportedError("tray icon geometry is only supported on Windows")
