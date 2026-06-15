from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Mapping

from ritualist.errors import DependencyMissingError, RitualistError


class ShellAdapter:
    def launch(
        self,
        *,
        command: str,
        args: list[str] | None = None,
        cwd: str | None = None,
        wait: bool = False,
        env: Mapping[str, str] | None = None,
    ) -> None:
        args = args or []
        launch_env = os.environ.copy()
        if env:
            launch_env.update(env)

        if os.name == "nt" and not args and not wait and _looks_like_startfile_target(command):
            startfile = getattr(os, "startfile", None)
            if startfile is None:
                raise RitualistError("Windows startfile support is unavailable")
            startfile(command)  # type: ignore[misc]
            return

        completed = subprocess.Popen(
            [command, *args],
            cwd=str(Path(cwd)) if cwd else None,
            env=launch_env,
        )
        if wait:
            return_code = completed.wait()
            if return_code != 0:
                raise RitualistError(f"process exited with code {return_code}: {command}")

    def wait_process(self, process_name: str, *, timeout_seconds: float) -> None:
        try:
            import psutil
        except ImportError as exc:
            raise DependencyMissingError(
                "app.wait_process requires optional dependency psutil; install ritualist[windows]"
            ) from exc

        deadline = time.monotonic() + timeout_seconds
        normalized = process_name.casefold()
        while time.monotonic() < deadline:
            for process in psutil.process_iter(["name"]):
                try:
                    name = process.info.get("name") or ""
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
                if name.casefold() == normalized:
                    return
            time.sleep(0.25)
        raise RitualistError(f"process did not appear within {timeout_seconds:g}s: {process_name}")


def _looks_like_startfile_target(command: str) -> bool:
    lowered = command.casefold()
    return (
        "://" in command
        or lowered.endswith(".lnk")
        or lowered.endswith(".url")
        or lowered.startswith("shell:")
    )
