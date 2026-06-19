from __future__ import annotations

from dataclasses import dataclass
import sys
from typing import Any


WM_HOTKEY = 0x0312
ERROR_HOTKEY_ALREADY_REGISTERED = 1409

_MODIFIERS = {
    "alt": 0x0001,
    "ctrl": 0x0002,
    "control": 0x0002,
    "shift": 0x0004,
    "win": 0x0008,
    "windows": 0x0008,
}

_VIRTUAL_KEYS = {
    "backspace": 0x08,
    "tab": 0x09,
    "enter": 0x0D,
    "return": 0x0D,
    "escape": 0x1B,
    "esc": 0x1B,
    "space": 0x20,
    "pageup": 0x21,
    "pagedown": 0x22,
    "end": 0x23,
    "home": 0x24,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "insert": 0x2D,
    "delete": 0x2E,
}
_VIRTUAL_KEYS.update({f"f{number}": 0x6F + number for number in range(1, 25)})


@dataclass(frozen=True)
class HotkeySpec:
    keys: tuple[str, ...]

    @classmethod
    def from_value(cls, value: str | list[str] | tuple[str, ...] | None) -> HotkeySpec:
        if value is None:
            return DEFAULT_HOTKEY
        if isinstance(value, str):
            parts = tuple(part.strip().casefold() for part in value.split("+") if part.strip())
        else:
            parts = tuple(str(part).strip().casefold() for part in value if str(part).strip())
        if len(parts) < 2:
            raise ValueError("global hotkey must include at least one modifier and one key")
        return cls(parts)

    def to_win32(self) -> tuple[int, int]:
        modifiers = 0
        key: str | None = None
        for part in self.keys:
            modifier = _MODIFIERS.get(part)
            if modifier is not None:
                modifiers |= modifier
                continue
            if key is not None:
                raise ValueError(f"global hotkey has more than one non-modifier key: {self.label}")
            key = part
        if modifiers == 0 or key is None:
            raise ValueError(f"global hotkey must include modifiers and one key: {self.label}")
        return modifiers, _virtual_key(key)

    @property
    def label(self) -> str:
        return "+".join(self.keys)


DEFAULT_HOTKEY = HotkeySpec(("win", "ctrl", "r"))


@dataclass(frozen=True)
class HotkeyRegistrationResult:
    registered: bool
    status: str
    hotkey: HotkeySpec
    message: str
    error_code: int | None = None


@dataclass(frozen=True)
class HotkeyEvent:
    hotkey_id: int
    hotkey: HotkeySpec


class WindowsGlobalHotkeyAdapter:
    """Register one narrow global hotkey with RegisterHotKey."""

    def __init__(
        self,
        *,
        hotkey: str | list[str] | tuple[str, ...] | None = None,
        hotkey_id: int = 0x5254,
        winapi: Any | None = None,
        platform: str | None = None,
    ) -> None:
        self.hotkey = HotkeySpec.from_value(hotkey)
        self.hotkey_id = int(hotkey_id)
        self._winapi = winapi
        self._platform = platform
        self._registered = False

    def register(self) -> HotkeyRegistrationResult:
        if not self._is_windows():
            return HotkeyRegistrationResult(
                registered=False,
                status="unsupported",
                hotkey=self.hotkey,
                message="global hotkeys are only supported on Windows",
            )

        try:
            modifiers, virtual_key = self.hotkey.to_win32()
        except ValueError as exc:
            return HotkeyRegistrationResult(
                registered=False,
                status="invalid",
                hotkey=self.hotkey,
                message=str(exc),
            )

        api = self._api()
        ok = bool(api.register_hotkey(None, self.hotkey_id, modifiers, virtual_key))
        if ok:
            self._registered = True
            return HotkeyRegistrationResult(
                registered=True,
                status="registered",
                hotkey=self.hotkey,
                message=f"registered global hotkey {self.hotkey.label}",
            )

        error_code = api.get_last_error()
        status = "conflict" if error_code == ERROR_HOTKEY_ALREADY_REGISTERED else "failed"
        return HotkeyRegistrationResult(
            registered=False,
            status=status,
            hotkey=self.hotkey,
            message=_hotkey_failure_message(self.hotkey, error_code),
            error_code=error_code,
        )

    def unregister(self) -> HotkeyRegistrationResult:
        if not self._registered:
            return HotkeyRegistrationResult(
                registered=False,
                status="not_registered",
                hotkey=self.hotkey,
                message=f"global hotkey {self.hotkey.label} was not registered",
            )
        if not self._is_windows():
            self._registered = False
            return HotkeyRegistrationResult(
                registered=False,
                status="unsupported",
                hotkey=self.hotkey,
                message="global hotkeys are only supported on Windows",
            )

        api = self._api()
        ok = bool(api.unregister_hotkey(None, self.hotkey_id))
        error_code = None if ok else api.get_last_error()
        self._registered = False
        return HotkeyRegistrationResult(
            registered=False,
            status="unregistered" if ok else "unregister_failed",
            hotkey=self.hotkey,
            message=(
                f"unregistered global hotkey {self.hotkey.label}"
                if ok
                else f"failed to unregister global hotkey {self.hotkey.label}"
            ),
            error_code=error_code,
        )

    def poll(self) -> HotkeyEvent | None:
        if not self._registered or not self._is_windows():
            return None
        message = self._api().peek_hotkey_message()
        if message is None or int(message) != self.hotkey_id:
            return None
        return HotkeyEvent(hotkey_id=self.hotkey_id, hotkey=self.hotkey)

    def close(self) -> None:
        self.unregister()

    def __enter__(self) -> WindowsGlobalHotkeyAdapter:
        self.register()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _api(self) -> Any:
        return self._winapi if self._winapi is not None else _Win32HotkeyApi()

    def _is_windows(self) -> bool:
        return (self._platform or sys.platform) == "win32"


