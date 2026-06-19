from __future__ import annotations

from typing import Any
import os


def place_qml_window(
    root: Any,
    *,
    anchor: str,
    margin: int = 16,
    fallback_width: int = 420,
    fallback_height: int = 520,
) -> None:
    if root is None:
        return
    rect = _available_geometry(root)
    if rect is None:
        return

    rect_x = _qt_number(rect, "x", 0)
    rect_y = _qt_number(rect, "y", 0)
    rect_width = max(1, _qt_number(rect, "width", 0))
    rect_height = max(1, _qt_number(rect, "height", 0))
    width = max(1, _root_number(root, "width", fallback_width))
    height = max(1, _root_number(root, "height", fallback_height))

    x = rect_x + rect_width - width - margin
    if anchor == "bottom-right":
        y = rect_y + rect_height - height - margin
    elif anchor == "right-center":
        y = rect_y + max(margin, (rect_height - height) // 2)
    else:
        y = rect_y + margin

    x = min(max(rect_x + margin, x), rect_x + rect_width - width)
    y = min(max(rect_y + margin, y), rect_y + rect_height - height)
    _set_root_position(root, int(x), int(y))


def activate_qml_window(root: Any) -> None:
    if root is None:
        return
    if hasattr(root, "forceActiveFocus"):
        root.forceActiveFocus()
    if hasattr(root, "raise_"):
        root.raise_()
    if hasattr(root, "requestActivate"):
        root.requestActivate()
    if os.name != "nt":
        return
    hwnd = _window_handle(root)
    if hwnd <= 0:
        return
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.ShowWindow.restype = wintypes.BOOL
        user32.BringWindowToTop.argtypes = [wintypes.HWND]
        user32.BringWindowToTop.restype = wintypes.BOOL
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.SetForegroundWindow.restype = wintypes.BOOL
        user32.SetActiveWindow.argtypes = [wintypes.HWND]
        user32.SetActiveWindow.restype = wintypes.HWND
        user32.SetFocus.argtypes = [wintypes.HWND]
        user32.SetFocus.restype = wintypes.HWND
        user32.GetForegroundWindow.argtypes = []
        user32.GetForegroundWindow.restype = wintypes.HWND
        switch_to_this_window = getattr(user32, "SwitchToThisWindow", None)
        if switch_to_this_window is not None:
            switch_to_this_window.argtypes = [wintypes.HWND, wintypes.BOOL]
            switch_to_this_window.restype = None
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        kernel32.GetCurrentThreadId.argtypes = []
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD
        user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
        user32.AttachThreadInput.restype = wintypes.BOOL
        user32.SetWindowPos.argtypes = [
            wintypes.HWND,
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint,
        ]
        user32.SetWindowPos.restype = wintypes.BOOL
        handle = wintypes.HWND(hwnd)
        _apply_transient_tool_window_style(user32, wintypes, ctypes, handle)
        _activate_win32_window(user32, kernel32, wintypes, handle, switch_to_this_window)
    except Exception:
        return


def _window_handle(root: Any) -> int:
    try:
        if hasattr(root, "winId"):
            return int(root.winId())
    except Exception:
        return 0
    return 0


def _available_geometry(root: Any) -> Any | None:
    screen = _screen_at_cursor()
    if screen is None and hasattr(root, "screen"):
        try:
            screen_attr = root.screen
            screen = screen_attr() if callable(screen_attr) else screen_attr
        except Exception:
            screen = None
    if screen is None or not hasattr(screen, "availableGeometry"):
        return None
    try:
        return screen.availableGeometry()
    except Exception:
        return None


def _screen_at_cursor() -> Any | None:
    try:
        from PySide6.QtGui import QCursor, QGuiApplication

        return QGuiApplication.screenAt(QCursor.pos())
    except Exception:
        return None


def _root_number(root: Any, name: str, fallback: int) -> int:
    value = getattr(root, name, None)
    try:
        if callable(value):
            return int(value())
        if value is not None:
            return int(value)
    except Exception:
        pass
    try:
        property_value = root.property(name)
        if property_value is not None:
            return int(property_value)
    except Exception:
        pass
    return fallback


def _qt_number(obj: Any, name: str, fallback: int) -> int:
    value = getattr(obj, name, None)
    try:
        if callable(value):
            return int(value())
        if value is not None:
            return int(value)
    except Exception:
        return fallback
    return fallback


def _set_root_position(root: Any, x: int, y: int) -> None:
    try:
        if hasattr(root, "setX") and hasattr(root, "setY"):
            root.setX(x)
            root.setY(y)
            return
    except Exception:
        pass
    try:
        root.setProperty("x", x)
        root.setProperty("y", y)
    except Exception:
        return


def _activate_win32_window(
    user32: Any,
    kernel32: Any,
    wintypes: Any,
    handle: Any,
    switch_to_this_window: Any | None = None,
) -> None:
    sw_show = 5
    hwnd_topmost = wintypes.HWND(-1)
    hwnd_notopmost = wintypes.HWND(-2)
    swp_no_size = 0x0001
    swp_no_move = 0x0002
    swp_no_activate = 0x0010
    swp_show_window = 0x0040
    flags = swp_no_move | swp_no_size | swp_show_window

    user32.ShowWindow(handle, sw_show)
    user32.SetWindowPos(handle, hwnd_topmost, 0, 0, 0, 0, flags)
    user32.SetWindowPos(handle, hwnd_notopmost, 0, 0, 0, 0, flags | swp_no_activate)

    current_thread = kernel32.GetCurrentThreadId()
    target_thread = user32.GetWindowThreadProcessId(handle, None)
    foreground = user32.GetForegroundWindow()
    foreground_thread = (
        user32.GetWindowThreadProcessId(foreground, None) if int(foreground or 0) else 0
    )
    attached: list[int] = []
    try:
        for thread_id in {int(target_thread or 0), int(foreground_thread or 0)}:
            if thread_id and thread_id != int(current_thread):
                if user32.AttachThreadInput(current_thread, thread_id, True):
                    attached.append(thread_id)
        user32.BringWindowToTop(handle)
        user32.SetForegroundWindow(handle)
        user32.SetActiveWindow(handle)
        user32.SetFocus(handle)
        if switch_to_this_window is not None and int(user32.GetForegroundWindow() or 0) != int(handle):
            switch_to_this_window(handle, True)
    finally:
        for thread_id in attached:
            user32.AttachThreadInput(current_thread, thread_id, False)


def _apply_transient_tool_window_style(
    user32: Any,
    wintypes: Any,
    ctypes_module: Any,
    handle: Any,
) -> None:
    gwl_exstyle = -20
    ws_ex_toolwindow = 0x00000080
    ws_ex_appwindow = 0x00040000
    swp_no_size = 0x0001
    swp_no_move = 0x0002
    swp_no_zorder = 0x0004
    swp_no_activate = 0x0010
    swp_frame_changed = 0x0020

    get_window_long = _window_long_api(user32, "GetWindowLongPtrW", "GetWindowLongW")
    set_window_long = _window_long_api(user32, "SetWindowLongPtrW", "SetWindowLongW")
    if get_window_long is None or set_window_long is None:
        return

    try:
        get_window_long.argtypes = [wintypes.HWND, ctypes_module.c_int]
        get_window_long.restype = ctypes_module.c_ssize_t
        set_window_long.argtypes = [wintypes.HWND, ctypes_module.c_int, ctypes_module.c_ssize_t]
        set_window_long.restype = ctypes_module.c_ssize_t
    except Exception:
        pass

    current_style = int(get_window_long(handle, gwl_exstyle) or 0)
    desired_style = (current_style & ~ws_ex_appwindow) | ws_ex_toolwindow
    if desired_style == current_style:
        return

    set_window_long(handle, gwl_exstyle, desired_style)
    user32.SetWindowPos(
        handle,
        wintypes.HWND(0),
        0,
        0,
        0,
        0,
        swp_no_move | swp_no_size | swp_no_zorder | swp_no_activate | swp_frame_changed,
    )


def _window_long_api(user32: Any, ptr_name: str, fallback_name: str) -> Any | None:
    api = getattr(user32, ptr_name, None)
    if api is not None:
        return api
    return getattr(user32, fallback_name, None)
