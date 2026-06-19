from __future__ import annotations

from dataclasses import dataclass
import sys
from typing import Any


TASKBAR_CREATED = "TaskbarCreated"


@dataclass(frozen=True)
class ShellEventRegistration:
    supported: bool
    taskbar_created_message: int | None
    message: str


class WindowsShellEventAdapter:
    def __init__(self, *, winapi: Any | None = None, platform: str | None = None) -> None:
        self._winapi = winapi
        self._platform = platform
        self._taskbar_created_message: int | None = None

    def register_taskbar_created(self) -> ShellEventRegistration:
        if not self._is_windows():
            return ShellEventRegistration(
                supported=False,
                taskbar_created_message=None,
                message="TaskbarCreated notifications are only supported on Windows",
            )
        message_id = int(self._api().register_window_message(TASKBAR_CREATED))
        self._taskbar_created_message = message_id
        return ShellEventRegistration(
            supported=True,
            taskbar_created_message=message_id,
            message="registered TaskbarCreated Explorer restart notification",
        )

    def is_taskbar_created(self, message: int) -> bool:
        if self._taskbar_created_message is None:
            registration = self.register_taskbar_created()
            if not registration.supported or registration.taskbar_created_message is None:
                return False
        return int(message) == self._taskbar_created_message

    def _api(self) -> Any:
        return self._winapi if self._winapi is not None else _Win32ShellEventApi()

    def _is_windows(self) -> bool:
        return (self._platform or sys.platform) == "win32"


class FakeShellEventAdapter:
    def __init__(self, *, message_id: int = 0x8001, supported: bool = True) -> None:
        self.message_id = int(message_id)
        self.supported = supported

    def register_taskbar_created(self) -> ShellEventRegistration:
        return ShellEventRegistration(
            supported=self.supported,
            taskbar_created_message=self.message_id if self.supported else None,
            message="fake TaskbarCreated notification",
        )

    def is_taskbar_created(self, message: int) -> bool:
        return self.supported and int(message) == self.message_id


class _Win32ShellEventApi:
    def register_window_message(self, name: str) -> int:
        import ctypes

        return int(ctypes.windll.user32.RegisterWindowMessageW(str(name)))
