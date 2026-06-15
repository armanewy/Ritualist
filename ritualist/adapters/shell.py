from __future__ import annotations

import os
import re
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

        local_command_path = resolve_local_command_path(command)
        if local_command_path is not None:
            if not local_command_path.exists():
                raise RitualistError(
                    "app.launch command path does not exist: "
                    f"{local_command_path}. Edit the recipe variable or config for this app path."
                )
            command = str(local_command_path)

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


def resolve_local_command_path(command: str) -> Path | None:
    expanded = _expand_command(command)
    if _is_url_or_shell_target(expanded):
        return None
    if not _looks_like_local_path(expanded):
        return None
    return Path(expanded)


def _expand_command(command: str) -> str:
    expanded = os.path.expanduser(os.path.expandvars(command))

    def replace_percent_var(match: re.Match[str]) -> str:
        key = match.group(1)
        return os.environ.get(key, match.group(0))

    return re.sub(r"%([^%]+)%", replace_percent_var, expanded)


def _is_url_or_shell_target(command: str) -> bool:
    lowered = command.casefold()
    return "://" in command or lowered.startswith("shell:")


def _looks_like_local_path(command: str) -> bool:
    lowered = command.casefold()
    return (
        lowered.endswith(".lnk")
        or lowered.endswith(".url")
        or lowered.startswith("\\\\")
        or bool(re.match(r"^[A-Za-z]:[\\/]", command))
        or command.startswith("~")
        or "/" in command
        or "\\" in command
    )
