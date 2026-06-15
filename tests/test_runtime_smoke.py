from __future__ import annotations

import base64
import io
import os
import struct
import sys
import tempfile
import time
import urllib.parse
import uuid
import wave

import pytest

if os.environ.get("RITUALIST_RUNTIME_SMOKE") != "1":
    pytest.skip(
        "set RITUALIST_RUNTIME_SMOKE=1 to run browser/window/UIA runtime smoke tests",
        allow_module_level=True,
    )

if sys.platform != "win32":
    pytest.skip("runtime smoke test requires Windows UI Automation", allow_module_level=True)


def test_runtime_workflow_with_real_adapters() -> None:
    from ritualist.adapters import create_default_adapters
    from ritualist.executor import WorkflowExecutor
    from ritualist.models import Recipe

    media_url = _local_media_url()
    window_title = f"Ritualist E2E Native UIA {uuid.uuid4()}"
    result_path = os.path.join(tempfile.gettempdir(), f"ritualist-e2e-{uuid.uuid4()}.txt")
    child_code = _native_button_window_code()
    recipe = Recipe.model_validate(
        {
            "id": "runtime_e2e",
            "name": "Runtime E2E",
            "steps": [
                {
                    "name": "Open local media",
                    "action": "browser.open",
                    "url": media_url,
                    "browser": "chromium",
                },
                {
                    "name": "Loop and play local media",
                    "action": "browser.media",
                    "selector": "#media",
                    "loop": True,
                    "muted": True,
                    "play": True,
                    "timeout_seconds": 10,
                },
                {
                    "name": "Launch native test window",
                    "action": "app.launch",
                    "command": sys.executable,
                    "args": ["-c", child_code, result_path, window_title],
                },
                {
                    "name": "Wait for native test window",
                    "action": "window.wait",
                    "title_contains": window_title,
                    "timeout_seconds": 10,
                },
                {
                    "name": "Focus native test window",
                    "action": "window.focus",
                    "title_contains": window_title,
                    "timeout_seconds": 10,
                },
                {
                    "name": "Minimize native test window",
                    "action": "window.minimize",
                    "title_contains": window_title,
                    "timeout_seconds": 10,
                },
                {
                    "name": "Maximize native test window",
                    "action": "window.maximize",
                    "title_contains": window_title,
                    "timeout_seconds": 10,
                },
                {
                    "name": "Click Play",
                    "action": "desktop.click_text",
                    "text": "Play",
                    "window_title_contains": window_title,
                    "requires_confirmation": True,
                    "timeout_seconds": 10,
                },
            ],
        }
    )

    adapters = create_default_adapters()
    try:
        summary = WorkflowExecutor(adapters=adapters, confirmer=lambda _prompt: True).run(recipe)
        assert summary.success
        assert [result.status for result in summary.results] == ["success"] * 8
        _wait_for_file(result_path)
        with open(result_path, "r", encoding="utf-8") as handle:
            assert handle.read() == "clicked"
    finally:
        close = getattr(adapters.browser, "close", None)
        if close:
            close()
        try:
            os.remove(result_path)
        except OSError:
            pass


def _local_media_url() -> str:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"".join(struct.pack("<h", 0) for _ in range(800)))

    audio = base64.b64encode(buffer.getvalue()).decode("ascii")
    html = (
        "<!doctype html><title>Ritualist E2E Runtime Media</title>"
        f"<audio id='media' controls src='data:audio/wav;base64,{audio}'></audio>"
    )
    return "data:text/html," + urllib.parse.quote(html)


def _native_button_window_code() -> str:
    return r'''
import ctypes
import sys
import win32api
import win32con
import win32gui

result_path = sys.argv[1]
window_title = sys.argv[2]
button_id = 1001
class_name = "RitualistE2ENativeTestWindow"

def wndproc(hwnd, msg, wparam, lparam):
    if msg == win32con.WM_COMMAND and win32api.LOWORD(wparam) == button_id:
        with open(result_path, "w", encoding="utf-8") as handle:
            handle.write("clicked")
        win32gui.PostQuitMessage(0)
        return 0
    if msg == win32con.WM_TIMER:
        win32gui.PostQuitMessage(0)
        return 0
    if msg == win32con.WM_DESTROY:
        win32gui.PostQuitMessage(0)
        return 0
    return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

hinst = win32api.GetModuleHandle(None)
wc = win32gui.WNDCLASS()
wc.lpfnWndProc = wndproc
wc.hInstance = hinst
wc.lpszClassName = class_name
try:
    win32gui.RegisterClass(wc)
except win32gui.error:
    pass
hwnd = win32gui.CreateWindow(
    class_name,
    window_title,
    win32con.WS_OVERLAPPEDWINDOW,
    240,
    240,
    420,
    240,
    0,
    0,
    hinst,
    None,
)
win32gui.CreateWindow(
    "BUTTON",
    "Play",
    win32con.WS_CHILD | win32con.WS_VISIBLE | win32con.BS_PUSHBUTTON,
    140,
    80,
    140,
    44,
    hwnd,
    button_id,
    hinst,
    None,
)
ctypes.windll.user32.SetTimer(hwnd, 1, 30000, 0)
win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
win32gui.UpdateWindow(hwnd)
win32gui.PumpMessages()
'''


def _wait_for_file(path: str) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if os.path.exists(path):
            return
        time.sleep(0.2)
    raise AssertionError(f"file was not created: {path}")