class FakeGlobalHotkeyAdapter:
    def __init__(
        self,
        *,
        hotkey: str | list[str] | tuple[str, ...] | None = None,
        fail_status: str | None = None,
    ) -> None:
        self.hotkey = HotkeySpec.from_value(hotkey)
        self.fail_status = fail_status
        self.registered = False
        self.events: list[HotkeyEvent] = []

    def register(self) -> HotkeyRegistrationResult:
        if self.fail_status:
            return HotkeyRegistrationResult(
                registered=False,
                status=self.fail_status,
                hotkey=self.hotkey,
                message=f"fake hotkey registration {self.fail_status}",
            )
        self.registered = True
        return HotkeyRegistrationResult(
            registered=True,
            status="registered",
            hotkey=self.hotkey,
            message=f"registered fake global hotkey {self.hotkey.label}",
        )

    def unregister(self) -> HotkeyRegistrationResult:
        self.registered = False
        return HotkeyRegistrationResult(
            registered=False,
            status="unregistered",
            hotkey=self.hotkey,
            message=f"unregistered fake global hotkey {self.hotkey.label}",
        )

    def emit(self) -> None:
        self.events.append(HotkeyEvent(hotkey_id=0, hotkey=self.hotkey))

    def poll(self) -> HotkeyEvent | None:
        if not self.events:
            return None
        return self.events.pop(0)

    def close(self) -> None:
        self.unregister()


class _Win32HotkeyApi:
    def register_hotkey(
        self,
        hwnd: object,
        hotkey_id: int,
        modifiers: int,
        virtual_key: int,
    ) -> int:
        import ctypes

        return int(ctypes.windll.user32.RegisterHotKey(hwnd, hotkey_id, modifiers, virtual_key))

    def unregister_hotkey(self, hwnd: object, hotkey_id: int) -> int:
        import ctypes

        return int(ctypes.windll.user32.UnregisterHotKey(hwnd, hotkey_id))

    def get_last_error(self) -> int:
        import ctypes

        return int(ctypes.windll.kernel32.GetLastError())

    def peek_hotkey_message(self) -> int | None:
        import ctypes
        from ctypes import wintypes

        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        class MSG(ctypes.Structure):
            _fields_ = [
                ("hwnd", wintypes.HWND),
                ("message", wintypes.UINT),
                ("wParam", wintypes.WPARAM),
                ("lParam", wintypes.LPARAM),
                ("time", wintypes.DWORD),
                ("pt", POINT),
            ]

        msg = MSG()
        remove_message = 0x0001
        has_message = ctypes.windll.user32.PeekMessageW(
            ctypes.byref(msg),
            None,
            WM_HOTKEY,
            WM_HOTKEY,
            remove_message,
        )
        if not has_message:
            return None
        return int(msg.wParam)


def _virtual_key(key: str) -> int:
    if len(key) == 1 and key.isalpha():
        return ord(key.upper())
    if len(key) == 1 and key.isdigit():
        return ord(key)
    try:
        return _VIRTUAL_KEYS[key]
    except KeyError as exc:
        raise ValueError(f"unsupported global hotkey key: {key}") from exc


def _hotkey_failure_message(hotkey: HotkeySpec, error_code: int) -> str:
    if error_code == ERROR_HOTKEY_ALREADY_REGISTERED:
        return f"global hotkey {hotkey.label} is already registered by another application"
    return f"failed to register global hotkey {hotkey.label}; Win32 error {error_code}"
